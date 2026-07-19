"""Local multi-agent execution: a strong lead orchestrator assigns a model tier
and skills to each decomposed sub-agent, then each sub-agent runs in-process
through ``AIGateway.chat()``.

Flow (used by the pipeline's A2A auto-dispatch when ``a2a.execution_mode == 'local'``):

    task → TaskDecomposer → [architect, developer, tester, reviewer, devops]
         → LeadOrchestrator.assign()   # strong model picks tier + skills per role
         → run_local()                 # each role → AIGateway.chat(model=tier, skills)
         → per-agent results + merged report + telemetry assignments

The model pool is the set of *real* configured providers (``router._PROVIDER_MODELS``)
filtered by ``ProviderHealthChecker`` — strong = anthropic/claude, weak = the free/cheap
providers (workers-ai, deepseek, opencode-zen, mimo, omniroute).

Implementation of ``run_local`` lives in ``multiagent_run.py`` (``_LocalRun``);
this module keeps the stable public import surface.
"""
from __future__ import annotations

# Re-exported for backward compatibility — external callers import these from
# voly.a2a.multiagent (pipeline/stages.py, telemetry, tests).
from voly.a2a.assignment import (
    Assignment,
    apply_env_provider_exclusions,
    chat_fallback_providers,
    evaluate_multiagent_outcome,
    exclude_provider_on_gateway_error as _exclude_provider_on_gateway_error,
    resolve_tier_model,
)  # noqa: F401
from voly.a2a.chat_fallback import chat_with_provider_fallback
from voly.a2a.context import (
    DEFAULT_PERSONA,
    ROLE_PROMPT,
    delta_for_role,
    git_diff_evidence,
    memory_block,
    project_context_block,
    skills_block,
)
from voly.a2a.hybrid import resolve_role_executor  # noqa: F401
from voly.a2a.lead import LeadOrchestrator, _parse_plan  # noqa: F401
from voly.a2a.multiagent_run import run_local  # noqa: F401
from voly.a2a.report import merge_report  # noqa: F401
from voly.a2a.waves import build_waves

# Back-compat aliases for tests / external imports.
_build_waves = build_waves
_chat_with_provider_fallback = chat_with_provider_fallback
_git_diff_evidence = git_diff_evidence
_delta_for_role = delta_for_role
_project_context_block = project_context_block
_skills_block = skills_block
_memory_block = memory_block
_ROLE_PROMPT = ROLE_PROMPT
_DEFAULT_PERSONA = DEFAULT_PERSONA

__all__ = [
    "Assignment",
    "LeadOrchestrator",
    "merge_report",
    "run_local",
]
