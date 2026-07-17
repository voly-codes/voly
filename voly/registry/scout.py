"""SkillScout — finds marketplace skills not yet installed locally.

Used by the pipeline's SKILL_SUGGEST stage to surface relevant skills
to the user during task execution, without blocking the run.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from voly.registry.skills import SkillRegistry

_log = logging.getLogger("voly.registry.scout")


class SkillScout:
    def __init__(self, registry: "SkillRegistry", marketplace_url: str = ""):
        self._registry = registry
        self._marketplace_url = marketplace_url.rstrip("/")

    def find_missing(self, task: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Search marketplace for skills relevant to task that are not installed locally.

        Returns a list of slim skill dicts (id, name, description, repository,
        install_kind, tags) sorted by relevance. Returns [] silently on any error
        — the pipeline must never fail because of scout failures.
        """
        if not self._marketplace_url or not task:
            return []

        try:
            from voly.registry.marketplace import MarketplaceClient
            mp = MarketplaceClient(self._marketplace_url)
            # Long task prompts dilute marketplace FTS — search on a compact query.
            query = " ".join(task.split())[:240].strip() or task[:240]
            result = mp.search(query, limit=limit * 2)
        except Exception as exc:
            _log.debug("SkillScout marketplace search failed: %s", exc)
            return []

        local_ids: set[str] = {s.id for s in self._registry.index.list_all()}

        suggestions: list[dict[str, Any]] = []
        for raw in result.get("skills", []):
            sid = raw.get("id", "")
            if not sid or sid in local_ids:
                continue
            suggestions.append({
                "id": sid,
                "name": raw.get("name", sid),
                "description": raw.get("description", ""),
                "repository": raw.get("repository", ""),
                "install_kind": raw.get("install_kind", "single"),
                "tags": raw.get("tags", []),
            })
            if len(suggestions) >= limit:
                break

        return suggestions
