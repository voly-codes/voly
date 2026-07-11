"""Agent-side run report to a linked VOLY Cloud control plane (mocked HTTP)."""

from __future__ import annotations

import json

import pytest

from voly.cloud_link import build_report_body, report_run_event
from voly.config import CloudConfig, VOLYConfig
from voly.telemetry import TaskEvent, emit_event_from_config

_CLOUD_ENV_KEYS = (
    "VOLY_CLOUD_ENABLED",
    "VOLY_CLOUD_URL",
    "VOLY_CLOUD_TENANT_ID",
    "VOLY_CLOUD_TOKEN",
    "VOLY_CLOUD_USER_ID",
)


@pytest.fixture(autouse=True)
def _hermetic_cloud_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # .env is loaded into os.environ by unrelated tests — keep these hermetic.
    for key in _CLOUD_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _event(**overrides) -> TaskEvent:
    defaults = dict(
        task_id="run-1",
        agent="claude",
        status="completed",
        executor="claude-code",
        cost_usd=0.42,
        task_prompt="add health endpoint",
        report={
            "summary": "added /health",
            "files_changed": ["app.py"],
            "files_created": ["tests/test_health.py"],
            "files_deleted": [],
            "actions": [],
        },
    )
    defaults.update(overrides)
    return TaskEvent(**defaults)


def _linked_config() -> VOLYConfig:
    config = VOLYConfig()
    config.cloud = CloudConfig(
        enabled=True,
        base_url="http://cloud.test:7790/",
        tenant_id="t-abc",
        token="jwt-token",
        user_id="u-1",
    )
    return config


class _Resp:
    status = 201

    def read(self) -> bytes:
        return b'{"event":{}}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_build_report_body_maps_task_event_fields() -> None:
    body = build_report_body(_event(), user_id="u-1")
    assert body["run_id"] == "run-1"
    assert body["task"] == "add health endpoint"
    assert body["success"] is True
    assert body["status"] == "completed"
    assert body["executor"] == "claude-code"
    assert body["cost_usd"] == pytest.approx(0.42)
    assert body["files_touched"] == ["app.py", "tests/test_health.py"]
    assert body["summary"] == "added /health"
    assert body["user_id"] == "u-1"


def test_build_report_body_falls_back_to_result_and_task_id() -> None:
    event = _event(task_prompt=None, report=None, result="x" * 900, status="failed")
    body = build_report_body(event)
    assert body["task"] == "run-1"
    assert body["success"] is False
    assert len(body["summary"]) == 500
    assert body["files_touched"] == []
    assert body["user_id"] is None


def test_report_run_event_posts_tenant_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_urlopen(req, timeout=5.0):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("voly.cloud_link.urllib.request.urlopen", fake_urlopen)
    assert report_run_event(_event(), _linked_config()) is True
    assert captured["url"] == "http://cloud.test:7790/cloud/v1/tenants/t-abc/runs/report"
    assert captured["auth"] == "Bearer jwt-token"
    assert captured["body"]["run_id"] == "run-1"
    assert captured["body"]["user_id"] == "u-1"


def test_report_run_event_noop_when_disabled_or_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("no HTTP expected")

    monkeypatch.setattr("voly.cloud_link.urllib.request.urlopen", boom)

    assert report_run_event(_event(), None) is False
    assert report_run_event(_event(), VOLYConfig()) is False

    incomplete = _linked_config()
    incomplete.cloud.token = ""
    assert report_run_event(_event(), incomplete) is False


def test_report_run_event_swallows_delivery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    def fail(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("voly.cloud_link.urllib.request.urlopen", fail)
    assert report_run_event(_event(), _linked_config()) is False


def test_emit_event_from_config_reports_to_cloud(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_urlopen(req, timeout=5.0):
        calls.append(req.full_url)
        return _Resp()

    monkeypatch.setattr("voly.cloud_link.urllib.request.urlopen", fake_urlopen)
    monkeypatch.delenv("CF_R2_ENDPOINT", raising=False)
    monkeypatch.delenv("CF_PIPELINE_TELEMETRY_ENDPOINT", raising=False)
    monkeypatch.delenv("PIPELINE_TELEMETRY_ENDPOINT", raising=False)

    config = _linked_config()
    config.telemetry.events_dir = str(tmp_path / "events")
    config.telemetry.pipeline_url = ""
    config.telemetry.r2_enabled = False
    config.spend.enabled = False

    path = emit_event_from_config(_event(), config)
    assert path is not None and path.exists()
    assert calls == ["http://cloud.test:7790/cloud/v1/tenants/t-abc/runs/report"]


def test_parser_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.config._parser import _parse_config

    monkeypatch.setenv("VOLY_CLOUD_ENABLED", "1")
    monkeypatch.setenv("VOLY_CLOUD_URL", "http://cp:7790")
    monkeypatch.setenv("VOLY_CLOUD_TENANT_ID", "t-env")
    monkeypatch.setenv("VOLY_CLOUD_TOKEN", "tok-env")

    config = _parse_config({})
    assert config.cloud.enabled is True
    assert config.cloud.base_url == "http://cp:7790"
    assert config.cloud.tenant_id == "t-env"
    assert config.cloud.token == "tok-env"


def test_parser_yaml_section(monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.config._parser import _parse_config

    config = _parse_config(
        {
            "cloud": {
                "enabled": True,
                "base_url": "http://cp:7790",
                "tenant_id": "t-yaml",
                "token": "tok-yaml",
                "user_id": "u-yaml",
                "timeout_seconds": 2,
            }
        }
    )
    assert config.cloud.enabled is True
    assert config.cloud.tenant_id == "t-yaml"
    assert config.cloud.user_id == "u-yaml"
    assert config.cloud.timeout_seconds == pytest.approx(2.0)
