import { Hono } from "hono";
import type { AppBindings, RolePayload } from "../types";

export const rolesRoutes = new Hono<AppBindings>();

rolesRoutes.post("/sync", async (c) => {
  try {
    const body = await c.req.json<{ roles?: RolePayload[] }>();
    const roles = body.roles ?? [];
    const now = Date.now();
    let upserted = 0;

    const stmt = c.env.CAPABILITY_DB.prepare(`
      INSERT INTO roles (
        id, tier, mode, system_prompt, default_executor, provider_offset,
        inject_prior_context, decomposer_signals, capability_requirements, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        tier = excluded.tier,
        mode = excluded.mode,
        system_prompt = excluded.system_prompt,
        default_executor = excluded.default_executor,
        provider_offset = excluded.provider_offset,
        inject_prior_context = excluded.inject_prior_context,
        decomposer_signals = excluded.decomposer_signals,
        capability_requirements = excluded.capability_requirements,
        updated_at = excluded.updated_at
    `);

    for (const role of roles) {
      const id = String(role.id ?? "").trim();
      if (!id) continue;

      await stmt
        .bind(
          id,
          String(role.tier ?? ""),
          String(role.mode ?? ""),
          String(role.system_prompt ?? ""),
          String(role.default_executor ?? ""),
          Number(role.provider_offset ?? 0),
          role.inject_prior_context ? 1 : 0,
          JSON.stringify(role.decomposer_signals ?? []),
          JSON.stringify(role.capability_requirements ?? {}),
          now,
        )
        .run();
      upserted += 1;
    }

    return c.json({ ok: true, upserted });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});
