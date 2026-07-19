"""Memory, Headroom, RTK, and skill pipeline stage implementations."""

from __future__ import annotations

from typing import Any

from voly.pipeline.types import PipelineStage


class _ContextStageMixin:
    """Mixin: memory / headroom / RTK / skill suggest+inject stages."""

    def _stage_memory_retrieve(self, task: str) -> list[dict[str, Any]]:
        if not self.config.memory.enabled:  # type: ignore[attr-defined]
            return []
        memory_results = self.memory.search(task, limit=5)  # type: ignore[attr-defined]
        messages = [
            {"role": "user", "content": f"[MEMORY: {m.category}] {m.title}: {m.content}"}
            for m in memory_results
        ]
        self._fire(PipelineStage.MEMORY_RETRIEVE, hits=memory_results)  # type: ignore[attr-defined]
        return messages

    def _stage_memory_store(self, task: str, response: Any, route: Any) -> None:
        self.memory.add(  # type: ignore[attr-defined]
            title=f"Task: {task[:100]}",
            content=response.content[:2000],
            category="history",
            metadata={"agent": route.agent, "model": route.model, "provider": route.provider},
            importance=0.6,
            tags=[route.agent, "task"],
        )
        self._fire(PipelineStage.MEMORY_STORE)  # type: ignore[attr-defined]

    def _stage_headroom_compress(
        self, messages: list[dict[str, Any]], model: str
    ) -> tuple[list[dict[str, Any]], int]:
        """Compress messages via Headroom when it's running. Returns (messages, tokens_saved)."""
        mgr = getattr(self, "headroom_mgr", None)
        if mgr is None or not mgr.is_running():
            self._fire(PipelineStage.HEADROOM_COMPRESS, messages=messages, tokens_saved=0)  # type: ignore[attr-defined]
            return messages, 0
        try:
            result = mgr.compress(messages, model=model)
            compressed = result.get("messages", messages)
            saved = result.get("tokens_saved", 0)
            self._fire(PipelineStage.HEADROOM_COMPRESS, messages=compressed, tokens_saved=saved)  # type: ignore[attr-defined]
            return compressed, saved
        except Exception:
            self._fire(PipelineStage.HEADROOM_COMPRESS, messages=messages, tokens_saved=0)  # type: ignore[attr-defined]
            return messages, 0

    def _stage_rtk(self) -> dict[str, Any]:
        if self.config.rtk.enabled and self.rtk.is_installed():  # type: ignore[attr-defined]
            stats = self.rtk.get_stats(scope="project")  # type: ignore[attr-defined]
            self._fire(PipelineStage.RTK_FILTER, stats=stats)  # type: ignore[attr-defined]
            return stats
        return {}

    def _stage_skill_suggest(self, task: str) -> list[dict]:
        """Query marketplace for skills relevant to task that are not installed locally.

        Non-blocking: any error is swallowed and an empty list is returned so the
        pipeline never fails because of a marketplace connectivity issue.
        Emits SKILL_SUGGEST with the suggestions list for the UI to handle.
        """
        marketplace_url = getattr(
            getattr(self.config, "registry", None), "marketplace_url", ""  # type: ignore[attr-defined]
        ) or ""
        if not marketplace_url:
            return []

        try:
            from voly.registry.scout import SkillScout
            scout = SkillScout(self.skill_registry, marketplace_url)  # type: ignore[attr-defined]
            suggestions = scout.find_missing(task)
        except Exception:
            return []

        if suggestions:
            self._fire(PipelineStage.SKILL_SUGGEST, suggestions=suggestions)  # type: ignore[attr-defined]

        return suggestions

    def _stage_skill_inject(
        self, task: str, agent_name: str | None
    ) -> tuple[list[str], str]:
        """Match installed skills and build a system-prompt block.

        Returns (skill_ids, prompt_addition). Both empty when nothing matches.
        """
        skills = self.match_skills_for_task(task, agent_name)  # type: ignore[attr-defined]
        skills_with_content = [s for s in skills if s.content and s.content.strip()]

        if not skills_with_content:
            self._fire(PipelineStage.SKILL_INJECT, skill_ids=[], injected=0)  # type: ignore[attr-defined]
            return [], ""

        lines: list[str] = ["# Loaded skills\n"]
        for skill in skills_with_content:
            lines.append(f"### {skill.name} ({skill.id})")
            lines.append(skill.content.strip()[:4000])
            lines.append("")

        block = "\n".join(lines).strip()
        ids = [s.id for s in skills_with_content]
        self._fire(PipelineStage.SKILL_INJECT, skill_ids=ids, injected=len(ids))  # type: ignore[attr-defined]
        return ids, block
