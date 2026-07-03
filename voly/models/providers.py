"""
Абстрактный слой провайдеров моделей.

Позволяет единообразно работать с разными LLM API:
    - Anthropic (messages API)
    - OpenAI (chat completions API)
    - Google Gemini (generateContent API)
    - Ollama (локальные модели)
"""

from __future__ import annotations

import os
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ModelResponse:
    content: str
    usage: ModelUsage = field(default_factory=ModelUsage)
    model: str = ""
    stop_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        ...

    @abstractmethod
    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        ...

    def supports_model(self, model: str) -> bool:
        return True


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        import urllib.request
        import urllib.error

        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            return ModelResponse(
                content="".join(
                    block.get("text", "")
                    for block in data.get("content", [])
                    if block.get("type") == "text"
                ),
                usage=ModelUsage(
                    input_tokens=data.get("usage", {}).get("input_tokens", 0),
                    output_tokens=data.get("usage", {}).get("output_tokens", 0),
                    cache_read_tokens=data.get("usage", {}).get("cache_read_input_tokens", 0),
                    cache_write_tokens=data.get("usage", {}).get("cache_creation_input_tokens", 0),
                ),
                model=data.get("model", model),
                stop_reason=data.get("stop_reason", ""),
                raw=data,
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Anthropic API error: {e.code} {e.read().decode()}") from e

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            total = 0
            for msg in messages:
                if isinstance(msg.get("content"), str):
                    total += len(enc.encode(msg["content"]))
                elif isinstance(msg.get("content"), list):
                    for block in msg["content"]:
                        if isinstance(block, dict) and "text" in block:
                            total += len(enc.encode(block["text"]))
            return total
        except ImportError:
            return sum(len(str(m)) // 4 for m in messages)


class OpenAIProvider(ModelProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        import urllib.request
        import urllib.error

        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})

        body: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools

        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            choice = data["choices"][0]
            return ModelResponse(
                content=choice["message"].get("content", "") or "",
                usage=ModelUsage(
                    input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                    output_tokens=data.get("usage", {}).get("completion_tokens", 0),
                ),
                model=data.get("model", model),
                stop_reason=choice.get("finish_reason", ""),
                raw=data,
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OpenAI API error: {e.code} {e.read().decode()}") from e

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model(model)
        except (ImportError, KeyError):
            try:
                import tiktoken
                enc = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                return sum(len(str(m)) // 4 for m in messages)
        total = 0
        for msg in messages:
            total += len(enc.encode(str(msg.get("content", ""))))
        return total


class GoogleProvider(ModelProvider):
    name = "google"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self.base_url = base_url or os.environ.get("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com")

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        import urllib.request
        import urllib.error

        url = f"{self.base_url}/v1beta/models/{model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = [{"text": msg["content"]}] if isinstance(msg["content"], str) else msg["content"]
            contents.append({"role": role, "parts": parts})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}] if isinstance(tools, list) else tools

        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            candidates = data.get("candidates", [{}])
            content = candidates[0].get("content", {}).get("parts", [{"text": ""}])
            text = "".join(p.get("text", "") for p in content)

            return ModelResponse(
                content=text,
                usage=ModelUsage(
                    input_tokens=data.get("usageMetadata", {}).get("promptTokenCount", 0),
                    output_tokens=data.get("usageMetadata", {}).get("candidatesTokenCount", 0),
                ),
                model=model,
                stop_reason=candidates[0].get("finishReason", ""),
                raw=data,
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Google API error: {e.code} {e.read().decode()}") from e

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        return sum(len(str(m)) // 4 for m in messages)


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        import urllib.request
        import urllib.error

        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}

        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})

        body: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            return ModelResponse(
                content=data.get("message", {}).get("content", ""),
                usage=ModelUsage(
                    input_tokens=data.get("prompt_eval_count", 0),
                    output_tokens=data.get("eval_count", 0),
                ),
                model=data.get("model", model),
                stop_reason=data.get("done_reason", ""),
                raw=data,
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Ollama API error: {e.code} {e.read().decode()}") from e

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        return sum(len(str(m)) // 4 for m in messages)


class ProviderRegistry:
    _providers: dict[str, type[ModelProvider]] = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "google": GoogleProvider,
        "ollama": OllamaProvider,
    }

    _instances: dict[str, ModelProvider] = {}

    @classmethod
    def register(cls, name: str, provider_cls: type[ModelProvider]) -> None:
        cls._providers[name] = provider_cls

    @classmethod
    def get(cls, name: str, **kwargs: Any) -> ModelProvider:
        if name not in cls._instances:
            if name not in cls._providers:
                raise ValueError(f"Unknown provider: {name}. Available: {list(cls._providers)}")
            cls._instances[name] = cls._providers[name](**kwargs)
        return cls._instances[name]

    @classmethod
    def clear(cls) -> None:
        cls._instances.clear()


def get_provider(name: str, **kwargs: Any) -> ModelProvider:
    return ProviderRegistry.get(name, **kwargs)


def create_provider(provider_name: str, api_key: str = "", base_url: str | None = None) -> ModelProvider:
    prov_map = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "google": GoogleProvider,
        "ollama": OllamaProvider,
    }
    if provider_name not in prov_map:
        raise ValueError(f"Unknown provider: {provider_name}")
    return prov_map[provider_name](api_key=api_key, base_url=base_url)
