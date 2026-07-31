from __future__ import annotations

import json
import time

import pytest

import voly.hooks.runtime as runtime
from voly.hooks import (
    HookAdapter,
    HookEvent,
    HookEventType,
    HookManifest,
    HookRegistry,
)


def _manifest(
    hook_id: str = "observe-1",
    handler: str = "observe",
    permissions: list[str] | None = None,
    *,
    fail_policy: str = "fail_open",
    timeout: float = 1,
) -> dict:
    return {
        "hook_id": hook_id,
        "handler": handler,
        "events": ["run_started"],
        "permissions": permissions or ["observe"],
        "timeout_seconds": timeout,
        "idempotency": "run-event-v1",
        "fail_policy": fail_policy,
        "enabled": True,
    }


def _adapter(tmp_path, registry):
    return HookAdapter(
        registry,
        state_path=tmp_path / "state.json",
        evidence_log=tmp_path / "evidence.jsonl",
        telemetry_log=tmp_path / "telemetry.jsonl",
    )


def _event(tmp_path, payload=None):
    return HookEvent(
        HookEventType.RUN_STARTED,
        run_id="run-1",
        project_id="project-a",
        cwd=str(tmp_path),
        payload=payload or {},
        event_id="event-1",
    )


def test_manifest_requires_safety_contract():
    with pytest.raises(ValueError, match="missing required"):
        HookManifest.from_dict({"hook_id": "bad"})
    with pytest.raises(ValueError, match="timeout"):
        HookManifest.from_dict(_manifest(timeout=0))


def test_imported_hook_is_disabled_until_approved(tmp_path):
    registry = HookRegistry(tmp_path / "manifests.json")
    imported = registry.import_manifest(_manifest())

    assert imported.imported is True
    assert imported.enabled is False
    assert _adapter(tmp_path, registry).dispatch(_event(tmp_path)) == []

    registry.approve(imported.hook_id)
    result = _adapter(tmp_path, registry).dispatch(_event(tmp_path))
    assert result[0].status == "completed"


def test_idempotency_and_automatic_audit_logs(tmp_path):
    registry = HookRegistry(tmp_path / "manifests.json")
    registry.import_manifest(_manifest())
    registry.approve("observe-1")
    adapter = _adapter(tmp_path, registry)

    first = adapter.dispatch(_event(tmp_path))
    second = adapter.dispatch(_event(tmp_path))

    assert first[0].status == "completed"
    assert second[0].status == "duplicate"
    assert len((tmp_path / "evidence.jsonl").read_text().splitlines()) == 2
    assert len((tmp_path / "telemetry.jsonl").read_text().splitlines()) == 2


def test_permission_denial_respects_fail_policy(tmp_path):
    registry = HookRegistry(tmp_path / "manifests.json")
    registry.import_manifest(_manifest(
        handler="secret_scan",
        permissions=["read_project"],
        fail_policy="fail_closed",
    ))
    registry.approve("observe-1")

    result = _adapter(tmp_path, registry).dispatch(_event(tmp_path))

    assert result[0].status == "blocked"
    assert result[0].proceed is False


def test_failing_hook_does_not_mutate_event_or_stop_other_hooks(tmp_path):
    payload = {"changed_files": ["voly/code.py"]}
    registry = HookRegistry(tmp_path / "manifests.json")
    registry.import_manifest(_manifest(
        "docs",
        "docs_check",
        ["read_project", "read_docs"],
        fail_policy="fail_closed",
    ))
    registry.import_manifest(_manifest("observe"))
    registry.approve("docs")
    registry.approve("observe")

    results = _adapter(tmp_path, registry).dispatch(_event(tmp_path, payload))

    assert [item.status for item in results] == ["failed", "completed"]
    assert results[0].proceed is False
    assert payload == {"changed_files": ["voly/code.py"]}


def test_timeout_is_bounded_and_fail_open(monkeypatch, tmp_path):
    def slow(_event):
        time.sleep(0.1)
        return {}

    monkeypatch.setitem(runtime._HANDLERS, "observe", slow)
    registry = HookRegistry(tmp_path / "manifests.json")
    registry.import_manifest(_manifest(timeout=0.01))
    registry.approve("observe-1")

    started = time.monotonic()
    result = _adapter(tmp_path, registry).dispatch(_event(tmp_path))[0]

    assert result.status == "timeout"
    assert result.proceed is True
    assert time.monotonic() - started < 0.08


def test_secret_scan_and_docs_check_builtins(tmp_path):
    source = tmp_path / "app.py"
    source.write_text('API_KEY="abcdefghijklmnop"\n', encoding="utf-8")
    registry = HookRegistry(tmp_path / "manifests.json")
    secret = _manifest(
        "secret",
        "secret_scan",
        ["read_project", "scan_secrets"],
        fail_policy="fail_closed",
    )
    registry.import_manifest(secret)
    registry.approve("secret")

    result = _adapter(tmp_path, registry).dispatch(
        _event(tmp_path, {"changed_files": ["app.py"]})
    )[0]

    assert result.status == "failed"
    assert result.proceed is False
    audit = json.loads((tmp_path / "evidence.jsonl").read_text().splitlines()[0])
    assert audit["hook_id"] == "secret"


def test_scoped_tests_reject_non_test_executable(tmp_path):
    registry = HookRegistry(tmp_path / "manifests.json")
    registry.import_manifest(_manifest(
        "tests",
        "scoped_tests",
        ["execute_tests"],
        fail_policy="fail_closed",
    ))
    registry.approve("tests")

    result = _adapter(tmp_path, registry).dispatch(
        _event(tmp_path, {"test_argv": ["powershell", "-Command", "echo unsafe"]})
    )[0]

    assert result.status == "failed"
    assert "not allowlisted" in result.error
    assert result.proceed is False
