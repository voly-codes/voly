"""Tests for VOLY config module."""

import os
import tempfile
from pathlib import Path

from voly.config import (
    VOLYConfig,
    RTKConfig,
    HeadroomConfig,
    PxpipeConfig,
    MemoryConfig,
    A2AConfig,
    AGUIConfig,
    ModelConfig,
    AgentConfig,
    create_default_config,
    load_config,
)


def test_default_config() -> None:
    cfg = VOLYConfig()
    assert cfg.default_model == "claude-sonnet"
    assert cfg.default_agent == "claude"
    assert cfg.rtk.enabled is True
    assert cfg.headroom.enabled is True
    assert cfg.pxpipe.enabled is False
    assert cfg.a2a.enabled is True
    assert cfg.agui.enabled is True


def test_create_default_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "voly.yaml"
        create_default_config(path)
        assert path.exists()
        content = path.read_text()
        assert "default_model: claude-sonnet" in content
        assert "default_agent: claude" in content
        assert "rtk:" in content
        assert "headroom:" in content
        assert "pxpipe:" in content
        assert "a2a:" in content
        assert "agui:" in content


def test_load_config_from_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "voly.yaml"
        path.write_text("""
default_model: gpt-4o
default_agent: my-agent
rtk:
  enabled: false
  binary_path: /usr/local/bin/rtk
headroom:
  port: 9999
  savings_profile: balanced
pxpipe:
  enabled: true
  port: 47822
  models: claude-sonnet-4-5
  auto_start: true
  override_anthropic_base_url: true
a2a:
  port: 9200
  remote_agents:
    - http://localhost:9001
agui:
  port: 9300
  session_timeout_seconds: 7200
models:
  my-model:
    provider: openai
    model: gpt-4o-mini
    api_key: sk-test
agents:
  my-agent:
    description: Test agent
    tools: [github, gitlab]
""")
        cfg = load_config(path)
        assert cfg.default_model == "gpt-4o"
        assert cfg.default_agent == "my-agent"
        assert cfg.rtk.enabled is False
        assert cfg.rtk.binary_path == "/usr/local/bin/rtk"
        assert cfg.headroom.port == 9999
        assert cfg.headroom.savings_profile == "balanced"
        assert cfg.pxpipe.enabled is True
        assert cfg.pxpipe.port == 47822
        assert cfg.pxpipe.models == "claude-sonnet-4-5"
        assert cfg.pxpipe.auto_start is True
        assert cfg.pxpipe.override_anthropic_base_url is True
        assert cfg.a2a.port == 9200
        assert cfg.a2a.remote_agents == ["http://localhost:9001"]
        assert cfg.agui.port == 9300
        assert cfg.agui.session_timeout_seconds == 7200
        assert "my-model" in cfg.models
        assert cfg.models["my-model"].provider == "openai"
        assert "my-agent" in cfg.agents
        assert cfg.agents["my-agent"].tools == ["github", "gitlab"]


def test_get_model_config() -> None:
    cfg = VOLYConfig()
    model = cfg.get_model_config("claude-sonnet")
    assert model.provider == "anthropic"
    assert "claude-sonnet" in model.model

    model = cfg.get_model_config("gpt-4o")
    assert model.provider == "openai"

    model = cfg.get_model_config("unknown-model")
    assert model.provider == "anthropic"


def test_a2a_config_defaults() -> None:
    cfg = A2AConfig()
    assert cfg.enabled is True
    assert cfg.port == 9100
    assert cfg.agent_discovery is True
    assert cfg.remote_agents == []


def test_agui_config_defaults() -> None:
    cfg = AGUIConfig()
    assert cfg.enabled is True
    assert cfg.port == 9101
    assert cfg.streaming is True
    assert cfg.session_timeout_seconds == 3600


# ─── Upward discovery is bounded at the target project's own VCS root ────────
# VOLY runs against arbitrary --cwd projects; walking to the filesystem root
# risked silently loading an unrelated ancestor's voly.yaml/.env (and its
# credentials) on a multi-project machine.
def test_find_config_path_stops_at_git_root(tmp_path: Path) -> None:
    from voly.config._loader import _find_config_path

    # unrelated-parent/voly.yaml must NOT be visible to a git-rooted child
    # project that doesn't have its own voly.yaml.
    (tmp_path / "voly.yaml").write_text("default_model: from-ancestor\n")
    project = tmp_path / "some-project"
    (project / ".git").mkdir(parents=True)
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)

    assert _find_config_path(nested) is None


def test_find_config_path_finds_own_config_within_git_root(tmp_path: Path) -> None:
    from voly.config._loader import _find_config_path

    project = tmp_path / "some-project"
    (project / ".git").mkdir(parents=True)
    (project / "voly.yaml").write_text("default_model: from-project\n")
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)

    found = _find_config_path(nested)
    assert found == project / "voly.yaml"


def test_load_dotenv_does_not_cross_git_root(
    tmp_path: Path, monkeypatch
) -> None:
    from voly.config._loader import _load_dotenv

    (tmp_path / ".env").write_text("VOLY_ANCESTOR_SECRET=leaked\n")
    project = tmp_path / "some-project"
    (project / ".git").mkdir(parents=True)
    nested = project / "src"
    nested.mkdir(parents=True)

    monkeypatch.delenv("VOLY_ANCESTOR_SECRET", raising=False)
    _load_dotenv(nested)
    assert "VOLY_ANCESTOR_SECRET" not in os.environ


def test_load_request_and_plan_command_timeouts(tmp_path: Path) -> None:
    path = tmp_path / "voly.yaml"
    path.write_text(
        """
ai_gateway:
  request_timeout_seconds: 15
plan:
  command_timeout_seconds: 60
"""
    )
    cfg = load_config(path)
    assert cfg.ai_gateway.request_timeout_seconds == 15.0
    assert cfg.plan.command_timeout_seconds == 60.0
