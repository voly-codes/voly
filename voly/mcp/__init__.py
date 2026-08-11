"""MCP server exposing VOLY as an orchestrator to any MCP client.

Not to be confused with `voly.tools.mcp`, which is the *client* side — the
manager for MCP servers that VOLY's own agents consume. This package is the
other direction: it lets Cloudflare OS, Claude Desktop, or any MCP host drive
VOLY runs.

Requires the `mcp` extra: `pip install -e ".[mcp]"`.
"""

from __future__ import annotations

__all__ = ["build_server"]


def build_server(*args, **kwargs):  # type: ignore[no-untyped-def]
    """Lazy re-export so importing this package never requires the MCP SDK."""
    from voly.mcp.server import build_server as _build

    return _build(*args, **kwargs)
