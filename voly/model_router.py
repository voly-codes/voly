"""
Model Router — выбор оптимальной модели по стоимости, latency и типу задачи.

Routing factors:
    - cost (цена за 1M токенов)
    - latency (быстродействие)
    - task_type (архитектура / кодинг / фаст-сёрч / дешёвый батч)
    - skill_requirements (требования скилла к модели)

Примеры:
    Архитектура → Claude Opus (качество важнее цены)
    Кодинг → Claude Sonnet (баланс)
    Быстрый поиск → GPT-4o-mini (дешево и быстро)
    Дешёвый батч → Ollama / Gemini Flash (минимальная цена)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskCategory(Enum):
    ARCHITECTURE = "architecture"
    CODING = "coding"
    REVIEW = "review"
    TESTING = "testing"
    SEARCH = "search"
    BATCH = "batch"
    DOCUMENTATION = "documentation"
    SECURITY = "security"
    ANALYSIS = "analysis"


@dataclass
class ModelInfo:
    name: str
    provider: str
    input_cost_per_1m: float
    output_cost_per_1m: float
    avg_latency_ms: float
    context_window: int = 200_000
    max_output_tokens: int = 8192
    capabilities: list[str] = field(default_factory=list)
    strengths: list[TaskCategory] = field(default_factory=list)


DEFAULT_MODELS: dict[str, ModelInfo] = {
    "claude-opus-4-5-20250929": ModelInfo(
        name="claude-opus-4-5-20250929",
        provider="anthropic",
        input_cost_per_1m=15.0,
        output_cost_per_1m=75.0,
        avg_latency_ms=3000,
        context_window=200_000,
        max_output_tokens=32768,
        capabilities=["architecture", "complex-reasoning", "analysis"],
        strengths=[TaskCategory.ARCHITECTURE, TaskCategory.ANALYSIS, TaskCategory.SECURITY],
    ),
    "claude-sonnet-4-5-20250929": ModelInfo(
        name="claude-sonnet-4-5-20250929",
        provider="anthropic",
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0,
        avg_latency_ms=1500,
        context_window=200_000,
        max_output_tokens=32768,
        capabilities=["coding", "review", "testing", "documentation"],
        strengths=[TaskCategory.CODING, TaskCategory.REVIEW, TaskCategory.TESTING],
    ),
    "gpt-4o": ModelInfo(
        name="gpt-4o",
        provider="openai",
        input_cost_per_1m=2.5,
        output_cost_per_1m=10.0,
        avg_latency_ms=1200,
        context_window=128_000,
        max_output_tokens=16384,
        capabilities=["coding", "review", "search", "analysis"],
        strengths=[TaskCategory.REVIEW, TaskCategory.ANALYSIS],
    ),
    "gpt-4o-mini": ModelInfo(
        name="gpt-4o-mini",
        provider="openai",
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        avg_latency_ms=500,
        context_window=128_000,
        max_output_tokens=16384,
        capabilities=["fast-search", "simple-coding", "testing"],
        strengths=[TaskCategory.SEARCH, TaskCategory.TESTING, TaskCategory.BATCH],
    ),
    "gemini-2.5-pro": ModelInfo(
        name="gemini-2.5-pro",
        provider="google",
        input_cost_per_1m=1.25,
        output_cost_per_1m=5.0,
        avg_latency_ms=1800,
        context_window=1_000_000,
        max_output_tokens=65536,
        capabilities=["coding", "review", "large-context", "analysis"],
        strengths=[TaskCategory.CODING, TaskCategory.ANALYSIS],
    ),
    "gemini-2.5-flash": ModelInfo(
        name="gemini-2.5-flash",
        provider="google",
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        avg_latency_ms=400,
        context_window=1_000_000,
        max_output_tokens=32768,
        capabilities=["fast-search", "simple-coding", "batch"],
        strengths=[TaskCategory.SEARCH, TaskCategory.BATCH, TaskCategory.TESTING],
    ),
    # ── DeepSeek ──────────────────────────────────────────────────────────────
    "deepseek-chat": ModelInfo(
        name="deepseek-chat",
        provider="deepseek",
        input_cost_per_1m=0.27,
        output_cost_per_1m=1.10,
        avg_latency_ms=800,
        context_window=64_000,
        max_output_tokens=8192,
        capabilities=["coding", "review", "simple-coding", "batch"],
        strengths=[TaskCategory.CODING, TaskCategory.REVIEW, TaskCategory.BATCH],
    ),
    "deepseek-coder": ModelInfo(
        name="deepseek-coder",
        provider="deepseek",
        input_cost_per_1m=0.14,
        output_cost_per_1m=0.28,
        avg_latency_ms=700,
        context_window=64_000,
        max_output_tokens=8192,
        capabilities=["coding", "simple-coding", "testing", "batch"],
        strengths=[TaskCategory.CODING, TaskCategory.TESTING, TaskCategory.BATCH],
    ),
    "deepseek-reasoner": ModelInfo(
        name="deepseek-reasoner",
        provider="deepseek",
        input_cost_per_1m=0.55,
        output_cost_per_1m=2.19,
        avg_latency_ms=3500,
        context_window=64_000,
        max_output_tokens=32768,
        capabilities=["complex-reasoning", "architecture", "analysis"],
        strengths=[TaskCategory.ARCHITECTURE, TaskCategory.ANALYSIS, TaskCategory.SECURITY],
    ),
    # ── OpenCode Go ───────────────────────────────────────────────────────────
    "kimi-k3": ModelInfo(
        name="kimi-k3",
        provider="opencode",
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        avg_latency_ms=2000,
        context_window=256_000,
        max_output_tokens=32768,
        capabilities=["architecture", "complex-reasoning", "analysis", "coding"],
        strengths=[TaskCategory.ARCHITECTURE, TaskCategory.ANALYSIS, TaskCategory.CODING],
    ),
    "opencode-go": ModelInfo(
        name="opencode-go",
        provider="opencode",
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        avg_latency_ms=1200,
        context_window=128_000,
        max_output_tokens=16384,
        capabilities=["coding", "agentic", "review", "testing"],
        strengths=[TaskCategory.CODING, TaskCategory.TESTING],
    ),
    # ── OpenCode Zen ──────────────────────────────────────────────────────────
    "zen": ModelInfo(
        name="zen",
        provider="zen",
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        avg_latency_ms=1500,
        context_window=128_000,
        max_output_tokens=16384,
        capabilities=["analysis", "architecture", "review", "documentation"],
        strengths=[TaskCategory.ANALYSIS, TaskCategory.ARCHITECTURE, TaskCategory.DOCUMENTATION],
    ),
    # ── MiMo ──────────────────────────────────────────────────────────────────
    "MiMo-7B-RL": ModelInfo(
        name="MiMo-7B-RL",
        provider="mimo",
        input_cost_per_1m=0.05,
        output_cost_per_1m=0.10,
        avg_latency_ms=300,
        context_window=32_000,
        max_output_tokens=4096,
        capabilities=["fast-search", "simple-coding", "batch"],
        strengths=[TaskCategory.BATCH, TaskCategory.SEARCH],
    ),
}


class ModelRouter:
    def __init__(self, models: dict[str, ModelInfo] | None = None):
        self._models = models or dict(DEFAULT_MODELS)

    def register(self, info: ModelInfo) -> None:
        self._models[info.name] = info

    def get(self, name: str) -> ModelInfo | None:
        return self._models.get(name)

    def list_models(self) -> list[ModelInfo]:
        return list(self._models.values())

    def route(
        self,
        task: str = "",
        category: TaskCategory | None = None,
        prefer_cost: bool = False,
        prefer_speed: bool = False,
        required_capability: str | None = None,
    ) -> ModelInfo:
        if category is None:
            category = self._infer_category(task)

        candidates = list(self._models.values())

        if required_capability:
            candidates = [m for m in candidates if required_capability in m.capabilities]

        if not candidates:
            candidates = list(self._models.values())

        scored: list[tuple[ModelInfo, float]] = []
        for model in candidates:
            score = 0.0

            if category in model.strengths:
                score += 10.0

            if required_capability and required_capability in model.capabilities:
                score += 5.0

            if prefer_cost:
                total_cost = model.input_cost_per_1m + model.output_cost_per_1m
                score += 50.0 / (total_cost + 0.01)

            if prefer_speed:
                score += 5000.0 / (model.avg_latency_ms + 1)

            scored.append((model, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def estimate_cost(
        self, model_name: str, input_tokens: int, output_tokens: int
    ) -> float:
        model = self._models.get(model_name)
        if not model:
            return 0.0
        return (
            (input_tokens / 1_000_000) * model.input_cost_per_1m
            + (output_tokens / 1_000_000) * model.output_cost_per_1m
        )

    def compare_models(self, input_tokens: int, output_tokens: int) -> list[dict[str, Any]]:
        results = []
        for model in self._models.values():
            cost = self.estimate_cost(model.name, input_tokens, output_tokens)
            results.append({
                "model": model.name,
                "provider": model.provider,
                "cost": round(cost, 4),
                "latency_ms": model.avg_latency_ms,
                "context_window": model.context_window,
            })
        results.sort(key=lambda x: x["cost"])
        return results

    def _infer_category(self, task: str) -> TaskCategory:
        t = task.lower()
        if any(kw in t for kw in ["архитектур", "architecture", "design system", "спроектир"]):
            return TaskCategory.ARCHITECTURE
        if any(kw in t for kw in ["review", "ревью", "audit"]):
            return TaskCategory.REVIEW
        if any(kw in t for kw in ["тест", "test", "pytest", "unittest"]):
            return TaskCategory.TESTING
        if any(kw in t for kw in ["безопасност", "security", "уязвим", "vulnerab"]):
            return TaskCategory.SECURITY
        if any(kw in t for kw in ["найди", "search", "найти", "grep", "locate"]):
            return TaskCategory.SEARCH
        if any(kw in t for kw in ["анализ", "analysis", "research", "исслед"]):
            return TaskCategory.ANALYSIS
        if any(kw in t for kw in ["документ", "document", "readme", "wiki"]):
            return TaskCategory.DOCUMENTATION
        if any(kw in t for kw in ["напиши", "создай", "реализуй", "implement", "code", "build", "сделай"]):
            return TaskCategory.CODING
        return TaskCategory.CODING
