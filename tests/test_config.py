"""Tests for CodeOps config module."""

import tempfile
from pathlib import Path

from codeops.config import (
    CodeOpsConfig,
    RTKConfig,
    HeadroomConfig,
    MemoryConfig,
    A2AConfig,
    AGUIConfig,
    ModelConfig,
    AgentConfig,
    create_default_config,
    load_config,
)


def test_default_config() -> None:
    cfg = CodeOpsConfig()
    assert cfg.default_model == "claude-sonnet"
    assert cfg.default_agent == "claude"
    assert cfg.rtk.enabled is True
    assert cfg.headroom.enabled is True
    assert cfg.a2a.enabled is True
    assert cfg.agui.enabled is True


def test_create_default_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "codeops.yaml"
        create_default_config(path)
        assert path.exists()
        content = path.read_text()
        assert "default_model: claude-sonnet" in content
        assert "default_agent: claude" in content
        assert "rtk:" in content
        assert "headroom:" in content
        assert "a2a:" in content
        assert "agui:" in content


def test_load_config_from_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "codeops.yaml"
        path.write_text("""
default_model: gpt-4o
default_agent: my-agent
rtk:
  enabled: false
  binary_path: /usr/local/bin/rtk
headroom:
  port: 9999
  savings_profile: balanced
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
        assert cfg.a2a.port == 9200
        assert cfg.a2a.remote_agents == ["http://localhost:9001"]
        assert cfg.agui.port == 9300
        assert cfg.agui.session_timeout_seconds == 7200
        assert "my-model" in cfg.models
        assert cfg.models["my-model"].provider == "openai"
        assert "my-agent" in cfg.agents
        assert cfg.agents["my-agent"].tools == ["github", "gitlab"]


def test_get_model_config() -> None:
    cfg = CodeOpsConfig()
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
