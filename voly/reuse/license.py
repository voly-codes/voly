"""License allow/deny for reuse apply."""

from __future__ import annotations

import re
from pathlib import Path

# SPDX-ish keys normalized to lowercase.
DEFAULT_ALLOWED = frozenset({
    "mit",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "0bsd",
    "unlicense",
})

DEFAULT_DENIED = frozenset({
    "gpl-2.0",
    "gpl-3.0",
    "agpl-3.0",
    "lgpl-2.1",
    "lgpl-3.0",
})

_LICENSE_FILE_NAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.md",
)

# Heuristic text → SPDX
_TEXT_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bMIT License\b", re.I), "mit"),
    (re.compile(r"Apache License[, ]+Version 2\.0", re.I), "apache-2.0"),
    (re.compile(r"BSD 3-Clause", re.I), "bsd-3-clause"),
    (re.compile(r"BSD 2-Clause", re.I), "bsd-2-clause"),
    (re.compile(r"\bISC License\b", re.I), "isc"),
    (re.compile(r"\bUnlicense\b", re.I), "unlicense"),
    (re.compile(r"GNU AFFERO GENERAL PUBLIC LICENSE", re.I), "agpl-3.0"),
    (re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 3", re.I), "gpl-3.0"),
    (re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 2", re.I), "gpl-2.0"),
]


def normalize_spdx(value: str | None) -> str:
    if not value:
        return ""
    s = value.strip().lower()
    s = s.replace(" ", "-")
    # GitHub sometimes returns "mit" already; normalize common aliases
    aliases = {
        "apache-2": "apache-2.0",
        "apache2": "apache-2.0",
        "bsd-3": "bsd-3-clause",
        "bsd-2": "bsd-2-clause",
        "gplv3": "gpl-3.0",
        "gplv2": "gpl-2.0",
        "agplv3": "agpl-3.0",
        "the-unlicense": "unlicense",
    }
    return aliases.get(s, s)


def is_allowed(
    spdx: str | None,
    *,
    allowed: list[str] | frozenset[str] | None = None,
    denied: list[str] | frozenset[str] | None = None,
) -> bool:
    """Return True if license may be copied into a project via apply."""
    key = normalize_spdx(spdx)
    if not key:
        return False
    deny = {normalize_spdx(x) for x in (denied if denied is not None else DEFAULT_DENIED)}
    allow = {normalize_spdx(x) for x in (allowed if allowed is not None else DEFAULT_ALLOWED)}
    if key in deny:
        return False
    return key in allow


def detect_license_from_text(text: str) -> str:
    if not text:
        return ""
    head = text[:4000]
    for pat, spdx in _TEXT_HINTS:
        if pat.search(head):
            return spdx
    return ""


def read_license_file(repo_dir: str | Path) -> tuple[str, str]:
    """Return (spdx, source_path) from LICENSE* in repo root, or ('', '')."""
    root = Path(repo_dir)
    for name in _LICENSE_FILE_NAMES:
        path = root / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            spdx = detect_license_from_text(text)
            return spdx, str(path)
    return "", ""


def resolve_license(
    *,
    github_spdx: str = "",
    repo_dir: str | Path | None = None,
) -> str:
    """Prefer GitHub API SPDX; fall back to LICENSE file heuristics."""
    gh = normalize_spdx(github_spdx)
    if gh and gh != "other" and gh != "noassertion":
        return gh
    if repo_dir is not None:
        file_spdx, _ = read_license_file(repo_dir)
        if file_spdx:
            return file_spdx
    return gh
