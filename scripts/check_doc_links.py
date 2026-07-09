#!/usr/bin/env python3
"""CI gate: no broken relative links between Markdown docs.

Catches renamed/removed docs that leave dangling `[text](path.md)` links — the
kind of drift that made the plan docs reference stale filenames. Only checks
relative links to local files (skips http/https/mailto and pure #anchors).

Exit 1 (with a list) on any broken link; 0 when all resolve.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "docs", ROOT]  # docs/ + top-level READMEs/CLAUDE.md
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _iter_md() -> list[pathlib.Path]:
    seen: set[pathlib.Path] = set()
    files: list[pathlib.Path] = []
    for md in (ROOT / "docs").rglob("*.md"):
        seen.add(md)
        files.append(md)
    for name in ("README.md", "README_ru.md", "CLAUDE.md"):
        p = ROOT / name
        if p.exists() and p not in seen:
            files.append(p)
    return files


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#", "tel:"))


def main() -> int:
    broken: list[str] = []
    for md in _iter_md():
        text = md.read_text(encoding="utf-8")
        for m in LINK_RE.finditer(text):
            target = m.group(1).strip()
            if _is_external(target) or not target:
                continue
            path_part = target.split("#", 1)[0].split("?", 1)[0]
            if not path_part:  # pure anchor
                continue
            resolved = (md.parent / path_part).resolve()
            if not resolved.exists():
                rel = md.relative_to(ROOT)
                broken.append(f"{rel} → {target}")

    if broken:
        print("✘ broken relative doc links:")
        for b in broken:
            print(f"    {b}")
        print("\nFix: update the link or restore the target file.")
        return 1
    print("✓ doc-links: all relative Markdown links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
