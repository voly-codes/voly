"""Local structure pack: tree + ProjectScanner + keyword-relevant files."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from voly.reuse.report import CandidatePack

_log = logging.getLogger("voly.reuse.pack")

_EXCLUDE_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", "target", ".pytest_cache", ".tox", "vendor", ".voly",
})

_CODE_EXTS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt",
    ".cs", ".rb", ".php", ".swift", ".c", ".cpp", ".h", ".hpp", ".md",
    ".yaml", ".yml", ".toml", ".json",
})

_STOP = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "using",
    "create", "add", "make", "implement", "build", "write", "fix", "update",
    "please", "need", "want", "should", "could", "would", "have", "been",
    "file", "files", "code", "project", "repo", "repository",
})


def _keywords(task: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b", task)
    out: list[str] = []
    for t in tokens:
        low = t.lower()
        if low in _STOP or t in out:
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def build_tree(root: Path, *, max_entries: int = 400, max_depth: int = 4) -> str:
    lines: list[str] = []
    root = root.resolve()

    def walk(dir_path: Path, prefix: str, depth: int) -> None:
        if len(lines) >= max_entries or depth > max_depth:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for ent in entries:
            if len(lines) >= max_entries:
                lines.append(f"{prefix}…")
                return
            name = ent.name
            if name in _EXCLUDE_DIRS or name.startswith("."):
                continue
            if ent.is_dir():
                lines.append(f"{prefix}{name}/")
                walk(ent, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}{name}")

    walk(root, "", 0)
    return "\n".join(lines)


def score_relevant_files(root: Path, keywords: list[str], *, top_n: int = 12) -> list[str]:
    if not keywords:
        return []
    scores: dict[str, int] = {}
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext not in _CODE_EXTS:
                continue
            full = Path(dirpath) / fn
            try:
                rel = str(full.relative_to(root)).replace(os.sep, "/")
            except ValueError:
                continue
            # Score path + a small content sample
            hay = rel.lower()
            score = 0
            for kw in keywords:
                if kw.lower() in hay:
                    score += 3
            try:
                sample = full.read_text(encoding="utf-8", errors="replace")[:8000].lower()
            except OSError:
                sample = ""
            for kw in keywords:
                if kw.lower() in sample:
                    score += 1
            if score:
                scores[rel] = score
    return sorted(scores, key=lambda p: -scores[p])[:top_n]


def _scanner_summary(root: Path) -> str:
    try:
        from voly.scanner import ProjectScanner

        profile = ProjectScanner(root).scan()
        langs = ",".join(l.name for l in (profile.languages or [])[:5])
        fws = ",".join(f.name for f in (profile.frameworks or [])[:5])
        pms = ",".join(profile.package_managers or [])
        parts = [
            f"languages={langs}" if langs else "",
            f"frameworks={fws}" if fws else "",
            f"pkg={pms}" if pms else "",
            f"arch={profile.architecture}" if profile.architecture else "",
        ]
        return "; ".join(p for p in parts if p) or "(empty profile)"
    except Exception as e:
        _log.debug("ProjectScanner failed: %s", e)
        return ""


def pack_repo(
    repo_dir: str | Path,
    *,
    task: str = "",
    max_chars: int = 80_000,
    candidate: CandidatePack | None = None,
) -> CandidatePack:
    """Fill CandidatePack with tree, scanner summary, and relevant file paths."""
    root = Path(repo_dir)
    pack = candidate or CandidatePack(full_name=root.name)
    pack.cache_path = str(root)

    tree = build_tree(root)
    scanner = _scanner_summary(root)
    kws = _keywords(task)
    relevant = score_relevant_files(root, kws)

    # Assemble text budget
    parts = [
        f"# {pack.full_name}",
        f"stars={pack.stars} language={pack.language} license={pack.license_spdx}",
        f"description={pack.description}",
        "## Scanner",
        scanner or "(none)",
        "## Tree",
        tree,
        "## Relevant files",
        "\n".join(relevant) or "(none)",
    ]
    # Include small snippets for top files
    budget = max_chars
    body = "\n".join(parts)
    snippets: list[str] = []
    used = len(body)
    for rel in relevant[:8]:
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        snippet = text[:2000]
        block = f"\n### {rel}\n```\n{snippet}\n```\n"
        if used + len(block) > budget:
            break
        snippets.append(block)
        used += len(block)

    pack.tree_summary = tree[:20_000]
    pack.scanner_summary = scanner
    pack.relevant_files = relevant
    pack.pack_chars = used
    # Stash full pack text in notes-friendly attribute via tree_summary extension
    # Callers that need the full pack for the LLM use format_pack_for_llm().
    pack.tree_summary = tree[:20_000]
    if snippets:
        # Append marker so picker can use relevant content without huge tree
        pack.tree_summary = (
            tree[:12_000]
            + "\n\n## File snippets\n"
            + "".join(snippets)
        )[: max_chars]
    return pack


def format_pack_for_llm(candidate: CandidatePack) -> str:
    return (
        f"Repo: {candidate.full_name}\n"
        f"URL: {candidate.html_url}\n"
        f"Stars: {candidate.stars} Language: {candidate.language} "
        f"License: {candidate.license_spdx} allowed={candidate.license_allowed}\n"
        f"Description: {candidate.description}\n"
        f"Scanner: {candidate.scanner_summary}\n"
        f"Relevant paths: {', '.join(candidate.relevant_files)}\n\n"
        f"{candidate.tree_summary}"
    )
