"""Compile free-text success criteria into draft acceptance checks (PR5).

Output is always a **draft** — never auto-trusted without review. Heuristic only;
DSPy / LLM may call the same helper after generating criteria text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from voly.plan.types import AcceptanceCheck

# File-ish tokens (relative paths)
_PATH_RE = re.compile(
    r"(?P<path>(?:[\w.-]+/)*[\w.-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|cs|md|yml|yaml|json|toml|sql|css|html|sh))\b",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


@dataclass
class CriteriaDraft:
    """Draft acceptance list + notes for the human / agent to review."""

    checks: list[AcceptanceCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_lines: list[str] = field(default_factory=list)
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_required": self.review_required,
            "checks": [c.to_dict() for c in self.checks],
            "notes": list(self.notes),
            "source_lines": list(self.source_lines),
        }

    def to_yaml_fragment(self) -> str:
        """YAML snippet for pasting under a plan step's acceptance:."""
        if not self.checks:
            return "acceptance: []\n"
        lines = ["acceptance:"]
        for c in self.checks:
            lines.append(f"  - type: {c.type}")
            if c.paths:
                lines.append("    paths:")
                for p in c.paths:
                    lines.append(f"      - {p}")
            if c.run:
                lines.append(f"    run: {c.run!r}")
                lines.append(f"    expect_exit: {c.expect_exit}")
            if c.pattern:
                lines.append(f"    pattern: {c.pattern!r}")
        return "\n".join(lines) + "\n"


def _split_lines(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        s = _BULLET_RE.sub("", s).strip()
        if s:
            lines.append(s)
    # Single paragraph without bullets → treat whole text as one criterion
    if not lines and raw:
        lines = [raw]
    return lines


def _paths_in(line: str) -> list[str]:
    return [m.group("path") for m in _PATH_RE.finditer(line)]


def _compile_line(line: str) -> tuple[list[AcceptanceCheck], list[str]]:
    """Map one criterion line → checks + notes."""
    low = line.lower()
    checks: list[AcceptanceCheck] = []
    notes: list[str] = []
    paths = _paths_in(line)

    # Tests / CI command
    if any(
        k in low
        for k in (
            "tests pass",
            "test pass",
            "pytest",
            "npm test",
            "unit test",
            "all tests",
            "тесты проходят",
            "прогон тест",
        )
    ):
        if "npm" in low or "jest" in low or "vitest" in low:
            cmd = "npm test -- --watchAll=false"
        elif "cargo" in low:
            cmd = "cargo test"
        elif "go test" in low:
            cmd = "go test ./..."
        else:
            cmd = "pytest -q"
        # Explicit command quoted in the line
        m = re.search(r"[`'\"]([^`'\"]+)[`'\"]", line)
        if m and any(x in m.group(1) for x in ("pytest", "npm", "cargo", "go ", "make ")):
            cmd = m.group(1).strip()
        checks.append(AcceptanceCheck(type="command", run=cmd, expect_exit=0))
        notes.append(f"draft command from criteria: {cmd!r} — confirm for this repo")

    # Files exist / create / add
    if paths and any(
        k in low
        for k in (
            "exist",
            "create",
            "add file",
            "write",
            "implement",
            "добав",
            "созда",
            "файл",
            "present",
        )
    ):
        checks.append(AcceptanceCheck(type="files_exist", paths=list(dict.fromkeys(paths))))
        notes.append(f"draft files_exist: {paths}")

    # Files must not exist / remove
    if paths and any(k in low for k in ("delete", "remove", "must not exist", "absent", "удал")):
        checks.append(AcceptanceCheck(type="files_missing", paths=list(dict.fromkeys(paths))))

    # Git change
    if any(
        k in low
        for k in (
            "git diff",
            "code change",
            "changed files",
            "diff non",
            "изменен",
            "изменения в",
            "touch",
        )
    ) or (paths and any(k in low for k in ("modify", "update", "refactor", "измени"))):
        if paths:
            checks.append(
                AcceptanceCheck(type="git_diff_contains", paths=list(dict.fromkeys(paths)))
            )
        else:
            checks.append(AcceptanceCheck(type="git_diff_nonempty"))

    # Output / report contains
    m = re.search(
        r"(?:output|report|response|ответ)\s+(?:contains?|includes?|mentions?|содержит)\s+[\"']?(.+?)[\"']?\s*$",
        line,
        re.I,
    )
    if m:
        pat = re.escape(m.group(1).strip().rstrip("."))
        checks.append(AcceptanceCheck(type="output_regex", pattern=pat))

    # Regex explicitly
    m2 = re.search(r"regex[:\s]+[`'\"]?(.+?)[`'\"]?\s*$", line, re.I)
    if m2:
        checks.append(AcceptanceCheck(type="output_regex", pattern=m2.group(1).strip()))

    # Bare paths with no other signal → files_exist
    if paths and not checks:
        checks.append(AcceptanceCheck(type="files_exist", paths=list(dict.fromkeys(paths))))
        notes.append("bare paths → draft files_exist (review)")

    # Vague quality criteria → soft output_nonempty only
    if not checks and any(
        k in low
        for k in (
            "review",
            "document",
            "explain",
            "summary",
            "ревью",
            "опис",
            "done",
            "complete",
            "успешн",
        )
    ):
        checks.append(AcceptanceCheck(type="output_nonempty"))
        notes.append(f"vague criterion → output_nonempty only: {line[:80]!r}")

    if not checks:
        notes.append(f"unmapped criterion (no auto check): {line[:120]!r}")

    return checks, notes


def compile_success_criteria(text: str) -> CriteriaDraft:
    """Turn free-text success criteria into a reviewable draft of acceptance checks.

    Deduplicates identical checks. Always sets ``review_required=True``.
    """
    draft = CriteriaDraft(review_required=True)
    lines = _split_lines(text)
    draft.source_lines = list(lines)
    if not lines:
        draft.notes.append("empty criteria — no checks generated")
        return draft

    seen: set[str] = set()
    for line in lines:
        checks, notes = _compile_line(line)
        draft.notes.extend(notes)
        for c in checks:
            key = json_key(c)
            if key in seen:
                continue
            seen.add(key)
            draft.checks.append(c)

    if not draft.checks:
        draft.notes.append(
            "no structured checks inferred — consider files_exist / command / git_diff_* manually"
        )
    else:
        draft.notes.insert(
            0,
            f"DRAFT: {len(draft.checks)} check(s) from {len(lines)} line(s) — review before active mode",
        )
    return draft


def json_key(check: AcceptanceCheck) -> str:
    import json

    return json.dumps(check.to_dict(), sort_keys=True, ensure_ascii=False)


def criteria_to_acceptance(text: str) -> list[AcceptanceCheck]:
    """Convenience: compile and return checks only (still a draft)."""
    return compile_success_criteria(text).checks
