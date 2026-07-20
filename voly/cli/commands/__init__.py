"""CLI command groups — each module exposes a Click group or command."""
from .a2a import a2a, agui
from .infra import memory, rtk, headroom, pxpipe, mcp
from .platform import registry, model, ai_gateway, scan_project, match_task
from .skill import skill
from .runner import runner
from .telemetry import telemetry
from .runs_cmd import runs
from .analytics import compare, savings, balance
from .lifecycle import init, setup
from .serve_cmd import serve
from .run_cmd import run
from .status_cmd import status
from .config_cmd import config_cmd
from .tunnel import tunnel
from .spend import spend
from .catalog import catalog
from .cloud_cmd import cloud
from .dspy_cmd import dspy_cmd
from .ui_cmd import ui
from .plan_cmd import plan_cmd
from .reuse_cmd import reuse_cmd
from .repo import repo_cmd

__all__ = [
    "a2a",
    "agui",
    "memory",
    "rtk",
    "headroom",
    "pxpipe",
    "mcp",
    "registry",
    "model",
    "ai_gateway",
    "scan_project",
    "match_task",
    "skill",
    "runner",
    "telemetry",
    "runs",
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
    "cloud",
    "dspy_cmd",
    "ui",
    "plan_cmd",
    "reuse_cmd",
    "repo_cmd",
]
