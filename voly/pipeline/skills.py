"""_SkillsMixin: match_skills_for_task + match_agent_for_task."""

from __future__ import annotations

import re
from typing import Any


# Navigation/index skills that list other skills but have no executable expertise.
# Kept in sync with is_index:true flags in the catalog; this list survives catalog resyncs.
_KNOWN_INDEX_SKILL_IDS = frozenset({"engineering-skills"})

# Ultra-generic task words that let markdown/review skills match every code task.
_GENERIC_TASK_TOKENS = frozenset({
    "code", "review", "tests", "test", "testing", "write", "writing", "update",
    "changes", "implement", "implementation", "add", "create", "check", "with",
    "from", "that", "this", "have", "into", "your", "file", "files", "project",
})

# Frontend stack markers — monorepo `ui/` TypeScript must not inject these into
# backend/Python tasks unless the task itself mentions a frontend signal.
_FRONTEND_STACK = frozenset({
    "typescript", "javascript", "tsx", "jsx", "css", "html",
    "react", "nextjs", "next", "svelte", "sveltekit", "vue", "nuxt",
    "angular", "frontend", "ui", "component", "components", "dashboard",
})


def _task_keywords(task: str) -> set[str]:
    return {
        w for w in re.sub(r"[^\w\s]", "", task.lower()).split()
        if len(w) > 3 and w not in _GENERIC_TASK_TOKENS
    }


def _tokens(text: str) -> set[str]:
    """Word-boundary tokens — substring matching lets 'write' hit 'writing'."""
    return {t for t in re.split(r"[^\w]+", text.lower()) if t}


def _score_skill(
    skill: Any,
    *,
    keywords: set[str],
    agent_name: str | None,
    languages: set[str],
    frameworks: set[str],
    project_source: Any,
    curated_sources: tuple[Any, ...],
) -> float:
    """Relevance of one skill to (task, agent, project stack).

    PROJECT skills are generated from this repo's own docs — always relevant.
    Curated builtins may qualify on agent compatibility alone when they have no
    stack constraint; marketplace/org skills and stack-specific builtins need a
    concrete task or matching stack signal.
    """
    if getattr(skill, "is_index", False) or skill.id in _KNOWN_INDEX_SKILL_IDS:
        return 0.0
    if skill.source == project_source:
        return 10.0
    # Uncurated skills that name compatible agents must match the role —
    # otherwise the same top-2 markdown skills attach to every A2A role.
    agents = list(skill.compatible_agents or [])
    if (
        agent_name
        and agents
        and agent_name not in agents
        and skill.source not in curated_sources
    ):
        return 0.0
    langs = {x.lower() for x in (skill.compatible_languages or []) if x != "*"}
    fws = {x.lower() for x in (skill.compatible_frameworks or []) if x != "*"}
    tags = {x.lower() for x in (skill.tags or [])}
    caps = {x.lower() for x in (skill.capabilities or [])}
    skill_frontend = bool((langs | fws | tags | caps) & _FRONTEND_STACK)
    task_frontend = bool(keywords & _FRONTEND_STACK)
    has_specific_stack = bool(langs or fws)

    score = 0.0
    if agent_name and agent_name in agents:
        if skill.source in curated_sources and has_specific_stack:
            # skill-nextjs etc.: agent match alone must not clear the threshold
            # on a FastAPI task just because the monorepo has a ui/ folder.
            score += 0.5
        elif skill.source in curated_sources:
            score += 2.0
        else:
            score += 0.5

    def _stack_bonus(overlap: set[str]) -> float:
        if not overlap:
            return 0.0
        if skill_frontend and not task_frontend:
            return 0.0
        return 2.0

    score += _stack_bonus(langs & languages)
    score += _stack_bonus(fws & frameworks)
    hay_tokens = _tokens(
        " ".join([skill.name or "", *(skill.tags or []), *(skill.capabilities or [])])
    )
    score += min(len(keywords & hay_tokens), 3)
    if keywords & _tokens(skill.description or ""):
        score += 0.5
    return score


class _SkillsMixin:
    """Mixin for Pipeline: skill matching and agent-for-task resolution."""

    # Minimum relevance to inject a skill into a prompt. Curated builtins need
    # one concrete signal (keyword / stack / agent match). Marketplace and org
    # skills self-declare metadata and dev tasks share generic words (review,
    # tests, update…), so a single keyword hit is not enough — they need two
    # signals (two keywords, or a project language/framework match).
    SKILL_RELEVANCE_THRESHOLD = 1.0
    SKILL_RELEVANCE_THRESHOLD_UNCURATED = 2.0

    def match_skills_for_task(self, task: str, agent_name: str | None = None) -> list[Any]:
        """Return up to 10 active skills relevant for the given task.

        Candidates are gathered from installed sources, agent-specific
        built-ins, project language/framework matches, and task-keyword
        search — then **scored for relevance** and filtered: a skill must
        show at least one concrete signal for this task/stack. Installed
        marketplace/org skills are no longer unconditionally injected.
        """
        from voly.registry.skills import SkillSource

        profile = self.scan_project() if self.config.scanner.enabled else None  # type: ignore[attr-defined]
        keywords = _task_keywords(task)
        languages = {lang.name.lower() for lang in profile.languages} if profile else set()
        frameworks = {fw.name.lower() for fw in profile.frameworks} if profile else set()

        candidates: list[Any] = []

        # 1. Installed sources. PROJECT skills (generated from this repo's docs)
        #    are always relevant; MARKETPLACE / ORGANIZATION ones still have to
        #    pass relevance scoring below.
        for source in (SkillSource.PROJECT, SkillSource.MARKETPLACE, SkillSource.ORGANIZATION):
            candidates.extend(self.skill_registry.search(source=source))  # type: ignore[attr-defined]

        # 2. Agent-specific built-ins.
        if agent_name:
            candidates.extend(self.skill_registry.search(agent=agent_name))  # type: ignore[attr-defined]

        # 3. Project language / framework skills.
        if profile:
            for lang in profile.languages:
                candidates.extend(self.skill_registry.search(language=lang.name))  # type: ignore[attr-defined]
            for fw in profile.frameworks:
                candidates.extend(self.skill_registry.search(framework=fw.name))  # type: ignore[attr-defined]

        # 4. Keyword matching: split task into significant words and search each.
        for word in keywords:
            candidates.extend(self.skill_registry.search(query=word))  # type: ignore[attr-defined]

        # Deduplicate preserving discovery order, then score and filter.
        seen: set[str] = set()
        unique: list[Any] = []
        for s in candidates:
            if s.id not in seen:
                seen.add(s.id)
                unique.append(s)

        curated = (SkillSource.BUILTIN,)
        scored = [
            (
                _score_skill(
                    s,
                    keywords=keywords,
                    agent_name=agent_name,
                    languages=languages,
                    frameworks=frameworks,
                    project_source=SkillSource.PROJECT,
                    curated_sources=curated,
                ),
                i,
                s,
            )
            for i, s in enumerate(unique)
        ]
        def _threshold(s: Any) -> float:
            if s.source in curated or s.source == SkillSource.PROJECT:
                return self.SKILL_RELEVANCE_THRESHOLD
            return self.SKILL_RELEVANCE_THRESHOLD_UNCURATED

        relevant = [
            (score, i, s) for score, i, s in scored
            if score >= _threshold(s)
        ]
        relevant.sort(key=lambda t: (-t[0], t[1]))
        return [s for _, _, s in relevant[:10]]

    def match_agent_for_task(self, task: str) -> dict[str, Any]:
        route = self.router.route(task)  # type: ignore[attr-defined]
        agent_def = self.agent_registry.get(route.agent)  # type: ignore[attr-defined]

        if agent_def:
            model_name = agent_def.preferred_model or route.model
        else:
            category = self.model_router._infer_category(task)  # type: ignore[attr-defined]
            model_info = self.model_router.route(category=category)  # type: ignore[attr-defined]
            model_name = model_info.name

        return {
            "agent": route.agent,
            "agent_def": agent_def,
            "model": model_name,
            "provider": route.provider,
            "skills": self.match_skills_for_task(task, route.agent),
            "tools": route.tools,
        }
