"""Built-in model registry — used by VOLYConfig.get_model_config() as fallback."""

from codeops.config._types import ModelConfig

_DEFAULT_MODELS: dict[str, ModelConfig] = {
    # Anthropic (via Cloudflare Gateway)
    "claude-sonnet": ModelConfig(provider="anthropic", model="claude-sonnet-4-5-20250929"),
    "claude-opus":   ModelConfig(provider="anthropic", model="claude-opus-4-5-20250929"),
    # OpenAI (via Cloudflare Gateway)
    "gpt-4o":        ModelConfig(provider="openai", model="gpt-4o"),
    "gpt-4o-mini":   ModelConfig(provider="openai", model="gpt-4o-mini"),
    # Google (via Cloudflare Gateway)
    "gemini-pro":    ModelConfig(provider="google", model="gemini-2.5-pro"),
    "gemini-flash":  ModelConfig(provider="google", model="gemini-2.5-flash"),
    # DeepSeek direct
    "deepseek-chat":     ModelConfig(provider="deepseek", model="deepseek-chat"),
    "deepseek-reasoner": ModelConfig(provider="deepseek", model="deepseek-reasoner"),
    # MiMo direct
    "mimo-pro":  ModelConfig(provider="mimo", model="mimo-v2.5-pro"),
    "mimo-fast": ModelConfig(provider="mimo", model="mimo-v2.5"),
    "mimo-omni": ModelConfig(provider="mimo", model="mimo-v2-omni"),

    # ── OpenCode Go (opencode.ai/zen/go/v1) — subscription-based ──
    "deepseek-v4-flash": ModelConfig(provider="opencode", model="deepseek-v4-flash"),
    "deepseek-v4-pro":   ModelConfig(provider="opencode", model="deepseek-v4-pro"),
    "kimi-k2.6":         ModelConfig(provider="opencode", model="kimi-k2.6"),
    "kimi-k2.7-code":    ModelConfig(provider="opencode", model="kimi-k2.7-code"),
    "qwen3.7-plus":      ModelConfig(provider="opencode", model="qwen3.7-plus"),
    "qwen3.7-max":       ModelConfig(provider="opencode", model="qwen3.7-max"),
    "minimax-m3":        ModelConfig(provider="opencode", model="minimax-m3"),
    "glm-5.2":           ModelConfig(provider="opencode", model="glm-5.2"),
    "mimo-v2.5":         ModelConfig(provider="opencode", model="mimo-v2.5"),
    "mimo-v2.5-pro":     ModelConfig(provider="opencode", model="mimo-v2.5-pro"),

    # ── OpenCode Zen (opencode.ai/zen/v1) — pay-per-use curated ──
    "claude-sonnet-4-6":      ModelConfig(provider="opencode-zen", model="claude-sonnet-4-6"),
    "claude-opus-4-8":        ModelConfig(provider="opencode-zen", model="claude-opus-4-8"),
    "claude-haiku-4-5":       ModelConfig(provider="opencode-zen", model="claude-haiku-4-5"),
    "gpt-5.5":                ModelConfig(provider="opencode-zen", model="gpt-5.5"),
    "gpt-5.5-pro":            ModelConfig(provider="opencode-zen", model="gpt-5.5-pro"),
    "gpt-5.4":                ModelConfig(provider="opencode-zen", model="gpt-5.4"),
    "gpt-5.4-mini":           ModelConfig(provider="opencode-zen", model="gpt-5.4-mini"),
    "gemini-3.5-flash":       ModelConfig(provider="opencode-zen", model="gemini-3.5-flash"),
    "deepseek-v4-flash-free": ModelConfig(provider="opencode-zen", model="deepseek-v4-flash-free"),
    "mimo-v2.5-free":         ModelConfig(provider="opencode-zen", model="mimo-v2.5-free"),
    "big-pickle":             ModelConfig(provider="opencode-zen", model="big-pickle"),
    "grok-build-0.1":         ModelConfig(provider="opencode-zen", model="grok-build-0.1"),
}
