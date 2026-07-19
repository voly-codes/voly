"""Module picker via AIGateway.chat() → JSON modules list."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from voly.reuse.pack import format_pack_for_llm
from voly.reuse.report import CandidatePack, PickedModule

_log = logging.getLogger("voly.reuse.picker")

_SYSTEM = """You select reusable source modules from candidate open-source repositories.
Return ONLY valid JSON (no markdown fences) with this shape:
{"modules":[{"repo":"owner/repo","path":"relative/path","reason":"...","confidence":0.0}]}
Rules:
- Prefer small, self-contained modules (dirs or files) over whole repos.
- Skip tests, docs, CI, vendor, and license-incompatible repos.
- confidence is 0.0–1.0.
- At most 8 modules total.
- Paths must exist in the provided tree/relevant files.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def plan_search_query(task: str, gateway: Any, *, model: str = "", provider: str = "") -> str:
    """Optional LLM query refinement; falls back to deterministic keywords."""
    from voly.reuse.github_search import task_to_query

    fallback = task_to_query(task)
    if gateway is None:
        return fallback
    try:
        resp = gateway.chat(
            messages=[{
                "role": "user",
                "content": (
                    "Turn this coding task into a short GitHub repository search query "
                    f"(keywords only, max 12 words). Task:\n{task}\n\n"
                    "Reply with the query string only."
                ),
            }],
            model=model or "claude-sonnet",
            provider_name=provider or "anthropic",
            max_tokens=64,
            temperature=0.0,
            system="You produce GitHub search queries. No explanation.",
            agent="reuse-query",
            cache_scope="reuse-query",
        )
        content = (resp.get("content") or "").strip().strip('"')
        if resp.get("error") or not content:
            return fallback
        # Keep it short and safe
        content = re.sub(r"[\n\r]+", " ", content)[:120]
        return content or fallback
    except Exception as e:
        _log.warning("query planner failed: %s", e)
        return fallback


def pick_modules(
    task: str,
    candidates: list[CandidatePack],
    gateway: Any,
    *,
    model: str = "",
    provider: str = "",
) -> list[PickedModule]:
    """Ask the gateway which modules to copy. Empty list on failure."""
    allowed = [c for c in candidates if c.license_allowed and not c.error]
    if not allowed:
        return []
    if gateway is None:
        return _heuristic_pick(task, allowed)

    packs = "\n\n---\n\n".join(format_pack_for_llm(c) for c in allowed[:5])
    user = (
        f"Task:\n{task}\n\n"
        f"Candidate packs:\n{packs}\n\n"
        "Select the best modules to copy into a target project under vendor/."
    )
    try:
        resp = gateway.chat(
            messages=[{"role": "user", "content": user}],
            model=model or "claude-sonnet",
            provider_name=provider or "anthropic",
            max_tokens=2048,
            temperature=0.0,
            system=_SYSTEM,
            agent="reuse-picker",
            cache_scope="reuse-pick",
        )
    except Exception as e:
        _log.warning("picker chat failed: %s", e)
        return _heuristic_pick(task, allowed)

    if resp.get("error"):
        _log.warning("picker error: %s", resp.get("error"))
        return _heuristic_pick(task, allowed)

    data = _extract_json(resp.get("content") or "")
    modules = data.get("modules") if isinstance(data, dict) else None
    if not isinstance(modules, list):
        return _heuristic_pick(task, allowed)

    by_name = {c.full_name: c for c in allowed}
    out: list[PickedModule] = []
    for raw in modules:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or "").strip().lstrip("./")
        repo = str(raw.get("repo") or "").strip()
        if not path or ".." in path.split("/"):
            continue
        if repo and repo not in by_name:
            # try match by suffix
            match = next((n for n in by_name if n.endswith("/" + repo) or n == repo), "")
            repo = match
        if not repo:
            # default to first candidate that lists the path
            for c in allowed:
                if path in c.relevant_files or path in (c.tree_summary or ""):
                    repo = c.full_name
                    break
        if not repo:
            continue
        try:
            conf = float(raw.get("confidence") or 0.5)
        except (TypeError, ValueError):
            conf = 0.5
        out.append(
            PickedModule(
                path=path,
                reason=str(raw.get("reason") or "")[:300],
                confidence=max(0.0, min(1.0, conf)),
                repo=repo,
            )
        )
        if len(out) >= 8:
            break
    return out or _heuristic_pick(task, allowed)


def _heuristic_pick(task: str, candidates: list[CandidatePack]) -> list[PickedModule]:
    """Offline fallback: top relevant files from the best-starred allowed repo."""
    ranked = sorted(candidates, key=lambda c: c.stars, reverse=True)
    out: list[PickedModule] = []
    for c in ranked[:2]:
        for path in c.relevant_files[:3]:
            out.append(
                PickedModule(
                    path=path,
                    reason="heuristic: keyword-relevant file",
                    confidence=0.35,
                    repo=c.full_name,
                )
            )
            if len(out) >= 5:
                return out
    return out
