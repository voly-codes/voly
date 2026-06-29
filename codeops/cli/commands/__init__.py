"""CLI command groups — each module exposes a Click group or command."""
from .a2a import a2a, agui
from .infra import memory, rtk, headroom, mcp
from .platform import workflow, registry, model, ai_gateway, scan_project, match_task
from .skill import skill
from .runner import runner
from .telemetry import telemetry
from .analytics import compare, savings, balance
from .lifecycle import init, setup
from .serve_cmd import serve
from .run_cmd import run
from .status_cmd import status
from .config_cmd import config_cmd
from .tunnel import tunnel
from .spend import spend
from .catalog import catalog
from .dspy_cmd import dspy_cmd
from .ui_cmd import ui

__all__ = [
    "a2a",
    "agui",
    "memory",
    "rtk",
    "headroom",
    "mcp",
    "workflow",
    "registry",
    "model",
    "ai_gateway",
    "scan_project",
    "match_task",
    "skill",
    "runner",
    "telemetry",
    "compare",
    "savings",
    "balance",
    "init",
    "setup",
    "serve",
    "run",
    "status",
    "config_cmd",
    "tunnel",
    "spend",
    "catalog",
    "dspy_cmd",
    "ui",
]
