"""Sync model catalog from OpenCode Zen GET /v1/models."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from codeops.catalog.types import CatalogModel

USER_AGENT = "CodeOps/0.1 (+https://github.com/codeops)"

FREE_MODEL_IDS = frozenset({
    "big-pickle",
    "deepseek-v4-flash-free",
    "mimo-v2.5-free",
    "nemotron-3-ultra-free",
    "north-mini-code-free",
    "qwen3.6-plus-free",
    "minimax-m3-free",
})

CHEAP_MODEL_IDS = frozenset({
    "deepseek-v4-flash",
    "qwen3.5-plus",
    "qwen3.6-plus",
    "glm-5",
    "glm-5.1",
    "glm-5.2",
    "minimax-m2.5",
    "minimax-m2.7",
    "kimi-k2.5",
    "kimi-k2.6",
})

PREMIUM_MODEL_IDS = frozenset({
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-fable-5",
    "gpt-5.5-pro",
    "gpt-5.4-pro",
})

PROVIDER_HINTS: list[tuple[str, str]] = [
    ("claude", "anthropic"),
    ("gpt", "openai"),
    ("gemini", "google"),
    ("deepseek", "deepseek"),
    ("kimi", "moonshot"),
    ("qwen", "alibaba"),
    ("glm", "z.ai"),
    ("minimax", "minimax"),
    ("mimo", "xiaomi"),
    ("nemotron", "nvidia"),
    ("grok", "xai"),
]


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _infer_provider(model_id: str, display_name: str = "") -> str:
    blob = f"{model_id} {display_name}".lower()
    for hint, provider in PROVIDER_HINTS:
        if hint in blob:
            return provider
    if "free" in model_id or model_id in ("big-pickle", "north-mini-code-free"):
        return "stealth"
    return "unknown"


def _infer_tier(model_id: str) -> str:
    if model_id in FREE_MODEL_IDS or model_id.endswith("-free"):
        return "free"
    if model_id in CHEAP_MODEL_IDS:
        return "cheap"
    if model_id in PREMIUM_MODEL_IDS:
        return "premium"
    if model_id in ("big-pickle", "north-mini-code-free"):
        return "stealth"
    return "standard"


def _infer_executors(model_id: str) -> list[str]:
    # GO endpoint models are often coding-focused; Zen API lists all on /zen/v1/models
    if model_id.endswith("-free") or "codex" in model_id or model_id.startswith("kimi"):
        return ["zen", "opencode"]
    if model_id.startswith("claude") or model_id.startswith("gpt"):
        return ["zen", "opencode", "pipeline"]
    return ["zen", "opencode"]


def _infer_strengths(model_id: str) -> list[str]:
    strengths: list[str] = []
    mid = model_id.lower()
    if "opus" in mid or "fable" in mid or "gpt-5.5" in mid:
        strengths.extend(["plan", "supervisor", "architecture"])
    if "haiku" in mid or "flash" in mid or "nano" in mid or "mini" in mid:
        strengths.extend(["review", "audit", "fast"])
    if "codex" in mid or "kimi" in mid or "deepseek" in mid:
        strengths.extend(["coding", "typescript", "backend"])
    if "sonnet" in mid:
        strengths.extend(["coding", "review", "ui"])
    if mid.endswith("-free"):
        strengths.append("free-tier")
    return strengths or ["general"]


def parse_zen_models_payload(data: object) -> list[CatalogModel]:
    """Parse OpenAI-style /v1/models response."""
    if isinstance(data, dict):
        items = data.get("data") or data.get("models") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    models: list[CatalogModel] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id") or item.get("model") or ""
        if not raw_id:
            continue
        model_id = raw_id.split("/")[-1] if "/" in raw_id else raw_id
        display = item.get("name") or item.get("display_name") or model_id
        models.append(
            CatalogModel(
                id=model_id,
                name=str(display),
                provider=_infer_provider(model_id, str(display)),
                tier=_infer_tier(model_id),
                executor_compat=_infer_executors(model_id),
                strengths=_infer_strengths(model_id),
                enabled=True,
            )
        )
    return models


def fetch_zen_models(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> list[CatalogModel]:
    url = (base_url or os.getenv("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen/v1")).rstrip("/")
    if not url.endswith("/models"):
        url = f"{url}/models"
    key = api_key or os.getenv("OPENCODE_API_KEY", "")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Zen models API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Zen models API: {exc.reason}") from exc

    models = parse_zen_models_payload(data)
    if not models:
        models = _builtin_fallback_catalog()
    return models


def _builtin_fallback_catalog() -> list[CatalogModel]:
    """Fallback when API unavailable — matches user's Zen workspace list."""
    ids = [
        "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5",
        "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-free",
        "kimi-k2.6", "kimi-k2.5", "gpt-5.3-codex", "gpt-5.4-mini",
        "qwen3.5-plus", "qwen3.6-plus-free", "mimo-v2.5-free",
        "nemotron-3-ultra-free", "glm-5.2", "minimax-m2.7",
        "gemini-3.1-pro", "gemini-3.5-flash",
    ]
    return [
        CatalogModel(
            id=mid,
            name=mid,
            provider=_infer_provider(mid),
            tier=_infer_tier(mid),
            executor_compat=_infer_executors(mid),
            strengths=_infer_strengths(mid),
        )
        for mid in ids
    ]
