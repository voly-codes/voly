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
def _hermetic_cloud_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # .env is loaded into os.environ by unrelated tests — keep these hermetic.
    for key in _CLOUD_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Point the device-link file away from the repo's real .voly/.
    monkeypatch.setenv("VOLY_CLOUD_LINK_FILE", str(tmp_path / "cloud-link.json"))


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


# --- device link file + voly cloud CLI -------------------------------------


def test_link_file_roundtrip(tmp_path) -> None:
    from voly.cloud_link import delete_link_file, link_file_path, read_link_file, save_link_file

    assert read_link_file() is None
    path = save_link_file({"base_url": "http://cp:7790", "tenant_id": "t-1", "token": "tok"})
    assert path == link_file_path()
    link = read_link_file()
    assert link is not None and link["tenant_id"] == "t-1"
    assert delete_link_file() is True
    assert read_link_file() is None


def test_report_falls_back_to_link_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.cloud_link import save_link_file

    save_link_file(
        {"base_url": "http://cp:7790/", "tenant_id": "t-link", "token": "tok-link", "user_id": "u-9"}
    )
    captured: dict = {}

    def fake_urlopen(req, timeout=5.0):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr("voly.cloud_link.urllib.request.urlopen", fake_urlopen)
    # config has cloud disabled — the login link file should drive the report
    assert report_run_event(_event(), VOLYConfig()) is True
    assert captured["url"] == "http://cp:7790/cloud/v1/tenants/t-link/runs/report"
    assert captured["auth"] == "Bearer tok-link"
    assert captured["body"]["user_id"] == "u-9"


def test_explicit_config_wins_over_link_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.cloud_link import resolve_cloud_link, save_link_file

    save_link_file({"base_url": "http://file:1", "tenant_id": "t-file", "token": "tok-file"})
    link = resolve_cloud_link(_linked_config())
    assert link is not None and link["tenant_id"] == "t-abc"


def _cli_responses(url: str) -> dict:
    if url.endswith("/users/login"):
        return {"access_token": "user-tok", "user": {"id": "u-1"}}
    if url.endswith("/users/me"):
        return {
            "user": {"id": "u-1"},
            "organizations": [{"tenant_id": "t-cli", "slug": "cliorg", "role": "owner"}],
        }
    if "/devices" in url and not url.endswith("/heartbeat"):
        return {
            "device": {"id": "dev-1", "tenant_id": "t-cli", "user_id": "u-1", "name": "host"},
            "device_token": {"access_token": "tenant-tok", "expires_in": 2592000},
        }
    if url.endswith("/tokens"):
        return {"access_token": "tenant-tok", "expires_in": 2592000}
    raise AssertionError(f"unexpected url {url}")


def test_cli_cloud_login_status_logout(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    from voly.cli.commands.cloud_cmd import cloud
    from voly.cloud_link import read_link_file

    class _CliResp:
        def __init__(self, body: dict, status: int = 200):
            self._body = body
            self.status = status

        def read(self) -> bytes:
            return json.dumps(self._body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured_tokens: list[str] = []

    def fake_urlopen(req, timeout=15.0):
        auth = req.get_header("Authorization") or ""
        captured_tokens.append(auth)
        body = _cli_responses(req.full_url)
        return _CliResp(body, status=201 if "/devices" in req.full_url else 200)

    monkeypatch.setattr("voly.cli.commands.cloud_cmd.urllib.request.urlopen", fake_urlopen)

    runner = CliRunner()
    result = runner.invoke(
        cloud,
        ["login", "--url", "http://cp:7790", "--email", "a@b.co", "--password", "hunter2pass"],
    )
    assert result.exit_code == 0, result.output
    assert "cliorg" in result.output

    link = read_link_file()
    assert link is not None
    assert link["tenant_id"] == "t-cli"
    assert link["token"] == "tenant-tok"
    assert link["device_id"] == "dev-1"
    assert "Bearer user-tok" in captured_tokens

    result = runner.invoke(cloud, ["status"])
    assert result.exit_code == 0, result.output
    assert "cliorg" in result.output
    assert "dev-1" in result.output

    result = runner.invoke(cloud, ["logout"])
    assert result.exit_code == 0
    assert read_link_file() is None

    result = runner.invoke(cloud, ["status"])
    assert result.exit_code == 1


def test_cli_device_code_login(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    from voly.cli.commands.cloud_cmd import cloud
    from voly.cloud_link import read_link_file

    class _CliResp:
        def __init__(self, body: dict, status: int = 200):
            self._body = body
            self.status = status

        def read(self) -> bytes:
            return json.dumps(self._body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    polls = {"n": 0}

    def fake_urlopen(req, timeout=15.0):
        url = req.full_url
        if url.endswith("/device-auth/start"):
            return _CliResp(
                {
                    "device_code": "dc",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "http://dash/link",
                    "verification_uri_complete": "http://dash/link?code=ABCD-EFGH",
                    "interval": 1,
                    "expires_in": 600,
                }
            )
        if url.endswith("/device-auth/poll"):
            polls["n"] += 1
            if polls["n"] < 2:
                import urllib.error
                from io import BytesIO

                raise urllib.error.HTTPError(
                    url, 400, "pending", hdrs=None, fp=BytesIO(b'{"detail":"authorization_pending"}')
                )
            return _CliResp(
                {
                    "device": {"id": "dev-2", "tenant_id": "t-2"},
                    "device_token": {"access_token": "edge-2"},
                    "tenant_id": "t-2",
                    "tenant_slug": "acme",
                    "user_id": "u-2",
                    "user_email": "a@b.co",
                }
            )
        raise AssertionError(url)

    monkeypatch.setattr("voly.cli.commands.cloud_cmd.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("voly.cli.commands.cloud_cmd.time.sleep", lambda *_: None)
    monkeypatch.setattr("voly.cli.commands.cloud_cmd.webbrowser.open", lambda *_: True)

    runner = CliRunner()
    result = runner.invoke(cloud, ["login", "--url", "http://cp:7790", "--no-browser"])
    assert result.exit_code == 0, result.output
    link = read_link_file()
    assert link is not None
    assert link["device_id"] == "dev-2"
    assert link["token"] == "edge-2"
    assert link["tenant_slug"] == "acme"


def test_send_heartbeat_and_sync(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.cloud_link import save_link_file, send_heartbeat, sync_local_events
    from voly.telemetry import TaskEvent

    save_link_file(
        {
            "base_url": "http://cp:7790",
            "tenant_id": "t-1",
            "token": "tok",
            "device_id": "dev-9",
            "user_id": "u-1",
        }
    )
    urls: list[str] = []

    def fake_urlopen(req, timeout=5.0):
        urls.append(req.full_url)
        return _Resp()

    monkeypatch.setattr("voly.cloud_link.urllib.request.urlopen", fake_urlopen)
    assert send_heartbeat() is True
    assert any("/devices/dev-9/heartbeat" in u for u in urls)

    events_dir = tmp_path / "events"
    events_dir.mkdir()
    ev = TaskEvent(task_id="past-1", agent="a", status="completed", task_prompt="old", cost_usd=0.1)
    (events_dir / "past-1.json").write_text(ev.to_json(), encoding="utf-8")
    urls.clear()
    result = sync_local_events(None, since_days=30, limit=10, events_dir=events_dir)
    assert result["synced"] == 1
    assert any("/runs/report" in u for u in urls)
