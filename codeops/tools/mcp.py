"""
MCP Manager — управление MCP серверами и инструментами.

Model Context Protocol (MCP) — стандартный протокол для подключения
инструментов к AI-агентам.

CodeOps использует MCP First подход: все инструменты подключаются
через MCP, обеспечивая единый интерфейс для любого агента.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolInfo:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    server: str = ""


@dataclass
class MCPServer:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[ToolInfo] = field(default_factory=list)

    def to_config(self) -> dict[str, Any]:
        return {
            self.name: {
                "command": self.command,
                "args": self.args,
                "env": self.env,
            }
        }


class MCPManager:
    BUILTIN_SERVERS: dict[str, dict[str, Any]] = {
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
        },
        "gitlab": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gitlab"],
            "env": {"GITLAB_PERSONAL_ACCESS_TOKEN": "${GITLAB_TOKEN}"},
        },
        "postgres": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres"],
            "env": {"DATABASE_URL": "${DATABASE_URL}"},
        },
        "docker": {
            "command": "docker",
            "args": ["run", "-i", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock", "mcp/docker"],
        },
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/"],
            "env": {},
        },
    }

    def __init__(self):
        self._servers: dict[str, MCPServer] = {}

    def register_builtin(self, name: str) -> MCPServer:
        if name not in self.BUILTIN_SERVERS:
            raise ValueError(f"Unknown built-in MCP server: {name}. Available: {list(self.BUILTIN_SERVERS)}")
        spec = self.BUILTIN_SERVERS[name]
        server = MCPServer(name=name, command=spec["command"], args=spec["args"], env=spec["env"])
        self._servers[name] = server
        return server

    def register(self, server: MCPServer) -> None:
        self._servers[server.name] = server

    def unregister(self, name: str) -> None:
        self._servers.pop(name, None)

    def get(self, name: str) -> MCPServer | None:
        return self._servers.get(name)

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    def list_tools(self) -> dict[str, list[ToolInfo]]:
        return {name: server.tools for name, server in self._servers.items()}

    def generate_claude_config(self) -> dict[str, Any]:
        result: dict[str, Any] = {"mcpServers": {}}
        for server in self._servers.values():
            result["mcpServers"].update(server.to_config())
        return result

    def generate_opencode_config(self) -> dict[str, Any]:
        result: dict[str, Any] = {"mcpServers": {}}
        for server in self._servers.values():
            result["mcpServers"].update(server.to_config())
        return result

    def health_check(self, name: str, timeout: int = 10) -> bool:
        server = self._servers.get(name)
        if not server:
            return False
        try:
            result = subprocess.run(
                [server.command, *server.args, "--version"],
                capture_output=True,
                timeout=timeout,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
