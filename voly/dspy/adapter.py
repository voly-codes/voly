"""
DSPy LM adapter — routes DSPy model calls through VOLY AIGateway.

Why: DSPy must NOT bypass AIGateway. Routing through it preserves:
  - Cloudflare cache (semantic + exact)
  - DLP scanning
  - Rate limiting
  - Spend limits & per-agent budgets
  - Fallback chains (e.g. claude → workers-ai → deepseek)
  - Telemetry / cost accounting

Targets DSPy 3.x BaseLM interface: forward() must return an OpenAI-compatible
response object with .choices[0].message.content and .model.
Caching is handled by AIGateway itself — DSPy-level cache is disabled.
"""

from __future__ import annotations

import logging
import types
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
            "DSPy is not installed. Run: pip install voly[dspy]  "
            "or: pip install 'dspy>=2.5.0'"
        )


def _build_openai_response(content: str, model_name: str, usage: dict[str, int]) -> Any:
    """Wrap gateway dict result as an OpenAI-compatible response for DSPy _process_completion.

    DSPy reads:
      response.choices[i].message.content  → text output
      response.model                        → model id (for history)
      dict(response.usage)                  → token counts (plain dict works)
    """
    message = types.SimpleNamespace(content=content, tool_calls=None)
    choice = types.SimpleNamespace(message=message, finish_reason="stop")
    return types.SimpleNamespace(
        choices=[choice],
        model=model_name,
        usage=usage,
    )


_BaseLM = dspy.BaseLM if _DSPY_AVAILABLE else object


class VOLYDSPyLM(_BaseLM):  # type: ignore[misc]
    """
    DSPy 3.x-compatible LM adapter backed by VOLY AIGateway.

    Usage:
        lm = VOLYDSPyLM(gateway, model="claude-sonnet-4-6", provider="anthropic", agent="reviewer")
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
        model_name = f"voly/{provider}/{model}"
        super().__init__(
            model=model_name,
            model_type="chat",
            temperature=temperature,
            max_tokens=max_tokens,
            cache=False,  # caching is done by AIGateway, not DSPy
        )
        self.gateway = gateway
        self._gw_model = model
        self._gw_provider = provider
        self.agent = agent

    # ------------------------------------------------------------------
    # DSPy 3.x BaseLM interface — forward() is the only required override
    # ------------------------------------------------------------------

    def forward(
        self,
        prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Call AIGateway and return OpenAI-compatible response object."""
        if messages is None:
            messages = [{"role": "user", "content": prompt or ""}]

        max_tokens = kwargs.pop("max_tokens", self.kwargs.get("max_tokens", 4096))
        temperature = kwargs.pop("temperature", self.kwargs.get("temperature", 0.0))

        result = self.gateway.chat(
            messages=messages,
            model=self._gw_model,
            provider_name=self._gw_provider,
            max_tokens=max_tokens,
            temperature=temperature,
            agent=self.agent,
        )

        if result.get("error"):
            raise RuntimeError(f"VOLYDSPyLM gateway error: {result['error']}")

        content = result.get("content", "")
        raw = result.get("usage", {})
        usage = {
            "prompt_tokens": raw.get("input_tokens", raw.get("prompt_tokens", 0)),
            "completion_tokens": raw.get("output_tokens", raw.get("completion_tokens", 0)),
            "total_tokens": raw.get("total_tokens", 0),
        }
        return _build_openai_response(content, self.model, usage)

    def __repr__(self) -> str:
        return f"VOLYDSPyLM(model={self.model!r}, agent={self.agent!r})"
