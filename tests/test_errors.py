"""Tests for error handling — exceptions, validation, and error returns."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# Custom exception classes
# ============================================================


def test_marketplace_error_can_be_raised_and_caught() -> None:
    from voly.registry.marketplace import MarketplaceError

    with pytest.raises(MarketplaceError, match="marketplace is down"):
        raise MarketplaceError("marketplace is down")

    try:
        raise MarketplaceError("HTTP 404: not found")
    except MarketplaceError as e:
        assert "HTTP 404" in str(e)


def test_catalog_client_error_can_be_raised_and_caught() -> None:
    from voly.catalog.client import CatalogClientError

    with pytest.raises(CatalogClientError, match="catalog unreachable"):
        raise CatalogClientError("catalog unreachable")

    with pytest.raises(CatalogClientError):
        raise CatalogClientError("HTTP 500: internal error")


def test_memory_client_error_can_be_raised_and_caught() -> None:
    from voly.memory.client import MemoryClientError

    with pytest.raises(MemoryClientError):
        raise MemoryClientError("memory service error")


def test_spend_client_error_can_be_raised_and_caught() -> None:
    from voly.spend.client import SpendClientError

    with pytest.raises(SpendClientError):
        raise SpendClientError("spend service error")


def test_federation_client_error_can_be_raised_and_caught() -> None:
    from voly.a2a.federation import FederationClientError

    with pytest.raises(FederationClientError):
        raise FederationClientError("federation error")


def test_telemetry_delivery_error_can_be_raised_and_caught() -> None:
    from voly.telemetry import TelemetryDeliveryError

    with pytest.raises(TelemetryDeliveryError, match="network down"):
        raise TelemetryDeliveryError("network down")

    with pytest.raises(TelemetryDeliveryError):
        raise TelemetryDeliveryError("HTTP 500: internal error")


# ============================================================
# Registry / loader validation errors
# ============================================================


def test_skill_from_dict_raises_on_missing_id_and_name() -> None:
    from voly.registry.loader import skill_from_dict

    with pytest.raises(ValueError, match="Skill must have id or name"):
        skill_from_dict({})

    with pytest.raises(ValueError, match="Skill must have id or name"):
        skill_from_dict({"description": "no id here"})


def test_skill_from_dict_uses_name_as_fallback_id() -> None:
    from voly.registry.loader import skill_from_dict

    skill = skill_from_dict({"name": "my-skill"})
    assert skill.id == "my-skill"


# ============================================================
# Registry / skills marketplace errors
# ============================================================


def test_install_from_marketplace_raises_without_url() -> None:
    from voly.registry.marketplace import MarketplaceError
    from voly.registry.skills import SkillRegistry

    registry = SkillRegistry(marketplace_url="")

    with pytest.raises(MarketplaceError, match="marketplace_url is not configured"):
        registry.install_from_marketplace("some-skill")


def test_publish_to_marketplace_raises_without_url() -> None:
    from voly.registry.marketplace import MarketplaceError
    from voly.registry.skills import SkillRegistry

    registry = SkillRegistry(marketplace_url="")

    with pytest.raises(MarketplaceError, match="marketplace_url is not configured"):
        registry.publish_to_marketplace({"name": "test"})


# ============================================================
# A2A errors
# ============================================================


@pytest.mark.asyncio
async def test_a2a_agent_execute_without_executor() -> None:
    from voly.a2a import A2AAgent, AgentCard, A2ATask

    card = AgentCard(
        name="NoOpAgent",
        description="Agent without executor",
        url="http://localhost:9999",
    )
    agent = A2AAgent(card)
    task = A2ATask(id="t1", title="test")

    with pytest.raises(NotImplementedError, match="NoOpAgent has no executor"):
        await agent.execute(task)  # type: ignore[misc]


def test_a2a_client_discover_returns_none_on_error() -> None:
    from voly.a2a import A2AClient

    client = A2AClient()
    result = client.discover("http://nonexistent.example.com/agent")
    assert result is None


def test_a2a_send_task_returns_failed_on_connection_error() -> None:
    from voly.a2a import A2AClient, A2ATask

    client = A2AClient()
    task = A2ATask(
        id="t-fail",
        title="fail",
        description="will fail",
        agent_url="http://nonexistent.example.com/agent",
    )

    result = client.send_task("http://nonexistent.example.com/agent", task)
    assert result.state.value == "failed"
    assert "error" in result.error.lower() or "failed" in result.error.lower()


def test_a2a_get_task_status_returns_none_on_error() -> None:
    from voly.a2a import A2AClient

    client = A2AClient()
    result = client.get_task_status("http://nonexistent.example.com/agent", "t1")
    assert result is None


# ============================================================
# Telemetry errors
# ============================================================


def test_send_to_pipeline_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.telemetry import TaskEvent, TelemetryDeliveryError, send_to_pipeline

    event = TaskEvent(task_id="http-err", agent="test", status="completed")

    class FakeHTTPError(OSError):
        def __init__(self, code: int, msg: str):
            self.code = code
            self.msg = msg

        def read(self) -> bytes:
            return b'{"error":"internal"}'

    def failing_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="http://example.com",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=MagicMock(),
        )

    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
        url="http://example.com",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=MagicMock(**{"read.return_value": b'internal error'}),
    )):
        with pytest.raises(TelemetryDeliveryError, match="HTTP 500"):
            send_to_pipeline("https://pipe.example.com/ingest", event, token="tok")


def test_send_to_pipeline_raises_on_url_error() -> None:
    from voly.telemetry import TaskEvent, TelemetryDeliveryError, send_to_pipeline

    event = TaskEvent(task_id="url-err", agent="test", status="completed")

    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError(
        reason="Name or service not known"
    )):
        with pytest.raises(TelemetryDeliveryError, match="Name or service not known"):
            send_to_pipeline("https://pipe.example.com/ingest", event)


def test_emit_event_handles_pipeline_failure_gracefully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voly.telemetry import TaskEvent, TelemetryDeliveryError, emit_event

    event = TaskEvent(task_id="graceful-fail", agent="test", status="completed")
    events: list = []

    def capturing_send(*args, **kwargs):
        events.append(args)
        raise TelemetryDeliveryError("network error")

    monkeypatch.setattr("voly.telemetry.send_to_pipeline", capturing_send)

    path = emit_event(
        event,
        events_dir=tmp_path,
        pipeline_url="https://pipe.example.com/ingest",
    )
    assert path is not None
    assert path.exists()
    assert json.loads(path.read_text())["task_id"] == "graceful-fail"


# ============================================================
# HTTP client errors (Marketplace, Catalog, Federation, Workflow, Memory, Spend)
# ============================================================


@pytest.fixture
def mock_http_error() -> MagicMock:
    """Create a mock that raises HTTPError when urlopen is called."""
    import urllib.error

    fp = MagicMock()
    fp.read.return_value = b'{"error":"not found"}'
    fp.__enter__.return_value = fp
    return fp


def _test_client_http_error(
    client_class,
    error_class,
    base_url: str = "http://localhost:8080",
    method_name: str = "health",
    method_args: tuple = (),
) -> None:
    """Shared helper: verify client methods raise the correct error on HTTP 500."""
    import urllib.error

    fp = MagicMock()
    fp.read.return_value = b'internal error'
    fp.__enter__.return_value = fp

    http_err = urllib.error.HTTPError(
        url=f"{base_url}/health",
        code=503,
        msg="Service Unavailable",
        hdrs={},
        fp=fp,
    )

    client = client_class(base_url=base_url)
    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(error_class, match="HTTP 503"):
            getattr(client, method_name)(*method_args)


def _test_client_url_error(client_class, error_class, base_url: str = "http://localhost:8080") -> None:
    """Shared helper: verify client methods raise the correct error on URLError."""
    import urllib.error

    client = client_class(base_url=base_url)
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError(
        reason="Connection refused"
    )):
        with pytest.raises(error_class, match="Connection refused"):
            client.health()


class TestMarketplaceClientErrors:
    def test_http_error(self) -> None:
        from voly.registry.marketplace import MarketplaceClient, MarketplaceError
        _test_client_http_error(MarketplaceClient, MarketplaceError)

    def test_url_error(self) -> None:
        from voly.registry.marketplace import MarketplaceClient, MarketplaceError
        _test_client_url_error(MarketplaceClient, MarketplaceError)


class TestCatalogClientErrors:
    def test_http_error(self) -> None:
        from voly.catalog.client import CatalogClient, CatalogClientError
        _test_client_http_error(CatalogClient, CatalogClientError)

    def test_url_error(self) -> None:
        from voly.catalog.client import CatalogClient, CatalogClientError
        _test_client_url_error(CatalogClient, CatalogClientError)


class TestFederationClientErrors:
    def test_http_error(self) -> None:
        from voly.a2a.federation import FederationClient, FederationClientError
        _test_client_http_error(FederationClient, FederationClientError)

    def test_url_error(self) -> None:
        from voly.a2a.federation import FederationClient, FederationClientError
        _test_client_url_error(FederationClient, FederationClientError)


class TestMemoryClientErrors:
    def test_http_error(self) -> None:
        from voly.memory.client import MemoryClient, MemoryClientError
        _test_client_http_error(MemoryClient, MemoryClientError)

    def test_url_error(self) -> None:
        from voly.memory.client import MemoryClient, MemoryClientError
        _test_client_url_error(MemoryClient, MemoryClientError)


class TestSpendClientErrors:
    def test_http_error(self) -> None:
        from voly.spend.client import SpendClient, SpendClientError
        _test_client_http_error(SpendClient, SpendClientError)

    def test_url_error(self) -> None:
        from voly.spend.client import SpendClient, SpendClientError
        _test_client_url_error(SpendClient, SpendClientError)


# ============================================================
# MCP errors
# ============================================================


def test_mcp_register_builtin_unknown() -> None:
    from voly.tools.mcp import MCPManager

    manager = MCPManager()

    with pytest.raises(ValueError, match="Unknown built-in MCP server"):
        manager.register_builtin("nonexistent-server")


# ============================================================
# Executor errors
# ============================================================


def test_build_executor_unknown_agent() -> None:
    from voly.executor.multi_agent import _build_executor

    with pytest.raises(ValueError, match="Unknown agent"):
        _build_executor("some-unknown-agent")


def test_executor_result_error_returns_success_false() -> None:
    from voly.executor.base import ExecutorResult

    ok = ExecutorResult(success=True, output="done")
    assert ok.success is True
    assert ok.error == ""

    err = ExecutorResult(success=False, error="something went wrong")
    assert err.success is False
    assert err.error == "something went wrong"
    assert err.num_turns == 0


# ============================================================
# AI Gateway errors
# ============================================================


def test_gateway_chat_returns_error_dict_on_failure() -> None:
    from voly.ai_gateway.gateway import AIGateway

    gw = AIGateway()
    gw._enabled = False
    result = gw.chat(
        messages=[{"role": "user", "content": "hello"}],
        model="nonexistent-model",
        provider_name="nonexistent-provider",
    )
    # Should return error dict instead of raising
    assert isinstance(result, dict)
    assert "error" in result
    assert "Unsupported provider" in result["error"]
