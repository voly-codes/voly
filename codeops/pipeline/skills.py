"""_SkillsMixin: match_skills_for_task + match_agent_for_task."""

from __future__ import annotations

import re
from typing import Any


class _SkillsMixin:
    """Mixin for Pipeline: skill matching and agent-for-task resolution."""

    def match_skills_for_task(self, task: str, agent_name: str | None = None) -> list[Any]:
        """Return up to 10 active skills relevant for the given task.

        Matching priority:
        1. Marketplace / organization skills the user explicitly installed — always included.
        2. Agent-specific skills (compatible_agents contains agent_name).
        3. Language / framework skills from the project profile (if scanner enabled).
        4. Keyword-level text match against skill name / description / tags / capabilities.
        """
        from codeops.registry.skills import SkillSource

        profile = self.scan_project() if self.config.scanner.enabled else None  # type: ignore[attr-defined]
        skills: list[Any] = []

        # 1. Project / marketplace / org skills — always included.
        #    PROJECT: generated from this project's docs (CLAUDE.md, README, etc.) → always relevant.
        #    MARKETPLACE / ORGANIZATION: explicitly installed by the user → explicit intent to use.
        for source in (SkillSource.PROJECT, SkillSource.MARKETPLACE, SkillSource.ORGANIZATION):
            skills.extend(self.skill_registry.search(source=source))  # type: ignore[attr-defined]

        # 2. Agent-specific built-ins.
        if agent_name:
            skills.extend(self.skill_registry.search(agent=agent_name))  # type: ignore[attr-defined]

        # 3. Project language / framework skills.
        if profile:
            for lang in profile.languages:
                skills.extend(self.skill_registry.search(language=lang.name))  # type: ignore[attr-defined]
            for fw in profile.frameworks:
                skills.extend(self.skill_registry.search(framework=fw.name))  # type: ignore[attr-defined]

        # 4. Keyword matching: split task into significant words and search each.
        keywords = [w for w in re.sub(r"[^\w\s]", "", task.lower()).split() if len(w) > 3]
        for word in keywords:
            skills.extend(self.skill_registry.search(query=word))  # type: ignore[attr-defined]

        # Deduplicate preserving priority order.
        seen: set[str] = set()
        unique: list[Any] = []
        for s in skills:
            if s.id not in seen:
                seen.add(s.id)
                unique.append(s)

        return unique[:10]

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
