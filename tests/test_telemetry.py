"""Tests for telemetry — CF Pipelines delivery and local fallback."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voly.config import CloudAnalyticsConfig, TelemetryConfig, VOLYConfig
from voly.telemetry import (
    TaskEvent,
    TelemetryDeliveryError,
    TokenMetrics,
    _emit_to_r2,
    emit_event,
    emit_event_from_config,
    event_to_pipeline_record,
    resolve_pipeline_endpoint,
    send_to_pipeline,
)


def test_resolve_pipeline_endpoint_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_PIPELINE_TELEMETRY_ENDPOINT", raising=False)
    assert resolve_pipeline_endpoint("") == ""

    monkeypatch.setenv("CF_PIPELINE_TELEMETRY_ENDPOINT", "https://pipe.example.com/ingest")
    assert resolve_pipeline_endpoint("") == "https://pipe.example.com/ingest"
    assert resolve_pipeline_endpoint("${CF_PIPELINE_TELEMETRY_ENDPOINT}") == (
        "https://pipe.example.com/ingest"
    )


def test_event_to_pipeline_record_flattens_tokens() -> None:
    event = TaskEvent(
        task_id="t1",
        agent="developer",
        status="completed",
        tokens=TokenMetrics(input=100, output=50, saved_rtk=10),
        cost_usd=0.01,
        gateway=__import__("voly.telemetry", fromlist=["GatewayMetrics"]).GatewayMetrics(
            cache_hit=True
        ),
    )
    record = event_to_pipeline_record(event)
    assert record["tokens_input"] == 100
    assert record["tokens_output"] == 50
    assert record["tokens_saved_rtk"] == 10
    assert record["cache_hit"] is True
    assert "ts_us" in record
    assert len(record["event_id"]) == 64
    assert "task_id" not in record


def test_send_to_pipeline_posts_json_array() -> None:
    event = TaskEvent(
        task_id="t2",
        agent="cursor",
        status="completed",
        task_prompt="private task",
        result="private result",
        error="private error",
        report={"files_changed": ["secret/path.py"]},
    )
    captured: dict = {}

    def fake_urlopen(req, timeout=5):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.headers)
        resp = MagicMock()
        resp.read.return_value = b"{}"
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        send_to_pipeline("https://pipe.example.com/ingest", event, token="test-token")

    payload = json.loads(captured["data"].decode())
    assert isinstance(payload, list)
    assert payload[0]["event_id"] != "t2"
    serialized = json.dumps(payload)
    assert "private task" not in serialized
    assert "private result" not in serialized
    assert "private error" not in serialized
    assert "secret/path.py" not in serialized
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["authorization"] == "Bearer test-token"
    assert "user-agent" in headers


def test_emit_event_writes_local_and_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = TaskEvent(task_id="local-1", agent="test", status="completed")
    sent: list[TaskEvent] = []

    def fake_send(endpoint, ev, **kwargs):
        sent.append(ev)

    monkeypatch.setattr("voly.telemetry.send_to_pipeline", fake_send)

    path = emit_event(
        event,
        events_dir=tmp_path,
        pipeline_url="https://pipe.example.com/ingest",
        remote_analytics_enabled=True,
    )

    assert path is not None
    assert path.exists()
    assert json.loads(path.read_text())["task_id"] == "local-1"
    assert len(sent) == 1


def test_emit_event_pipeline_failure_still_writes_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = TaskEvent(task_id="local-2", agent="test", status="completed")

    def fail_send(*args, **kwargs):
        raise TelemetryDeliveryError("network down")

    monkeypatch.setattr("voly.telemetry.send_to_pipeline", fail_send)

    path = emit_event(
        event,
        events_dir=tmp_path,
        pipeline_url="https://pipe.example.com/ingest",
        remote_analytics_enabled=True,
    )
    assert path is not None
    assert path.exists()


def test_emit_event_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = VOLYConfig(
        telemetry=TelemetryConfig(
            events_dir=str(tmp_path),
            pipeline_url="https://pipe.example.com/ingest",
            r2_enabled=False,
        ),
        cloud_analytics=CloudAnalyticsConfig(enabled=True),
    )
    sent: list[str] = []

    def fake_send(endpoint, ev, **kwargs):
        sent.append(endpoint)

    monkeypatch.setattr("voly.telemetry.send_to_pipeline", fake_send)

    emit_event_from_config(
        TaskEvent(task_id="cfg-1", agent="dev", status="completed"),
        config,
    )
    assert sent == ["https://pipe.example.com/ingest"]
    assert (tmp_path / "cfg-1.json").exists()


def test_emit_event_from_config_requires_explicit_remote_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = VOLYConfig(
        telemetry=TelemetryConfig(
            events_dir=str(tmp_path),
            pipeline_url="https://pipe.example.com/ingest",
            r2_enabled=False,
        ),
    )
    sent: list[str] = []
    monkeypatch.setattr(
        "voly.telemetry.send_to_pipeline",
        lambda endpoint, *_args, **_kwargs: sent.append(endpoint),
    )

    emit_event_from_config(
        TaskEvent(task_id="private-local", agent="dev", status="completed"),
        config,
    )

    assert sent == []
    assert (tmp_path / "private-local.json").exists()


def test_r2_upload_uses_sanitized_record(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _FakeR2:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def put(self, bucket, key, body, content_type) -> None:
            captured.update(
                bucket=bucket,
                key=key,
                body=json.loads(body.decode("utf-8")),
                content_type=content_type,
            )

    monkeypatch.setattr("voly.cloudflare.r2.R2Client", _FakeR2)
    event = TaskEvent(
        task_id="raw-id",
        agent="dev",
        status="completed",
        task_prompt="private task",
        result="private result",
        report={"files_changed": ["customer/repo.py"]},
    )

    _emit_to_r2(event, "https://r2.test", "bucket", "key", "secret")

    assert captured["key"].startswith("events/")
    serialized = json.dumps(captured["body"])
    assert "raw-id" not in serialized
    assert "private task" not in serialized
    assert "private result" not in serialized
    assert "customer/repo.py" not in serialized


def test_telemetry_cli_consent_gate() -> None:
    from click.testing import CliRunner

    from voly.cli.commands.telemetry import telemetry

    config = VOLYConfig(
        telemetry=TelemetryConfig(
            pipeline_url="https://pipe.example.com/ingest",
            r2_enabled=False,
        )
    )
    runner = CliRunner()

    status = runner.invoke(telemetry, ["status"], obj={"config": config})
    assert status.exit_code == 0
    assert "Remote consent: disabled" in status.output

    dry_run = runner.invoke(telemetry, ["test", "--dry-run"], obj={"config": config})
    assert dry_run.exit_code == 0

    send = runner.invoke(telemetry, ["test"], obj={"config": config})
    assert send.exit_code == 1
    assert "consent is disabled" in send.output


def test_config_loads_telemetry_pipeline_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.config import load_config

    monkeypatch.setenv("CF_PIPELINE_TELEMETRY_ENDPOINT", "https://env-pipe.example.com")
    cfg_path = tmp_path / "voly.yaml"
    cfg_path.write_text("""
telemetry:
  pipeline_url: "${CF_PIPELINE_TELEMETRY_ENDPOINT}"
""")
    cfg = load_config(cfg_path)
    assert cfg.telemetry.pipeline_url == "https://env-pipe.example.com"
