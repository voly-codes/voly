"""Project-agnostic validation of local Markdown link destinations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

_INLINE_LINK = re.compile(
    r"!?\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^)\s]+))",
)
_REFERENCE_DEFINITION = re.compile(
    r"^\s{0,3}\[[^\]\n]+\]:\s*(?:<([^>\n]+)>|(\S+))",
    re.MULTILINE,
)
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def _without_fenced_code(text: str) -> str:
    lines: list[str] = []
    fence_char = ""
    fence_size = 0
    for line in text.splitlines():
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if not fence_char:
                fence_char, fence_size = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_size:
                fence_char, fence_size = "", 0
            continue
        if not fence_char:
            lines.append(line)
    return "\n".join(lines)


def _destinations(text: str) -> list[str]:
    visible = _without_fenced_code(text)
    values: list[str] = []
    for pattern in (_INLINE_LINK, _REFERENCE_DEFINITION):
        for match in pattern.finditer(visible):
            destination = match.group(1) or match.group(2) or ""
            if destination:
                values.append(destination)
    return values


def validate_markdown_links(
    cwd: str,
    files_touched: list[str],
) -> tuple[bool, str, dict[str, Any]]:
    """Validate local inline and reference destinations in changed Markdown."""
    root = Path(cwd).resolve()
    markdown_files = sorted(
        {
            path.replace("\\", "/")
            for path in files_touched
            if Path(path).suffix.lower() in {".md", ".mdx"}
        }
    )
    if not markdown_files:
        return False, "no changed Markdown files", {"checked": [], "broken": []}

    checked: list[dict[str, str]] = []
    broken: list[dict[str, str]] = []
    for relative in markdown_files:
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            broken.append({"source": relative, "destination": "", "reason": "source_missing"})
            continue
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            broken.append(
                {"source": relative, "destination": "", "reason": f"read_error:{exc}"}
            )
            continue
        for raw_destination in _destinations(text):
            parsed = urlsplit(raw_destination)
            if (
                parsed.scheme
                or parsed.netloc
                or raw_destination.startswith(("#", "/"))
                or not parsed.path
            ):
                continue
            destination = unquote(parsed.path)
            target = (source.parent / destination).resolve()
            item = {"source": relative, "destination": raw_destination}
            if not target.is_relative_to(root):
                broken.append({**item, "reason": "outside_root"})
            elif not target.exists():
                broken.append({**item, "reason": "missing"})
            else:
                checked.append(item)

    message = (
        f"{len(markdown_files)} Markdown file(s), {len(checked)} local link(s) valid"
        if not broken
        else f"{len(broken)} broken local Markdown link(s)"
    )
    return not broken, message, {
        "files": markdown_files,
        "checked": checked,
        "broken": broken,
    }
