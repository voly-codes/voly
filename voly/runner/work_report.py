"""Git porcelain helpers and WorkReport construction for AgentRunner."""

from __future__ import annotations

import os
import subprocess

from voly.executor.base import WorkReport


def _git_porcelain(cwd: str) -> dict[str, str]:
    """Return {path: status_code} from `git status --porcelain`."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "-u"],
            cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        ).stdout
        result: dict[str, str] = {}
        for line in out.splitlines():
            if len(line) < 4:
                continue
            xy, path = line[:2], line[3:].strip()
            # Handle renames: "old -> new"
            if " -> " in path:
                path = path.split(" -> ")[-1]
            result[path] = xy.strip() or "?"
        return result
    except Exception:
        return {}


def _dir_snapshot_shallow(cwd: str) -> dict[str, tuple[int, float]]:
    """{filename: (size, mtime)} for immediate files in ``cwd`` (non-recursive).

    Fallback for when ``cwd`` is not itself a git repo (e.g. a plain folder
    that merely contains other repos) — ``git status`` sees nothing there,
    so file creation would otherwise go undetected. Deliberately shallow
    (one ``scandir`` call, no recursion) so it stays cheap and safe even when
    ``cwd`` is a large directory the executor doesn't fully own.
    """
    try:
        out: dict[str, tuple[int, float]] = {}
        with os.scandir(cwd) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    out[entry.name] = (st.st_size, st.st_mtime)
        return out
    except OSError:
        return {}


def _extract_summary(output: str) -> str:
    """Pull a short summary out of the agent's text output."""
    if not output:
        return ""
    # Split into paragraphs; prefer the last non-trivial one
    paragraphs = [p.strip() for p in output.split("\n\n") if p.strip()]
    if not paragraphs:
        return output[:600]
    # Look for a paragraph that reads like a summary
    summary_keywords = ("итого", "в итоге", "выполнено", "сделано", "изменено",
                        "summary", "in summary", "done", "completed", "changes made")
    for p in reversed(paragraphs):
        if any(kw in p.lower() for kw in summary_keywords):
            return p[:800]
    # Fall back to last paragraph
    return paragraphs[-1][:800]


def _build_work_report(
    output: str,
    before: dict[str, str],
    after: dict[str, str],
    *,
    fingerprints_before: dict[str, str] | None = None,
    fingerprints_after: dict[str, str] | None = None,
    dir_snapshot_before: dict[str, tuple[int, float]] | None = None,
    dir_snapshot_after: dict[str, tuple[int, float]] | None = None,
) -> WorkReport:
    changed, created, deleted, actions = [], [], [], []

    # git status saw nothing (not a git repo, or cwd isn't the repo root) —
    # fall back to a shallow before/after directory listing so a created file
    # still shows up instead of silently reporting zero changes.
    if not before and not after and dir_snapshot_before is not None and dir_snapshot_after is not None:
        for name in sorted(set(dir_snapshot_before) | set(dir_snapshot_after)):
            b, a = dir_snapshot_before.get(name), dir_snapshot_after.get(name)
            if b is None and a is not None:
                created.append(name)
            elif a is None and b is not None:
                deleted.append(name)
            elif a != b:
                changed.append(name)
    else:
        all_paths = set(before) | set(after)
        if fingerprints_before is not None and fingerprints_after is not None:
            all_paths |= set(fingerprints_before) | set(fingerprints_after)
        for path in sorted(all_paths):
            b, a = before.get(path), after.get(path)
            if b is None and a is not None:
                # Absent from the *before* porcelain = the file was clean-tracked
                # or did not exist. Only untracked (??) / staged-add (A) entries
                # are genuinely new; an "M" here is a tracked file modified during
                # the run — that's a change, not a creation.
                if "D" in a:
                    deleted.append(path)
                elif a.startswith("?") or "A" in a:
                    created.append(path)
                else:
                    changed.append(path)
            elif a is None and b is not None:
                deleted.append(path)
            elif a != b:
                changed.append(path)
            elif (
                fingerprints_before is not None
                and fingerprints_after is not None
                and a
                and ("?" in a or "A" in a)
                and fingerprints_before.get(path) != fingerprints_after.get(path)
            ):
                # Already-untracked path edited in place (status stayed ??).
                changed.append(path)

    # Extract action lines: look for "- ", "•", numbered items in output
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "• ", "* ")) and len(stripped) > 10:
            actions.append(stripped[2:].strip())
        elif len(stripped) > 5 and stripped[0].isdigit() and stripped[1] in ".):":
            actions.append(stripped[2:].strip())
    actions = actions[:20]  # cap

    return WorkReport(
        summary=_extract_summary(output),
        files_changed=changed,
        files_created=created,
        files_deleted=deleted,
        actions=actions,
    )
