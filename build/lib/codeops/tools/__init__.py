"""
Tool Layer — абстракция для доступа к внешним инструментам через MCP.

Поддерживает:
    - GitHub / GitLab API
    - Jira / Confluence / Wiki.js
    - PostgreSQL
    - Docker / Kubernetes
    - Temporal
    - Cloudflare
"""

from codeops.tools.mcp import MCPManager, MCPServer, ToolInfo

__all__ = ["MCPManager", "MCPServer", "ToolInfo"]
