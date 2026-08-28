"""CLI command groups — each module exposes a Click group or command."""
from .a2a import a2a, agui
from .analytics import balance, compare, savings
from .capability_cmd import capability_cmd
from .catalog import catalog
from .cloud_cmd import cloud
from .config_cmd import config_cmd
from .dspy_cmd import dspy_cmd
from .decide_cmd import decide_cmd
from .eval_cmd import eval_cmd
from .evidence_cmd import evidence_cmd
from .hooks_cmd import hooks_cmd
from .infra import headroom, mcp, memory, pxpipe, rtk
from .learning_cmd import learning_cmd
from .lifecycle import init, setup
from .plan_cmd import plan_cmd
from .platform import ai_gateway, match_task, model, registry, scan_project
from .quickstart import quickstart
from .repo import repo_cmd
from .research_cmd import research_cmd
from .reuse_cmd import reuse_cmd
from .run_cmd import run
from .runner import runner
from .runs_cmd import runs
from .serve_cmd import serve
from .sensing_cmd import sensing_cmd
from .skill import skill
from .spend import spend
from .status_cmd import status
from .telemetry import telemetry
from .tunnel import tunnel
from .ui_cmd import ui
from .workflow_cmd import workflow_cmd

__all__ = [
    "a2a",
    "agui",
    "memory",
    "rtk",
    "headroom",
    "hooks_cmd",
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
    "quickstart",
    "learning_cmd",
    "serve",
    "sensing_cmd",
    "run",
    "status",
    "config_cmd",
    "tunnel",
    "spend",
    "catalog",
    "cloud",
    "dspy_cmd",
    "decide_cmd",
    "evidence_cmd",
    "eval_cmd",
    "ui",
    "plan_cmd",
    "reuse_cmd",
    "repo_cmd",
    "research_cmd",
    "capability_cmd",
    "workflow_cmd",
]
