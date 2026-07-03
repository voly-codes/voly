"""
DSPy Modules for VOLY agents.

Each Module wraps a Signature with a reasoning strategy:
  - Predict:        direct answer
  - ChainOfThought: step-by-step reasoning before answer
  - ReAct:          reasoning + tool use loop

Design:
  - Modules are constructed lazily (dspy import guarded).
  - build_module(agent, strategy) → dspy.Module instance
  - Default strategy per agent reflects risk profile:
      reviewer    → ChainOfThought (need to reason about code)
      documenter  → Predict        (low risk, structured output)
      architect   → ChainOfThought (complex reasoning)
      bugfixer    → ChainOfThought (trace root cause)
      router      → Predict        (fast, low latency)
"""

from __future__ import annotations

from typing import Any

_DSPY_AVAILABLE = False
try:
    import dspy  # noqa: F401
    _DSPY_AVAILABLE = True
except ImportError:
    pass


def _require_dspy() -> None:
    if not _DSPY_AVAILABLE:
        raise ImportError("DSPy is not installed. Run: pip install codeops[dspy]")


# Default strategy per agent
_AGENT_STRATEGY: dict[str, str] = {
    "reviewer": "chain_of_thought",
    "architect": "chain_of_thought",
    "bugfixer": "chain_of_thought",
    "documenter": "predict",
    "router": "predict",
    "tester": "chain_of_thought",
    "security": "chain_of_thought",
    "devops": "chain_of_thought",
    "developer": "chain_of_thought",
}


def build_module(agent: str, strategy: str | None = None) -> Any:
    """
    Build a DSPy Module for the given agent.

    Args:
        agent:    VOLY agent name (reviewer, documenter, architect, bugfixer, …)
        strategy: override strategy (predict | chain_of_thought)

    Returns:
        dspy.Module instance ready for forward() calls
    """
    _require_dspy()
    import dspy
    from codeops.dspy.signatures import AGENT_SIGNATURES, ROUTING_SIGNATURE

    if agent == "router":
        sig = ROUTING_SIGNATURE()
    elif agent in AGENT_SIGNATURES:
        sig = AGENT_SIGNATURES[agent]()
    else:
        # Generic fallback: use documenter signature
        sig = AGENT_SIGNATURES.get("documenter", ROUTING_SIGNATURE)()

    effective_strategy = strategy or _AGENT_STRATEGY.get(agent, "predict")

    if effective_strategy == "chain_of_thought":
        return dspy.ChainOfThought(sig)
    else:
        return dspy.Predict(sig)


class VOLYModule:
    """
    Thin wrapper around a DSPy Module that carries agent metadata
    and exposes a uniform call interface for the DSPyRunner.

    Attributes:
        agent:   VOLY agent name
        module:  underlying dspy.Module (Predict / ChainOfThought)
    """

    def __init__(self, agent: str, strategy: str | None = None) -> None:
        _require_dspy()
        self.agent = agent
        self.module = build_module(agent, strategy)

    def __call__(self, **kwargs: Any) -> Any:
        """Forward call — kwargs are Signature InputFields."""
        return self.module(**kwargs)

    def __repr__(self) -> str:
        return f"VOLYModule(agent={self.agent!r}, module={self.module!r})"
