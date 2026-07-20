"""Pipeline types: PipelineStage, PipelineResult, PipelineMetrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelineStage(Enum):
    INIT = "init"
    REPO_INTELLIGENCE = "repo_intelligence"
    AGUI_START = "agui_start"
    A2A_DISCOVER = "a2a_discover"
    A2A_DELEGATE = "a2a_delegate"
    ROUTE = "route"
    MEMORY_RETRIEVE = "memory_retrieve"
    RTK_FILTER = "rtk_filter"
    SKILL_SUGGEST = "skill_suggest"
    SKILL_INJECT = "skill_inject"
    HEADROOM_COMPRESS = "headroom_compress"
    DSPY_PROGRAM_CALL = "dspy_program_call"
    MODEL_CALL = "model_call"
    MEMORY_STORE = "memory_store"
    AGUI_DONE = "agui_done"
    DONE = "done"
    ERROR = "error"


@dataclass
class PipelineResult:
    success: bool
    stage: PipelineStage
    response: Any = None
    route: Any = None
    analysis: Any = None
    memory_hits: list = field(default_factory=list)
    tokens_saved_by_rtk: int = 0
    tokens_saved_by_headroom: int = 0
    duration_ms: float = 0.0
    a2a_tasks: list = field(default_factory=list)
    agui_session_id: str = ""
    error: str = ""
    injected_skills: list[str] = field(default_factory=list)
    skill_suggestions: list[dict] = field(default_factory=list)
    event: Any = None
    dspy_used: bool = False
    dspy_mode: str = ""
    dspy_program_id: str | None = None
    dspy_program_version: int | None = None
    dspy_program_tag: str | None = None
    dspy_optimizer: str | None = None
    dspy_dataset: str | None = None
    dspy_compile_id: str | None = None
    dspy_score: float | None = None
    dspy_shadow_delta: float | None = None


@dataclass
class PipelineMetrics:
    total_tasks: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_tokens_saved_rtk: int = 0
    total_tokens_saved_headroom: int = 0
    avg_duration_ms: float = 0.0
    route_distribution: dict[str, int] = field(default_factory=dict)
