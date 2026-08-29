"""voly.sdk.tools — the explicit tool allowlist Agent(tools=[...]) resolves
against. Not an MCP client — see the module docstring for why."""

from __future__ import annotations

import pytest

from voly.sdk.tools import (
    ToolError,
    get_tool,
    list_tools,
    register_tool,
    resolve_tools,
)


def test_builtin_tools_are_registered() -> None:
    assert "current_time" in list_tools()
    assert "calculator" in list_tools()


def test_get_tool_unknown_name_raises() -> None:
    with pytest.raises(ToolError, match="unknown tool"):
        get_tool("does-not-exist")


def test_register_tool_rejects_duplicate_by_default() -> None:
    register_tool("dup_test_tool", "x", lambda: "ok", replace=True)
    with pytest.raises(ToolError, match="already registered"):
        register_tool("dup_test_tool", "x", lambda: "ok")


def test_register_tool_replace_overwrites() -> None:
    register_tool("replace_test_tool", "first", lambda: "first", replace=True)
    register_tool("replace_test_tool", "second", lambda: "second", replace=True)
    assert get_tool("replace_test_tool").description == "second"


def test_resolve_tools_is_fail_closed_on_any_unknown_name() -> None:
    register_tool("known_tool", "x", lambda: "ok", replace=True)
    with pytest.raises(ToolError):
        resolve_tools(["known_tool", "unknown_tool"])


def test_resolve_tools_returns_tool_objects_with_schema() -> None:
    register_tool("schema_test_tool", "does a thing", lambda x: x, replace=True,
                  parameters={"type": "object", "properties": {"x": {"type": "string"}}})
    [tool] = resolve_tools(["schema_test_tool"])
    schema = tool.schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "schema_test_tool"
    assert schema["function"]["description"] == "does a thing"


def test_calculator_evaluates_safely() -> None:
    calc = get_tool("calculator")
    assert calc.fn(expression="2 + 3 * 4") == "14"


def test_calculator_rejects_unsafe_expressions() -> None:
    calc = get_tool("calculator")
    with pytest.raises(ToolError):
        calc.fn(expression="__import__('os').system('echo hi')")


def test_current_time_returns_iso_utc() -> None:
    ct = get_tool("current_time")
    value = ct.fn()
    assert "T" in value  # ISO 8601 date/time separator
