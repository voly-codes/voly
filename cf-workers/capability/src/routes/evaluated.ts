import { Hono } from "hono";
import type {
  AppBindings,
  EvaluatedPackSnapshot,
  EvaluatedPackSnapshotItem,
} from "../types";

const MAX_PACKS = 32;
const MAX_PROVENANCE_HASHES = 64;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

export const evaluatedRoutes = new Hono<AppBindings>();

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(",")}}`;
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function authorized(header: string | undefined, secret: string): Promise<boolean> {
  const prefix = "Bearer ";
  if (!header?.startsWith(prefix) || !secret) return false;
  const [providedHash, secretHash] = await Promise.all([
    sha256(header.slice(prefix.length)),
    sha256(secret),
  ]);
  return providedHash === secretHash;
}

function validatePack(pack: EvaluatedPackSnapshotItem): string | null {
  if (!pack.capability_id?.trim()) return "capability_id required";
  if (!Number.isInteger(pack.version) || pack.version < 1) {
    return "version must be a positive integer";
  }
  if (!["pilot", "active", "retired"].includes(pack.state)) {
    return "invalid pack state";
  }
  if (!SHA256_PATTERN.test(pack.definition_hash ?? "")) {
    return "definition_hash must be sha256";
  }
  const hashes = pack.provenance?.instruction_hashes ?? {};
  if (Object.keys(hashes).length > MAX_PROVENANCE_HASHES) {
    return "too many provenance hashes";
  }
  if (Object.values(hashes).some((value) => !SHA256_PATTERN.test(value))) {
    return "provenance values must be sha256";
  }
  return null;
}

evaluatedRoutes.use("*", async (c, next) => {
  if (!(await authorized(c.req.header("Authorization"), c.env.EVALUATED_SYNC_TOKEN))) {
    return c.json({ ok: false, error: "unauthorized" }, 401);
  }
  await next();
});

evaluatedRoutes.post("/snapshots", async (c) => {
  try {
    const body = await c.req.json<EvaluatedPackSnapshot>();
    if (body.schema_version !== 1) {
      return c.json({ ok: false, error: "unsupported schema_version" }, 400);
    }
    if (!body.executor_id?.trim()) {
      return c.json({ ok: false, error: "executor_id required" }, 400);
    }
    if (!Array.isArray(body.packs) || body.packs.length > MAX_PACKS) {
      return c.json({ ok: false, error: "packs must contain at most 32 items" }, 400);
    }
    for (const pack of body.packs) {
      const error = validatePack(pack);
      if (error) return c.json({ ok: false, error }, 400);
    }

    const content = {
      schema_version: body.schema_version,
      executor_id: body.executor_id,
      packs: body.packs,
    };
    const payloadJson = stableStringify(content);
    const payloadHash = await sha256(payloadJson);
    if (body.snapshot_id !== payloadHash) {
      return c.json({ ok: false, error: "snapshot hash mismatch" }, 400);
    }

    const existing = await c.env.CAPABILITY_DB.prepare(
      `SELECT payload_sha256 FROM evaluated_snapshots WHERE snapshot_id = ?`,
    )
      .bind(body.snapshot_id)
      .first<{ payload_sha256: string }>();
    if (existing) {
      if (existing.payload_sha256 !== payloadHash) {
        return c.json({ ok: false, error: "snapshot conflict" }, 409);
      }
      return c.json({
        ok: true,
        snapshot_id: body.snapshot_id,
        idempotent: true,
        packs: body.packs.length,
      });
    }

    const now = Date.now();
    const statements = [
      c.env.CAPABILITY_DB.prepare(`
        INSERT OR IGNORE INTO evaluated_snapshots (
          snapshot_id, schema_version, executor_id, payload_json,
          payload_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
      `).bind(
        body.snapshot_id,
        body.schema_version,
        body.executor_id,
        payloadJson,
        payloadHash,
        now,
      ),
      ...body.packs.map((pack) =>
        c.env.CAPABILITY_DB.prepare(`
          INSERT INTO evaluated_pack_state (
            capability_id, version, executor_id, snapshot_id, state,
            definition_hash, provenance_json, decision_json, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(capability_id, version, executor_id) DO UPDATE SET
            snapshot_id = excluded.snapshot_id,
            state = excluded.state,
            definition_hash = excluded.definition_hash,
            provenance_json = excluded.provenance_json,
            decision_json = excluded.decision_json,
            updated_at = excluded.updated_at
        `).bind(
          pack.capability_id,
          pack.version,
          body.executor_id,
          body.snapshot_id,
          pack.state,
          pack.definition_hash,
          stableStringify(pack.provenance),
          stableStringify(pack.decision),
          now,
        ),
      ),
    ];
    await c.env.CAPABILITY_DB.batch(statements);
    return c.json({
      ok: true,
      snapshot_id: body.snapshot_id,
      idempotent: false,
      packs: body.packs.length,
    }, 201);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return c.json({ ok: false, error: message }, 500);
  }
});

evaluatedRoutes.get("/snapshots/:id", async (c) => {
  try {
    const snapshotId = c.req.param("id");
    const row = await c.env.CAPABILITY_DB.prepare(`
      SELECT payload_json, payload_sha256, created_at
      FROM evaluated_snapshots WHERE snapshot_id = ?
    `)
      .bind(snapshotId)
      .first<{
        payload_json: string;
        payload_sha256: string;
        created_at: number;
      }>();
    if (!row) return c.json({ ok: false, error: "snapshot not found" }, 404);
    return c.json({
      ok: true,
      snapshot_id: snapshotId,
      payload_sha256: row.payload_sha256,
      created_at: row.created_at,
      snapshot: JSON.parse(row.payload_json),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return c.json({ ok: false, error: message }, 500);
  }
});
