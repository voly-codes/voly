"""Tests for VOLY agent router."""

from voly.config import VOLYConfig
from voly.router import AgentRouter, RouteDecision, TaskAnalysis


def test_router_default() -> None:
    router = AgentRouter()
    result = router.route("Напиши функцию сложения")
    assert isinstance(result, RouteDecision)
    assert result.agent == "claude"
    assert result.provider == "anthropic"


def test_route_architecture_task() -> None:
    router = AgentRouter()
    result = router.route("Спроектируй архитектуру нового микросервиса")
    assert result.agent == "architect"
    # First preferred provider for architecture is anthropic (claude-sonnet-4-6)
    assert result.provider == "anthropic"
    assert "claude" in result.model


def test_route_review_task() -> None:
    router = AgentRouter()
    result = router.route("Сделай code review пулл-реквеста")
    assert result.agent == "reviewer"
    # First preferred provider for review is anthropic (health-aware chain)
    assert result.provider == "anthropic"


def test_route_bugfix_task() -> None:
    router = AgentRouter()
    result = router.route("Исправь баг с авторизацией пользователя")
    assert result.agent in ("bugfixer", "claude")


def test_route_test_task() -> None:
    router = AgentRouter()
    result = router.route("Напиши unit-тесты для модуля auth")
    assert result.agent == "tester"


def test_analyze_task_complexity() -> None:
    router = AgentRouter()
    analysis = router.analyze_task("Перепроектируй систему кеширования")
    assert analysis.complexity in ("high", "medium", "low")
    assert analysis.requires_code_gen is False
    assert analysis.confidence > 0.3


def test_analyze_simple_task() -> None:
    router = AgentRouter()
    analysis = router.analyze_task("Исправь опечатку в readme")
    assert analysis.complexity == "low"
    assert analysis.confidence > 0.3


def test_route_with_config_override() -> None:
    config = VOLYConfig()
    config.default_agent = "my-custom-agent"
    router = AgentRouter(config)
    result = router.route("Какая-то незнакомая задача без ключевых слов")
    assert result.agent == "my-custom-agent"
