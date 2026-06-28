"""
DSPy LM adapter — routes DSPy model calls through CodeOps AIGateway.

Why: DSPy must NOT bypass AIGateway.  Routing through it preserves:
  - Cloudflare cache (semantic + exact)
  - DLP scanning
  - Rate limiting
  - Spend limits & per-agent budgets
  - Fallback chains (e.g. claude → gpt-4o → deepseek)
  - Telemetry / cost accounting

The adapter conforms to the DSPy BaseLM interface used by dspy.configure(lm=...).
It implements __call__ (legacy) and supports the forward() / generate() patterns.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DSPY_AVAILABLE = False
try:
    import dspy  # noqa: F401

    _DSPY_AVAILABLE = True
except ImportError:
    pass


def _require_dspy() -> None:
    if not _DSPY_AVAILABLE:
        raise ImportError(
            "DSPy is not installed. Run: pip install codeops[dspy]  "
            "or: pip install 'dspy>=2.5.0'"
        )


class CodeOpsDSPyLM:
    """
    DSPy-compatible LM adapter backed by CodeOps AIGateway.

    Usage:
        lm = CodeOpsDSPyLM(gateway, model="claude-sonnet", provider="anthropic", agent="reviewer")
        dspy.configure(lm=lm)
    """

    def __init__(
        self,
        gateway: Any,
        model: str,
        provider: str,
        agent: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> None:
        _require_dspy()
        self.gateway = gateway
        self.model = model
        self.provider = provider
        self.agent = agent
        self.max_tokens = max_tokens
        self.temperature = temperature

        # DSPy >= 2.5 uses `model` attribute on LM objects for identification
        self._model_name = f"codeops/{provider}/{model}"

    # ------------------------------------------------------------------
    # DSPy BaseLM interface
    # ------------------------------------------------------------------

    def __call__(
        self,
        prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """DSPy calls LM with either a prompt string or messages list."""
        if messages is None:
            if prompt is None:
                raise ValueError("CodeOpsDSPyLM: either prompt or messages must be provided")
            messages = [{"role": "user", "content": prompt}]

        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        temperature = kwargs.pop("temperature", self.temperature)

        result = self.gateway.chat(
            messages=messages,
            model=self.model,
            provider_name=self.provider,
            max_tokens=max_tokens,
            temperature=temperature,
            agent=self.agent,
        )
        content = result.get("content", "")
        return [content]

    # DSPy >= 2.5 forward() signature
    def forward(
        self,
        prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> Any:
        _require_dspy()
        import dspy

        completions = self.__call__(prompt=prompt, messages=messages, **kwargs)

        # Wrap in dspy.Prediction-compatible structure
        return dspy.Prediction(completions=completions)

    # ------------------------------------------------------------------
    # Metadata helpers used by DSPy internals
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"CodeOpsDSPyLM(model={self._model_name!r}, agent={self.agent!r})"

    @property
    def model_type(self) -> str:
        return "chat"
