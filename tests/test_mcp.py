"""Tests for MCP Manager."""

from voly.tools.mcp import MCPManager, MCPServer, ToolInfo


def test_mcp_manager_builtins() -> None:
    mgr = MCPManager()
    assert "github" in mgr.BUILTIN_SERVERS
    assert "gitlab" in mgr.BUILTIN_SERVERS
    assert "postgres" in mgr.BUILTIN_SERVERS
    assert "filesystem" in mgr.BUILTIN_SERVERS
    assert "context7" in mgr.BUILTIN_SERVERS


def test_register_builtin_context7() -> None:
    mgr = MCPManager()
    server = mgr.register_builtin("context7")
    assert server.command == "npx"
    assert server.args == ["-y", "@upstash/context7-mcp"]
    assert server.env == {}


def test_register_builtin_docker_has_no_env_key() -> None:
    """Regression: BUILTIN_SERVERS["docker"] has no "env" key at all (unlike
    every other builtin) — register_builtin() used to index spec["env"]
    directly, which would have raised KeyError the first time anything
    actually called register_builtin("docker")."""
    mgr = MCPManager()
    server = mgr.register_builtin("docker")
    assert server.env == {}


def test_register_builtin() -> None:
    mgr = MCPManager()
    server = mgr.register_builtin("github")
    assert server.name == "github"
    assert "github" in mgr.list_servers()


def test_register_custom_server() -> None:
    mgr = MCPManager()
    server = MCPServer(
        name="custom-tool",
        command="npx",
        args=["-y", "custom-mcp"],
        env={"API_KEY": "test"},
    )
    mgr.register(server)
    assert "custom-tool" in mgr.list_servers()
    assert mgr.get("custom-tool") is not None


def test_unregister() -> None:
    mgr = MCPManager()
    mgr.register_builtin("github")
    assert "github" in mgr.list_servers()
    mgr.unregister("github")
    assert "github" not in mgr.list_servers()


def test_generate_claude_config() -> None:
    mgr = MCPManager()
    mgr.register_builtin("github")
    config = mgr.generate_claude_config()
    assert "mcpServers" in config
    assert "github" in config["mcpServers"]


def test_unknown_builtin() -> None:
    mgr = MCPManager()
    try:
        mgr.register_builtin("nonexistent")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown built-in" in str(e)


def test_server_to_config() -> None:
    server = MCPServer(name="test", command="echo", args=["hello"], env={"VAR": "val"})
    cfg = server.to_config()
    assert "test" in cfg
    assert cfg["test"]["command"] == "echo"
    assert cfg["test"]["args"] == ["hello"]
