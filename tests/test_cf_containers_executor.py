"""PoC: CfContainersExecutor with mocked sandbox-spike HTTP."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from voly.executor.cf_containers import CfContainersExecutor


def test_is_available_false_on_connection_error() -> None:
    ex = CfContainersExecutor(base_url="http://127.0.0.1:1", token="t")
    with patch(
        "voly.executor.cf_containers.urllib.request.urlopen",
        side_effect=OSError("down"),
    ):
        assert ex.is_available() is False


def test_run_missing_token() -> None:
    ex = CfContainersExecutor(base_url="http://127.0.0.1:8791", token="")
    r = ex.run("probe")
    assert r.success is False
    assert "VOLY_CF_CONTAINERS_TOKEN" in (r.error or "")
    assert r.not_available is False


def test_run_not_available() -> None:
    ex = CfContainersExecutor(base_url="http://127.0.0.1:9", token="tok")
    with patch.object(ex, "is_available", return_value=False):
        r = ex.run("probe sandbox")
    assert r.success is False
    assert r.not_available is True
    assert "not reachable" in (r.error or "").lower()
    assert "sandbox-spike" in (r.error or "")


def test_run_probe_success() -> None:
    ex = CfContainersExecutor(base_url="http://127.0.0.1:8791", token="tok", mode="probe")
    body = {
        "success": True,
        "stub": False,
        "mode": "sandbox",
        "run_id": "run-1",
        "tenant_id": "t1",
        "probes": {"python": {"stdout": "4"}, "file_written": True},
    }
    with (
        patch.object(ex, "is_available", return_value=True),
        patch.object(ex, "_post_run", return_value=body),
    ):
        r = ex.run("probe sandbox")

    assert r.success is True
    assert r.session_id == "run-1"
    assert "probes" in r.output
    assert r.metadata.get("provider") == "cloudflare-containers"
    assert r.metadata.get("probes", {}).get("file_written") is True


def test_run_stub_receipt_counts_as_success() -> None:
    ex = CfContainersExecutor(token="tok")
    body = {
        "success": True,
        "stub": True,
        "mode": "stub-probe",
        "run_id": "stub-1",
        "note": "Docker + Sandbox binding next",
        "task": "hello",
    }
    with (
        patch.object(ex, "is_available", return_value=True),
        patch.object(ex, "_post_run", return_value=body),
    ):
        r = ex.run("hello")
    assert r.success is True
    assert "[stub]" in r.output
    assert r.metadata.get("stub") is True


def test_run_sandbox_error() -> None:
    ex = CfContainersExecutor(token="tok")
    body = {
        "success": False,
        "stub": True,
        "sandbox_error": "Container failed to start",
        "note": "check Docker",
    }
    with (
        patch.object(ex, "is_available", return_value=True),
        patch.object(ex, "_post_run", return_value=body),
    ):
        r = ex.run("task")
    assert r.success is False
    assert "Container failed to start" in (r.error or "")


def test_post_run_posts_json_with_auth() -> None:
    ex = CfContainersExecutor(
        base_url="http://example.test",
        token="jwt-tok",
        mode="claude-code",
        repo="https://github.com/acme/app.git",
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"success": true, "stub": true, "mode": "stub-claude-code"}'
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch(
        "voly.executor.cf_containers.urllib.request.urlopen",
        return_value=mock_resp,
    ) as urlopen:
        out = ex._post_run("do work", timeout=30)

    assert out["success"] is True
    req = urlopen.call_args[0][0]
    assert req.full_url.endswith("/runs")
    payload = json.loads(req.data.decode())
    assert payload["task"] == "do work"
    assert payload["mode"] == "claude-code"
    assert payload["repo"] == "https://github.com/acme/app.git"
    auth = req.get_header("Authorization") or ""
    assert "jwt-tok" in str(auth)


def test_build_executor_registers_cf_containers() -> None:
    from voly.runner.agent_runner import EXECUTOR_NAMES, _build_executor

    assert "cf-containers" in EXECUTOR_NAMES
    ex = _build_executor("cf-containers")
    assert ex.name == "cf-containers"


def test_format_hint_for_cf_containers() -> None:
    from voly.executor.base import ExecutorResult, format_executor_failure

    r = ExecutorResult(
        success=False,
        error="Cloudflare Containers Worker not reachable at http://127.0.0.1:8791",
        not_available=True,
    )
    msg = format_executor_failure(r, executor_name="cf-containers")
    assert "sandbox-spike" in msg
    assert "Hint:" in msg
