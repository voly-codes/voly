from __future__ import annotations

import json
from pathlib import Path

import pytest

from voly.capability import (
    CapabilityRunEvidence,
    EvaluatedPackStore,
    build_remote_snapshot,
    has_current_verified_receipt,
    sync_remote_snapshot,
)


def _store(tmp_path: Path) -> EvaluatedPackStore:
    store = EvaluatedPackStore(tmp_path / "evaluated")
    store.initialize()
    return store


def _evidence(run_id: str) -> CapabilityRunEvidence:
    return CapabilityRunEvidence(
        capability_id="tdd-workflow",
        executor_id="codex",
        run_id=run_id,
        completion=True,
        tests_passed=True,
        rollback=False,
        corrections=0,
        cost_usd=0,
        latency_ms=100,
        retries=0,
        reviewer_accepted=True,
        baseline_score=0.5,
        variant_score=0.7,
        changed_capabilities=["tdd-workflow"],
        cost_measured=False,
        baseline_latency_ms=100,
        tokens_measured=False,
    )


def test_snapshot_is_deterministic_bounded_and_contains_staged_hashes(tmp_path):
    store = _store(tmp_path)
    manifest = tmp_path / "packs/ecc-universal/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "components": [{
            "staged_path": "content/skills/tdd-workflow/SKILL.md",
            "sha256": "a" * 64,
            "status": "staged",
        }],
    }), encoding="utf-8")

    first = build_remote_snapshot(store, "codex", packs_root=tmp_path / "packs")
    second = build_remote_snapshot(store, "codex", packs_root=tmp_path / "packs")

    assert first == second
    assert len(first["snapshot_id"]) == 64
    tdd = next(
        item for item in first["packs"]
        if item["capability_id"] == "tdd-workflow"
    )
    assert tdd["provenance"]["instruction_hashes"] == {
        "content/skills/tdd-workflow/SKILL.md": "a" * 64,
    }
    serialized = json.dumps(first)
    assert "run_id" not in serialized
    assert "created_at" not in serialized


def test_sync_requires_exact_readback_before_writing_receipt(tmp_path, monkeypatch):
    store = _store(tmp_path)
    snapshot = build_remote_snapshot(store, "codex", packs_root=tmp_path / "packs")
    content = {
        "schema_version": snapshot["schema_version"],
        "executor_id": snapshot["executor_id"],
        "packs": snapshot["packs"],
    }

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(self.payload).encode()

    calls = []

    def urlopen(request, timeout):
        calls.append((request, timeout))
        assert request.headers["Authorization"] == "Bearer secret"
        assert request.headers["User-agent"] == "voly-capability-sync/1"
        if request.method == "POST":
            return Response({"ok": True, "snapshot_id": snapshot["snapshot_id"]})
        return Response({
            "ok": True,
            "snapshot_id": snapshot["snapshot_id"],
            "payload_sha256": snapshot["snapshot_id"],
            "snapshot": content,
        })

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    receipt_path = tmp_path / "receipt.json"

    receipt = sync_remote_snapshot(
        store,
        snapshot,
        worker_url="https://capability.example",
        token="secret",
        receipt_path=receipt_path,
    )

    assert receipt.verified is True
    assert len(calls) == 2
    assert has_current_verified_receipt(store, "codex", receipt_path) is True
    store.record(_evidence("new-run"))
    assert has_current_verified_receipt(store, "codex", receipt_path) is False


def test_sync_rejects_tampered_readback(tmp_path, monkeypatch):
    store = _store(tmp_path)
    snapshot = build_remote_snapshot(store, "codex", packs_root=tmp_path / "packs")

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(self.payload).encode()

    def urlopen(request, timeout):
        if request.method == "POST":
            return Response({"snapshot_id": snapshot["snapshot_id"]})
        return Response({
            "payload_sha256": snapshot["snapshot_id"],
            "snapshot": {"schema_version": 1, "executor_id": "tampered", "packs": []},
        })

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    receipt_path = tmp_path / "receipt.json"
    with pytest.raises(ValueError, match="read-back"):
        sync_remote_snapshot(
            store,
            snapshot,
            worker_url="https://capability.example",
            token="secret",
            receipt_path=receipt_path,
        )
    assert receipt_path.exists() is False
