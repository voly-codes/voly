"""Explicit tool allowlist for ``Agent(tools=[...])``.

``Agent.tools`` is a ``list[str]`` of *names*, not raw callables — resolving
each name against this module's registry at construction time is the
"explicit allowlist" the proposal calls for (docs/proposals/
agent-workflow-sdk.md's non-goal list bans "arbitrary Python object
serialization"; a name that must already be registered is exactly the
opposite of accepting an arbitrary callable off the wire). An unregistered
name raises immediately (fail-closed) rather than being silently dropped or
resolved lazily at run time.

The tool-call loop that consumes these schemas
(``Agent._run_chat``'s bounded tool loop) follows the same shape already
proven in ``voly.a2a.agentic_judge.AgenticJudgeAgent``: OpenAI-style
``{"type": "function", "function": {...}}`` schemas passed to
``AIGateway.chat(tools=...)`` (already wired end-to-end at the transport
layer for Anthropic/OpenAI/Google — see ``voly/ai_gateway/providers.py``),
tool results fed back as a plain user message, bounded by a max step count.

This is **not** a Model Context Protocol (MCP) client — no JSON-RPC, no
subprocess server, no ``list_tools``/``call_tool`` wire protocol. See
``voly/tools/mcp.py::MCPManager`` for VOLY's actual MCP integration, which
generates ``.mcp.json`` configs for CLI executors (claude-code, opencode) to
consume themselves; it has no synchronous "call a tool, get a result"
primitive a chat-mode loop could reuse. Building a real MCP client is future
work, tracked as example 9's gap in ``examples/workflows/README.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class ToolError(ValueError):
    """Raised for tool registration/resolution usage errors."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    fn: Callable[..., Any] = field(default=None, repr=False)  # type: ignore[assignment]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, Tool] = {}


def register_tool(
    name: str,
    description: str,
    fn: Callable[..., Any],
    *,
    parameters: dict[str, Any] | None = None,
    replace: bool = False,
) -> Tool:
    """Register a tool under ``name``. Raises ``ToolError`` on a duplicate
    name unless ``replace=True`` (tests may need to redefine a tool)."""
    if not name or not name.strip():
        raise ToolError("tool name is required")
    if name in _REGISTRY and not replace:
        raise ToolError(f"tool already registered: {name!r}")
    tool = Tool(
        name=name,
        description=description,
        parameters=parameters or {"type": "object", "properties": {}},
        fn=fn,
    )
    _REGISTRY[name] = tool
    return tool


def get_tool(name: str) -> Tool:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ToolError(
            f"unknown tool: {name!r} — not registered in voly.sdk.tools "
            "(the explicit allowlist Agent(tools=[...]) resolves against)"
        ) from None


def resolve_tools(names: list[str]) -> list[Tool]:
    """Resolve an explicit allowlist of tool names. Fails closed: any
    unregistered name raises immediately rather than being dropped."""
    return [get_tool(name) for name in names]


def list_tools() -> list[str]:
    return sorted(_REGISTRY)


# ── Built-in example tools ──────────────────────────────────────────────────
# Deliberately minimal and side-effect-free (read-only / pure), matching the
# proposal's "safe defaults" design principle: registering does not mean an
# Agent uses them — a caller still opts in per-Agent via `tools=[...]`.


def _current_time(timezone: str = "UTC") -> str:
    import datetime

    if timezone.upper() != "UTC":
        raise ToolError("current_time only supports UTC in this offline-safe build")
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _calculator(expression: str) -> str:
    """Evaluate a numeric expression using Python's ast — no builtins, no names."""
    import ast
    import operator

    ops = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
        ast.Mod: operator.mod,
    }

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](_eval(node.operand))
        raise ToolError(f"unsupported expression: {ast.dump(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval(tree.body))
    except (SyntaxError, ToolError, ZeroDivisionError) as exc:
        raise ToolError(f"invalid expression {expression!r}: {exc}") from exc


register_tool(
    "current_time",
    "Return the current UTC time in ISO 8601 format.",
    _current_time,
    parameters={
        "type": "object",
        "properties": {"timezone": {"type": "string", "description": "Must be 'UTC'."}},
    },
)
register_tool(
    "calculator",
    "Evaluate a numeric arithmetic expression (+ - * / % **); no names or calls.",
    _calculator,
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
)
