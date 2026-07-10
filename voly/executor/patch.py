"""
LocalPatchApplier — парсит FILE-блоки из LLM-ответа и пишет файлы на диск.

Формат который запрашивается у модели:

    ### FILE: path/relative/to/cwd.ext
    ```lang
    ...complete file content...
    ```

Также поддерживает unified diff (--- a/... +++ b/...).
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger("voly.executor.patch")

# Matches:  ### FILE: src/foo/bar.py   (with optional leading ##, spaces, or "**File:**" markdown)
_FILE_HEADER = re.compile(
    r"^(?:#{1,4}\s+FILE:\s*|(?:\*{1,2})?File:\s*(?:\*{1,2})?)\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Fenced code block: ```lang\n...\n```
_CODE_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)

# Unified diff header
_DIFF_HEADER = re.compile(r"^---\s+a/(.+)$", re.MULTILINE)
_DIFF_PLUS   = re.compile(r"^\+\+\+\s+b/(.+)$", re.MULTILINE)


@dataclass
class AppliedFile:
    path: str
    created: bool = False   # True = new file, False = overwritten existing


@dataclass
class PatchResult:
    applied: list[AppliedFile] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        parts = []
        if self.applied:
            parts.append(f"applied {len(self.applied)} file(s): " + ", ".join(f.path for f in self.applied))
        if self.skipped:
            parts.append(f"skipped {len(self.skipped)}: " + ", ".join(self.skipped))
        if self.errors:
            parts.append(f"errors: " + "; ".join(self.errors))
        return " | ".join(parts) if parts else "no changes"


class LocalPatchApplier:
    """Parse LLM response and write file blocks to disk."""

    def __init__(self, cwd: str):
        self.cwd = os.path.realpath(os.path.expanduser(cwd))

    def apply(self, response: str) -> PatchResult:
        result = PatchResult()

        blocks = self._extract_file_blocks(response)
        if not blocks:
            blocks = self._extract_diff_blocks(response)

        if not blocks:
            result.skipped.append("no FILE blocks or diffs found in response")
            return result

        for rel_path, content in blocks:
            try:
                self._write(rel_path, content, result)
            except Exception as exc:
                msg = f"{rel_path}: {exc}"
                result.errors.append(msg)
                _log.error("patch apply error: %s", msg)

        return result

    # ── Parsers ───────────────────────────────────────────────────────────────

    def _extract_file_blocks(self, text: str) -> list[tuple[str, str]]:
        """Extract ### FILE: path + fenced code block pairs."""
        blocks: list[tuple[str, str]] = []

        # Split on FILE headers, then grab the first fenced block after each
        parts = _FILE_HEADER.split(text)
        # parts = [pre, path1, body1, path2, body2, ...]
        i = 1
        while i < len(parts) - 1:
            rel_path = parts[i].strip()
            body     = parts[i + 1]
            fence    = _CODE_FENCE.search(body)
            if fence:
                content = fence.group(1)
                blocks.append((rel_path, content))
            i += 2

        return blocks

    def _extract_diff_blocks(self, text: str) -> list[tuple[str, str]]:
        """Parse unified diff blocks and apply hunks."""
        blocks: list[tuple[str, str]] = []
        # Split into per-file diff sections
        sections = re.split(r"^diff --git", text, flags=re.MULTILINE)
        for section in sections[1:]:
            m_minus = _DIFF_HEADER.search(section)
            m_plus  = _DIFF_PLUS.search(section)
            if not m_minus or not m_plus:
                continue
            rel_path = m_plus.group(1).strip()
            patched  = self._apply_diff_section(rel_path, section)
            if patched is not None:
                blocks.append((rel_path, patched))
        return blocks

    def _apply_diff_section(self, rel_path: str, diff_text: str) -> str | None:
        """Apply a single-file unified diff section. Returns new content or None."""
        try:
            full = self._resolve_safe_path(rel_path)
        except ValueError as exc:
            _log.error("patch read error: %s", exc)
            return None
        try:
            original = Path(full).read_text(encoding="utf-8").splitlines(keepends=True)
        except FileNotFoundError:
            original = []

        lines   = original[:]
        hunks   = re.split(r"^@@", diff_text, flags=re.MULTILINE)[1:]
        offset  = 0

        for hunk in hunks:
            header_m = re.match(r"\s*-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s*@@", hunk)
            if not header_m:
                continue
            src_start = int(header_m.group(1)) - 1 + offset
            hunk_lines = hunk.split("\n", 1)[1].split("\n") if "\n" in hunk else []

            removes, adds = [], []
            for ln in hunk_lines:
                if ln.startswith("-"):
                    removes.append(ln[1:] + "\n")
                elif ln.startswith("+"):
                    adds.append(ln[1:] + "\n")

            end = src_start + len(removes)
            lines[src_start:end] = adds
            offset += len(adds) - len(removes)

        return "".join(lines) if lines else None

    # ── Path safety ──────────────────────────────────────────────────────────

    def _resolve_safe_path(self, rel_path: str) -> str:
        """Resolve rel_path under self.cwd; raise ValueError on escape.

        Used for both reads and writes — a model-supplied diff path with
        `../` must not be able to read a file outside the sandbox any more
        than it can write one.
        """
        rel_path = rel_path.lstrip("/")
        full = os.path.realpath(os.path.join(self.cwd, rel_path))
        if not full.startswith(self.cwd + os.sep) and full != self.cwd:
            raise ValueError(f"path escape attempt: {rel_path}")
        return full

    # ── Writer ────────────────────────────────────────────────────────────────

    def _write(self, rel_path: str, content: str, result: PatchResult) -> None:
        rel_path = rel_path.lstrip("/")
        full = self._resolve_safe_path(rel_path)
        exists = os.path.exists(full)
        os.makedirs(os.path.dirname(full), exist_ok=True)

        # Normalise indentation: dedent if the model over-indented
        content = textwrap.dedent(content)
        if not content.endswith("\n"):
            content += "\n"

        Path(full).write_text(content, encoding="utf-8")
        result.applied.append(AppliedFile(path=rel_path, created=not exists))
        _log.info("patch: wrote %s (%s)", rel_path, "created" if not exists else "updated")
