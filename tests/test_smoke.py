"""
Smoke tests — проверяют что все модули импортируются и CLI-команды
отвечают без исключений. Не требуют сети или внешних сервисов.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from codeops.cli.main import main


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


def test_import_a2a() -> None:
    import codeops.a2a  # noqa: F401


def test_import_agui() -> None:
    import codeops.agui  # noqa: F401


def test_import_ai_gateway() -> None:
    import codeops.ai_gateway  # noqa: F401


def test_import_memory() -> None:
    import codeops.memory  # noqa: F401


def test_import_model_router() -> None:
    import codeops.model_router  # noqa: F401


def test_import_registry() -> None:
    import codeops.registry  # noqa: F401
    import codeops.registry.agents  # noqa: F401
    import codeops.registry.skills  # noqa: F401


def test_import_scanner() -> None:
    import codeops.scanner  # noqa: F401


def test_import_workflow() -> None:
    import codeops.workflow  # noqa: F401


def test_import_pipeline() -> None:
    import codeops.pipeline  # noqa: F401


def test_import_telemetry() -> None:
    import codeops.telemetry  # noqa: F401


def test_import_config() -> None:
    from codeops.config import load_config, VOLYConfig

    cfg = load_config()
    assert isinstance(cfg, VOLYConfig)


# ---------------------------------------------------------------------------
# CLI smoke tests (no network, no side effects)
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Create a minimal codeops.yaml in a temp directory."""
    from codeops.config import create_default_config

    cfg_path = tmp_path / "codeops.yaml"
    create_default_config(cfg_path)
    return cfg_path


def test_cli_help(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "codeops" in result.output.lower()


def test_cli_version(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_init(runner: CliRunner, tmp_path: Path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["init", "--force"])
        assert result.exit_code == 0
        assert "codeops.yaml" in result.output.lower() or "config" in result.output.lower()


def test_cli_init_no_overwrite(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "init"])
    assert result.exit_code == 0
    assert "force" in result.output.lower() or "exists" in result.output.lower()


def test_cli_status(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "status"])
    assert result.exit_code == 0
    assert len(result.output) > 0


def test_cli_scan(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "scan"])
    assert result.exit_code == 0


def test_cli_registry_agents(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "registry", "agents"])
    assert result.exit_code == 0


def test_cli_registry_skills(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "registry", "skills"])
    assert result.exit_code == 0


def test_cli_workflow_list(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "workflow", "list"])
    assert result.exit_code == 0
    assert len(result.output) > 0


def test_cli_model_list(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "model", "list"])
    assert result.exit_code == 0
    assert "anthropic" in result.output.lower() or "claude" in result.output.lower()


def test_cli_model_route(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "model", "route", "write unit tests"])
    assert result.exit_code == 0
    assert "model" in result.output.lower()


def test_cli_match(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "match", "fix a bug in the API"])
    assert result.exit_code == 0
    assert "agent" in result.output.lower()


def test_cli_ai_gateway_status(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "ai-gateway", "status"])
    assert result.exit_code == 0
    assert "gateway" in result.output.lower() or "cloudflare" in result.output.lower()


def test_cli_mcp_list(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "mcp", "list"])
    assert result.exit_code == 0


def test_cli_mcp_config(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "mcp", "config"])
    assert result.exit_code == 0
    # Should output valid JSON
    try:
        json.loads(result.output)
    except json.JSONDecodeError:
        pytest.fail(f"mcp config output is not valid JSON:\n{result.output}")


def test_cli_memory_list(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "memory", "list"])
    assert result.exit_code == 0


def test_cli_a2a_list(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "a2a", "list"])
    assert result.exit_code == 0


def test_cli_rtk_stats(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "rtk", "stats"])
    # Passes when RTK is installed; acceptable to fail with "not found" when it isn't
    if result.exit_code != 0:
        assert "rtk" in result.output.lower() or (result.exception and "rtk" in str(result.exception).lower())


def test_cli_workflow_status(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "workflow", "status"])
    assert result.exit_code == 0


def test_cli_config_show(runner: CliRunner, tmp_config: Path) -> None:
    result = runner.invoke(main, ["--config", str(tmp_config), "config", "--show"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Installability smoke test
# ---------------------------------------------------------------------------


def test_all_submodules_importable() -> None:
    """Verify every declared package can be imported — catches missing __init__.py."""
    packages = [
        "codeops",
        "codeops.cli",
        "codeops.models",
        "codeops.memory",
        "codeops.tools",
        "codeops.rtk",
        "codeops.headroom",
        "codeops.a2a",
        "codeops.agui",
        "codeops.ai_gateway",
        "codeops.scanner",
        "codeops.workflow",
        "codeops.registry",
        "codeops.model_router",
        "codeops.pipeline",
    ]
    import importlib

    for pkg in packages:
        try:
            importlib.import_module(pkg)
        except ImportError as e:
            pytest.fail(f"Failed to import {pkg}: {e}")


# ---------------------------------------------------------------------------
# Telemetry unit tests
# ---------------------------------------------------------------------------


def test_telemetry_event_roundtrip(tmp_path: Path) -> None:
    from codeops.telemetry import (
        GatewayMetrics,
        TaskEvent,
        TokenMetrics,
        emit_event,
        load_events,
        new_task_id,
    )

    ev = TaskEvent(
        task_id=new_task_id(),
        agent="developer",
        status="completed",
        tokens=TokenMetrics(input=1000, output=200, saved_rtk=400, saved_headroom=800),
        gateway=GatewayMetrics(cache_hit=True, fallback_used=False, dlp_blocked=False),
        skill_ids=["skill-nextjs", "skill-docker"],
        routing_score=0.87,
        cost_usd=0.006,
        duration_ms=1234.5,
        model="claude-sonnet-4-6",
        provider="anthropic",
    )

    path = emit_event(ev, tmp_path)
    assert path is not None and path.exists()

    events = load_events(tmp_path)
    assert len(events) == 1
    loaded = events[0]
    assert loaded.task_id == ev.task_id
    assert loaded.agent == "developer"
    assert loaded.status == "completed"
    assert loaded.tokens.input == 1000
    assert loaded.tokens.saved_rtk == 400
    assert loaded.tokens.total_saved == 1200
    assert loaded.gateway.cache_hit is True
    assert loaded.skill_ids == ["skill-nextjs", "skill-docker"]
    assert loaded.routing_score == pytest.approx(0.87)


def test_telemetry_cost_estimate() -> None:
    from codeops.telemetry import _estimate_cost

    # claude-sonnet-4-6: $3/$15 per 1M tokens
    cost = _estimate_cost("claude-sonnet-4-6", 1_000_000, 0)
    assert cost == pytest.approx(3.0, rel=0.01)

    cost = _estimate_cost("claude-sonnet-4-6", 0, 1_000_000)
    assert cost == pytest.approx(15.0, rel=0.01)

    # Unknown model falls back to default rate
    cost = _estimate_cost("unknown-model-xyz", 1000, 500)
    assert cost > 0


def test_telemetry_new_task_id_unique() -> None:
    from codeops.telemetry import new_task_id

    ids = {new_task_id() for _ in range(100)}
    assert len(ids) == 100  # all unique UUIDs
