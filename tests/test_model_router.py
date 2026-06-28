"""Tests for Model Router."""

from codeops.model_router import (
    ModelRouter,
    ModelInfo,
    TaskCategory,
    DEFAULT_MODELS,
)


def test_model_router_routes_architecture() -> None:
    router = ModelRouter()
    model = router.route(task="Спроектируй архитектуру микросервисов", category=TaskCategory.ARCHITECTURE)
    assert model is not None
    assert model.provider in ("anthropic", "openai", "google")


def test_model_router_routes_coding() -> None:
    router = ModelRouter()
    model = router.route(task="Напиши функцию авторизации", category=TaskCategory.CODING)
    assert model is not None
    assert "claude" in model.name.lower() or "sonnet" in model.name.lower() or model.provider


def test_model_router_prefer_cost() -> None:
    router = ModelRouter()
    model = router.route(task="Сгенерируй документацию", prefer_cost=True)
    assert model.input_cost_per_1m <= 3.0


def test_model_router_prefer_speed() -> None:
    router = ModelRouter()
    model = router.route(task="Быстрый поиск файла", prefer_speed=True)
    assert model.avg_latency_ms <= 1500


def test_model_router_estimate_cost() -> None:
    router = ModelRouter()
    cost = router.estimate_cost("claude-sonnet-4-5-20250929", 10000, 1000)
    assert cost > 0


def test_model_router_compare_models() -> None:
    router = ModelRouter()
    results = router.compare_models(10000, 1000)
    assert len(results) >= 4
    assert results[0]["cost"] <= results[-1]["cost"]


def test_infer_category() -> None:
    router = ModelRouter()
    assert router._infer_category("Спроектируй архитектуру") == TaskCategory.ARCHITECTURE
    assert router._infer_category("Напиши функцию") == TaskCategory.CODING
    assert router._infer_category("Сделай code review") == TaskCategory.REVIEW
    assert router._infer_category("Напиши unit тесты") == TaskCategory.TESTING
    assert router._infer_category("Найди все файлы с auth") == TaskCategory.SEARCH
    assert router._infer_category("Напиши документацию") == TaskCategory.DOCUMENTATION
    assert router._infer_category("Проверь безопасность кода") == TaskCategory.SECURITY
    assert router._infer_category("Проанализируй логи") == TaskCategory.ANALYSIS


def test_model_info_fields() -> None:
    for name, model in DEFAULT_MODELS.items():
        assert model.name == name
        assert model.provider
        assert model.input_cost_per_1m >= 0
        assert model.context_window > 0
        assert model.avg_latency_ms > 0
