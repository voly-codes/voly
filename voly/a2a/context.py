"""Prompt/context helpers for local multi-agent roles."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from voly.a2a.roles import ROLE_REGISTRY

_log = logging.getLogger("voly.a2a.multiagent")

_PROJECT_CONTEXT_FILES = (
    "AGENT_TASK_2.txt",
    "AGENT_TASK.txt",
    "CLAUDE.md",
    "README.md",
    "ARCHITECTURE.md",
    "docs/ARCHITECTURE.md",
)
# Extra brief sources for greenfield / GDD-driven tasks (read heads only).
_PROJECT_CONTEXT_DOCS = (
    "docs/task2/Техническое_дополнение_Экономика_Персонал_Магазин_Карта.md",
    "docs/РУЧНОЙ_РЕЖИМ_техдокумент.md",
    "docs/Технический_документ_Ручной_режим_Lean_Arcade.md",
)
_PROJECT_CONTEXT_MAX_CHARS = 14_000
_DOC_HEAD_CHARS = 3_500

ROLE_PROMPT: dict[str, str] = {r.id: r.system_prompt for r in ROLE_REGISTRY.values()}
DEFAULT_PERSONA = (
    "You are a specialist engineer. Complete the assigned sub-task with quality and brevity."
)


def git_diff_evidence(
    cwd: str,
    files: list[str],
    *,
    max_chars: int = 3500,
    max_files: int = 12,
) -> str:
    """Unified git diff for reviewer/tester — real file evidence, not summaries."""
    import subprocess

    if not cwd or not files:
        return ""
    paths = [
        f for f in files
        if f and not str(f).startswith(".voly/")
    ][:max_files]
    if not paths:
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "diff", "--no-color", "--", *paths],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    diff = (proc.stdout or "").strip()
    if not diff:
        heads: list[str] = []
        for rel in paths[:8]:
            fp = Path(cwd) / rel
            if not fp.is_file():
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            heads.append(f"--- a/{rel}\n+++ b/{rel}\n@@ new file @@\n" + text[:400])
        diff = "\n".join(heads)
    if not diff:
        return ""
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n...(diff truncated)"
    return (
        "## Working-tree evidence (untrusted git diff)\n"
        "Use this as ground truth for which files exist and what changed. "
        "Do not invent missing files that appear here.\n\n"
        f"```diff\n{diff}\n```"
    )


def delta_for_role(
    cwd: str,
    git_before: dict,
    *,
    since: float,
) -> list[str]:
    """Git paths changed since ``git_before``, excluding other runs' noise."""
    from voly.plan.verify import changed_paths, git_porcelain

    git_after = git_porcelain(cwd)
    raw = sorted(changed_paths(git_before, git_after))
    out: list[str] = []
    floor = since - 1.5
    for rel in raw:
        if not rel or str(rel).startswith(".voly/"):
            continue
        fp = Path(cwd) / rel
        try:
            if fp.exists() and fp.stat().st_mtime < floor:
                continue
        except OSError:
            pass
        out.append(rel)
    return out


def project_context_block(cwd: str) -> str:
    """Read key project files to give the architect project-specific context."""
    import os

    if not cwd or not os.path.isdir(cwd):
        return ""
    parts: list[str] = []
    remaining = _PROJECT_CONTEXT_MAX_CHARS

    # Latest voly reuse report (candidates / picked modules) — search runs before A2A.
    try:
        from voly.reuse.context import format_reuse_context

        reuse_block = format_reuse_context(cwd, max_chars=min(2000, remaining))
        if reuse_block:
            parts.append(reuse_block.strip())
            remaining -= len(reuse_block)
    except Exception:
        pass

    for name in _PROJECT_CONTEXT_FILES:
        if remaining <= 0:
            break
        path = os.path.join(cwd, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read(remaining)
            snippet = content.strip()
            if snippet:
                parts.append(f"## {name}\n{snippet}")
                remaining -= len(snippet)
        except OSError:
            continue

    for name in _PROJECT_CONTEXT_DOCS:
        if remaining <= 0:
            break
        path = os.path.join(cwd, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read(min(_DOC_HEAD_CHARS, remaining))
            snippet = content.strip()
            if snippet:
                parts.append(f"## {name} (excerpt)\n{snippet}")
                remaining -= len(snippet)
        except OSError:
            continue

    proto = os.path.join(cwd, "docs", "act1-prototype.html")
    if remaining > 400 and os.path.isfile(proto):
        parts.append(
            "## docs/act1-prototype.html\n"
            "Playable HTML prototype is on disk at docs/act1-prototype.html "
            "(~68KB single-file Canvas game). Treat AGENT_TASK.txt timings/FSM "
            "and the as-built excerpt above as the behavioral contract; open the "
            "HTML in a browser for feel parity when implementing."
        )
    return "\n\n".join(parts)


def skills_block(
    skill_ids: list[str],
    skill_matcher: Callable[[str, str], list[Any]] | None,
    task: str,
    role: str,
) -> str:
    """Build a system-prompt block with the content of assigned skills."""
    if not skill_ids or not skill_matcher:
        return ""
    by_id = {getattr(s, "id", ""): s for s in skill_matcher(task, role)}
    parts: list[str] = []
    for sid in skill_ids:
        s = by_id.get(sid)
        content = getattr(s, "content", "") if s else ""
        if content and content.strip():
            parts.append(f"### {getattr(s, 'name', sid)} ({sid})\n{content.strip()[:3000]}")
    return ("# Loaded skills\n\n" + "\n\n".join(parts)) if parts else ""


def memory_block(memory: Any, query: str, limit: int = 3) -> tuple[str, int]:
    """Retrieve semantic-memory entries relevant to a sub-task. Returns (block, hits)."""
    if memory is None:
        return "", 0
    try:
        entries = memory.search(query, limit=limit)
    except Exception as e:  # noqa: BLE001
        _log.warning("memory search failed: %s", e)
        return "", 0
    parts = [
        f"- [{getattr(m, 'category', '?')}] {getattr(m, 'title', '')}: "
        f"{(getattr(m, 'content', '') or '')[:600]}"
        for m in entries
    ]
    if not parts:
        return "", 0
    return "# Relevant prior context (memory)\n" + "\n".join(parts), len(parts)
