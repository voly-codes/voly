"""Authenticated, deterministic sync of evaluated capability snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from voly.capability.evaluated_packs import (
    EvaluatedCapabilityPack,
    EvaluatedPackStore,
)
from voly.capability.validation import decide_capability

REMOTE_SYNC_SCHEMA_VERSION = 1
DEFAULT_REQUIRED_SAMPLES = 6


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_numbers(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_numbers(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def _store_state_hash(store: EvaluatedPackStore) -> str:
    digest = hashlib.sha256()
    for path in (store.packs_path, store.evidence_path):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"")
        digest.update(b"\0")
    return digest.hexdigest()


def _manifest_hashes(
    pack: EvaluatedCapabilityPack,
    *,
    packs_root: Path,
) -> dict[str, str]:
    source_pack_id = pack.source_pack_id
    manifest_path = packs_root / source_pack_id / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components = {
        str(item.get("staged_path")): str(item.get("sha256"))
        for item in manifest.get("components", [])
        if item.get("status") == "staged"
    }
    return {
        source: components[source]
        for source in pack.instruction_sources
        if source in components
    }


def _definition(pack: EvaluatedCapabilityPack) -> dict[str, Any]:
    data = dict(pack.to_dict())
    data.pop("state", None)
    data.pop("evidence_count", None)
    return data


def build_remote_snapshot(
    store: EvaluatedPackStore,
    executor_id: str,
    *,
    packs_root: str | Path = ".voly/capability/packs",
    additional_hashes: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a bounded canonical snapshot without raw prompts or evidence."""
    packs = sorted(store.load_packs(), key=lambda item: item.capability_id)
    if len(packs) > 32:
        raise ValueError("remote snapshot supports at most 32 packs")
    extra = additional_hashes or {}
    items = []
    for pack in packs:
        decision = decide_capability(
            store,
            pack.capability_id,
            executor_id,
            required_samples=DEFAULT_REQUIRED_SAMPLES,
        )
        metrics = store.metrics(pack.capability_id, executor_id)
        definition = _definition(pack)
        instruction_hashes = _manifest_hashes(
            pack,
            packs_root=Path(packs_root),
        )
        instruction_hashes.update(extra.get(pack.capability_id, {}))
        if len(instruction_hashes) > 64:
            raise ValueError("remote snapshot supports at most 64 provenance hashes")
        for name, value in instruction_hashes.items():
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"invalid provenance hash: {name}")
        items.append({
            "capability_id": pack.capability_id,
            "version": pack.version,
            "state": pack.state.value,
            "definition_hash": _sha256(_canonical(definition)),
            "definition": definition,
            "provenance": {
                "source_pack_id": pack.source_pack_id,
                "instruction_hashes": dict(sorted(instruction_hashes.items())),
            },
            "decision": asdict(decision),
            "metrics": asdict(metrics),
        })
    content = _normalize_numbers({
        "schema_version": REMOTE_SYNC_SCHEMA_VERSION,
        "executor_id": executor_id,
        "packs": items,
    })
    return {"snapshot_id": _sha256(_canonical(content)), **content}


@dataclass(frozen=True)
class RemoteSyncReceipt:
    schema_version: int
    snapshot_id: str
    executor_id: str
    worker_url: str
    store_state_hash: str
    verified: bool


def _request_json(
    request: urllib.request.Request,
    *,
    timeout: float,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"remote sync HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"remote sync unavailable: {exc}") from exc


def sync_remote_snapshot(
    store: EvaluatedPackStore,
    snapshot: dict[str, Any],
    *,
    worker_url: str,
    token: str,
    receipt_path: str | Path,
    timeout: float = 15,
) -> RemoteSyncReceipt:
    """Upload once, read back, verify exact canonical content, then receipt."""
    if not worker_url.strip():
        raise ValueError("capability worker URL is required")
    if not token:
        raise ValueError("VOLY_CAPABILITY_SYNC_TOKEN is required")
    base = worker_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    upload = urllib.request.Request(
        f"{base}/evaluated/snapshots",
        data=_canonical(snapshot).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    uploaded = _request_json(upload, timeout=timeout)
    if uploaded.get("snapshot_id") != snapshot["snapshot_id"]:
        raise ValueError("remote upload returned a different snapshot")

    readback = urllib.request.Request(
        f"{base}/evaluated/snapshots/{snapshot['snapshot_id']}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    remote = _request_json(readback, timeout=timeout)
    content = {
        "schema_version": snapshot["schema_version"],
        "executor_id": snapshot["executor_id"],
        "packs": snapshot["packs"],
    }
    if (
        remote.get("payload_sha256") != snapshot["snapshot_id"]
        or remote.get("snapshot") != content
    ):
        raise ValueError("remote read-back verification failed")

    receipt = RemoteSyncReceipt(
        schema_version=REMOTE_SYNC_SCHEMA_VERSION,
        snapshot_id=snapshot["snapshot_id"],
        executor_id=snapshot["executor_id"],
        worker_url=base,
        store_state_hash=_store_state_hash(store),
        verified=True,
    )
    path = Path(receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(receipt), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return receipt


def has_current_verified_receipt(
    store: EvaluatedPackStore,
    executor_id: str,
    receipt_path: str | Path,
) -> bool:
    path = Path(receipt_path)
    if not path.is_file():
        return False
    try:
        receipt = RemoteSyncReceipt(**json.loads(path.read_text(encoding="utf-8")))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        receipt.schema_version == REMOTE_SYNC_SCHEMA_VERSION
        and receipt.executor_id == executor_id
        and receipt.verified
        and receipt.store_state_hash == _store_state_hash(store)
    )


def sync_token_from_env() -> str:
    return os.getenv("VOLY_CAPABILITY_SYNC_TOKEN", "")
