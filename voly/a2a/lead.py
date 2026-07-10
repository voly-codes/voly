"""Lead orchestrator: a strong model assigns a tier + skills to each sub-agent.

Used by the pipeline's A2A auto-dispatch — ``LeadOrchestrator.assign()`` asks a
strong model for a plan and falls back to the deterministic role→tier map
(``assignment._ROLE_TIER``) when the lead call fails.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from voly.a2a.assignment import (
    _ROLE_TIER,
    _VALID_TIERS,
    Assignment,
    resolve_tier_model,
)
from voly.ai_gateway.health import get_checker
from voly.router import _PROVIDER_MODELS

_log = logging.getLogger("voly.a2a.multiagent")


class LeadOrchestrator:
    """Strong lead agent that assigns a model tier + skills to each sub-agent."""

    def __init__(
        self,
        gateway: Any,
        skill_matcher: Callable[[str, str], list[Any]] | None = None,
        checker: Any = None,
        lead_model: str = "",
    ):
        self.gateway = gateway
        self.skill_matcher = skill_matcher
        self.checker = checker or get_checker()
        self.lead_model = lead_model

    def _candidate_skills(self, task: str, role: str) -> list[tuple[str, str]]:
        """Return [(skill_id, name)] candidates for a role, from the registry."""
        if not self.skill_matcher:
            return []
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for s in self.skill_matcher(task, role)[:6]:
            sid = getattr(s, "id", "")
            if sid and sid not in seen:
                seen.add(sid)
                out.append((sid, getattr(s, "name", sid)))
        return out

    def assign(self, task: str, subtasks: list[Any]) -> list[Assignment]:
        """Produce an Assignment per sub-task. LLM-lead first, deterministic fallback."""
        skill_candidates = {
            i: self._candidate_skills(task, st.agent) for i, st in enumerate(subtasks)
        }
        plan = self._ask_lead(task, subtasks, skill_candidates)
        assignments: list[Assignment] = []
        for i, st in enumerate(subtasks):
            entry = plan.get(i, {}) if plan else {}
            tier = entry.get("tier") or _ROLE_TIER.get(st.agent, "standard")
            if tier not in _VALID_TIERS:
                tier = _ROLE_TIER.get(st.agent, "standard")
            valid_ids = {sid for sid, _ in skill_candidates[i]}
            skills = [s for s in entry.get("skills", []) if s in valid_ids]
            if not skills:
                skills = [sid for sid, _ in skill_candidates[i][:2]]
            model, provider = resolve_tier_model(tier, self.checker)
            assignments.append(Assignment(
                idx=i, role=st.agent, description=st.description,
                depends_on=list(getattr(st, "depends_on", [])),
                tier=tier, model=model, provider=provider, skills=skills,
                execution=entry.get("execution") or "",
            ))
        return assignments

    def _ask_lead(
        self, task: str, subtasks: list[Any], skill_candidates: dict[int, list[tuple[str, str]]]
    ) -> dict[int, dict[str, Any]]:
        """Call a strong model to assign tier + skills. Returns {idx: {tier, skills}}."""
        model, provider = (
            (self.lead_model, _provider_for_model(self.lead_model))
            if self.lead_model else resolve_tier_model("premium", self.checker)
        )
        roles_block = "\n".join(
            f"{i}. role={st.agent}; task={st.description[:160]}; "
            f"skills_available={[sid for sid, _ in skill_candidates[i]] or 'none'}"
            for i, st in enumerate(subtasks)
        )
        system = (
            "Ты lead-оркестратор. Для каждой суб-задачи назначь уровень модели (tier) и "
            "релевантные скилы. Критерии: сложное проектирование/ревью/безопасность → "
            "'premium'; обычная реализация → 'standard'; рутинные тесты/деплой/батч → 'cheap'. "
            "Скилы выбирай ТОЛЬКО из skills_available каждой роли (можно пусто). "
            "Опционально задай execution: 'executor' если роль должна писать файлы "
            "в проекте, 'chat' если достаточно текста; не уверен — опусти поле. "
            "Ответь СТРОГО JSON-массивом без пояснений: "
            '[{"idx":0,"tier":"premium","skills":["id1"],"execution":"chat"}, ...]'
        )
        user = f"Задача: {task}\n\nСуб-задачи:\n{roles_block}"
        try:
            resp = self.gateway.chat(
                [{"role": "user", "content": user}],
                model=model, provider_name=provider, system=system,
                agent="lead", max_tokens=1024, temperature=0.0,
            )
            content = resp.get("content", "") or ""
            if resp.get("error"):
                _log.warning("lead orchestrator error, using deterministic fallback: %s", resp["error"])
                return {}
            return _parse_plan(content)
        except Exception as e:  # noqa: BLE001 — fall back to deterministic assignment
            _log.warning("lead orchestrator call failed (%s), deterministic fallback", e)
            return {}


def _parse_plan(content: str) -> dict[int, dict[str, Any]]:
    """Extract the JSON array from the lead response into {idx: {tier, skills, execution}}."""
    start, end = content.find("["), content.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        arr = json.loads(content[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    plan: dict[int, dict[str, Any]] = {}
    for item in arr if isinstance(arr, list) else []:
        if isinstance(item, dict) and "idx" in item:
            try:
                execution = str(item.get("execution") or "").strip().lower()
                plan[int(item["idx"])] = {
                    "tier": item.get("tier"),
                    "skills": item.get("skills", []) if isinstance(item.get("skills"), list) else [],
                    "execution": execution if execution in ("chat", "executor") else "",
                }
            except (TypeError, ValueError):
                continue
    return plan


def _provider_for_model(model: str) -> str:
    for _model, provider in _PROVIDER_MODELS.values():
        if _model == model:
            return provider
    return "anthropic"
