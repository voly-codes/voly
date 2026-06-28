"""
Model Layer — абстракция для работы с различными LLM провайдерами.

Поддерживает:
    - Anthropic (Claude Sonnet / Opus)
    - OpenAI (GPT-4o / GPT-4o-mini)
    - Google (Gemini Pro / Flash)
    - Ollama (локальные модели)
    - Любые OpenAI-совместимые API

Принцип Model Agnostic: Код агента не зависит от конкретной модели.
"""

from codeops.models.providers import (
    ModelProvider,
    ModelResponse,
    ModelUsage,
    ProviderRegistry,
    AnthropicProvider,
    OpenAIProvider,
    GoogleProvider,
    OllamaProvider,
    get_provider,
    create_provider,
)

__all__ = [
    "ModelProvider",
    "ModelResponse",
    "ModelUsage",
    "ProviderRegistry",
    "AnthropicProvider",
    "OpenAIProvider",
    "GoogleProvider",
    "OllamaProvider",
    "get_provider",
    "create_provider",
]
