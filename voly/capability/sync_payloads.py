"""Seed YAML → CF Worker ProfilePayload conversion."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("voly.capability.sync_payloads")

_PACKAGE_SEEDS_DIR = Path(__file__).resolve().parent / "seeds"
_OP_KEYS = (
    "avg_latency_ms",
    "completion_rate",
    "retry_rate",
    "cost_per_task_usd",
    "total_runs",
)


def seed_file_to_payload(path: Path) -> dict[str, Any] | None:
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        _log.debug("seed read failed %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    executor_id = str(data.get("id") or "").strip()
    if not executor_id:
        return None
    caps: dict[str, Any] = {}
    for dim, raw in (data.get("capabilities") or {}).items():
        if not isinstance(raw, dict):
            continue
        cap: dict[str, Any] = {"score": float(raw.get("score", 0.5))}
        if "confidence" in raw:
            cap["confidence"] = float(raw["confidence"])
        if raw.get("sub_scores"):
            cap["sub_scores"] = {k: float(v) for k, v in raw["sub_scores"].items()}
        if raw.get("strengths"):
            cap["strengths"] = [str(s) for s in raw["strengths"]]
        if raw.get("weaknesses"):
            cap["weaknesses"] = [str(w) for w in raw["weaknesses"]]
        caps[str(dim)] = cap
    payload: dict[str, Any] = {
        "executor_id": executor_id,
        "kind": str(data.get("kind") or "executor"),
        "capabilities": caps,
        "constraints": dict(data.get("constraints") or {}),
    }
    op = data.get("operational")
    if isinstance(op, dict) and op:
        payload["operational"] = {k: float(op[k]) for k in _OP_KEYS if k in op}
    return payload


def load_seed_payloads(seeds_dir: str | None) -> list[dict[str, Any]]:
    directory = Path(seeds_dir) if seeds_dir else _PACKAGE_SEEDS_DIR
    if not directory.is_dir():
        return []
    profiles: list[dict[str, Any]] = []
    for pattern in ("*.yaml", "*.yml"):
        for path in sorted(directory.glob(pattern)):
            payload = seed_file_to_payload(path)
            if payload:
                profiles.append(payload)
    return profiles
