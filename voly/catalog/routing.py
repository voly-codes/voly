"""Route combat steps to executor + Zen model with free-tier fallback."""

from __future__ import annotations

import re

from voly.catalog.store import load_models
from voly.catalog.types import CatalogModel, MissionStepSpec

FREE_REVIEW_MODEL = "deepseek-v4-flash-free"
FREE_I18N_MODEL = "mimo-v2.5-free"
FREE_AUDIT_MODEL = "nemotron-3-ultra-free"

DEFAULT_MODEL_BY_EXECUTOR: dict[str, str] = {
    "cursor": "composer-2.5",
    "opencode": "kimi-k2.6",
    "zen": "claude-sonnet-4-6",
    "deepseek": "deepseek-v4-flash",
    "mimo": "mimo-v2.5-free",
}

PLANE_ISSUES_PLAN: list[MissionStepSpec] = [
    MissionStepSpec(
        executor="opencode",
        model="deepseek-v4-pro",
        agent_role="developer",
        skills=["smarty-backend-api"],
        free_fallback_model="deepseek-v4-flash-free",
    ),
    MissionStepSpec(
        executor="opencode",
        model="kimi-k2.6",
        agent_role="developer",
        skills=["plane-design-system", "component-patterns", "smarty-backend-api"],
    ),
    MissionStepSpec(
        executor="cursor",
        model="composer-2.5",
        agent_role="developer",
        skills=["plane-design-system", "component-patterns"],
    ),
    MissionStepSpec(
        executor="opencode",
        model="gpt-5.4-mini",
        agent_role="developer",
        skills=["plane-design-system"],
    ),
    MissionStepSpec(
        executor="cursor",
        model="composer-2.5",
        agent_role="developer",
        skills=["plane-design-system", "component-patterns"],
    ),
    MissionStepSpec(
        executor="opencode",
        model="deepseek-v4-pro",
        agent_role="developer",
        skills=["plane-design-system"],
    ),
    MissionStepSpec(
        executor="opencode",
        model="kimi-k2.6",
        agent_role="developer",
        skills=["plane-design-system", "ux-copy"],
    ),
    MissionStepSpec(
        executor="zen",
        model=FREE_REVIEW_MODEL,
        agent_role="reviewer",
        skills=["design-critique"],
        readonly=True,
        free_fallback_model=FREE_AUDIT_MODEL,
    ),
]

MISSION_PLANS: dict[str, list[MissionStepSpec]] = {
    "plane-issues": PLANE_ISSUES_PLAN,
}


def _catalog_index(base=None) -> dict[str, CatalogModel]:
    return {m.id: m for m in load_models(base)}


def resolve_model(
    executor: str,
    preferred: str,
    *,
    catalog_base=None,
    prefer_free: bool = False,
) -> str:
    idx = _catalog_index(catalog_base)
    if prefer_free:
        for mid in (FREE_REVIEW_MODEL, FREE_I18N_MODEL, FREE_AUDIT_MODEL):
            m = idx.get(mid)
            if m and m.enabled and executor in m.executor_compat:
                return mid
            if not idx and mid:
                return mid
        for m in idx.values():
            if m.tier == "free" and m.enabled and executor in m.executor_compat:
                return m.id
        return FREE_REVIEW_MODEL if executor == "zen" else DEFAULT_MODEL_BY_EXECUTOR.get(executor, preferred)

    m = idx.get(preferred)
    if m and m.enabled:
        return preferred
    return DEFAULT_MODEL_BY_EXECUTOR.get(executor, preferred)


def match_task(
    task: str,
    *,
    executor_hint: str | None = None,
    catalog_base=None,
) -> tuple[str, str]:
    """Return (executor, model) for ad-hoc task text."""
    text = task.lower()
    if executor_hint:
        ex = executor_hint
    elif re.search(r"\breview\b|\baudit\b|\bchecklist\b|do not edit", text):
        ex = "zen"
    elif re.search(r"\bbackend\b|\bapi\b|\broutes\b|smarty-tracker", text):
        ex = "opencode"
    elif re.search(r"\btsx\b|\breact\b|\btailwind\b|\bui\b|\bkanban\b", text):
        ex = "cursor"
    else:
        ex = "opencode"

    if ex == "zen":
        model = FREE_REVIEW_MODEL if re.search(r"\breview\b|\baudit\b|\bchecklist\b", text) else "claude-sonnet-4-6"
    elif ex == "cursor":
        model = "composer-2.5"
    elif "backend" in text:
        model = "deepseek-v4-pro"
    elif "calendar" in text or "gantt" in text or "spreadsheet" in text:
        model = "gpt-5.4-mini"
    else:
        model = "kimi-k2.6"

    model = resolve_model(ex, model, catalog_base=catalog_base, prefer_free=ex == "zen" and "review" in text)
    return ex, model


def get_mission_plan(mission_id: str) -> list[MissionStepSpec]:
    return list(MISSION_PLANS.get(mission_id, []))
