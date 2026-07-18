"""Scanner-based suggestions for plan acceptance (PR5)."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voly.plan.types import AcceptanceCheck

_TEST_FILE_RE = re.compile(
    r"(?:^|/)(?:test_[^/]+\.py|[^/]+_test\.py)$",
    re.IGNORECASE,
)


def _prefer_venv_pytest(command: str, cwd: str) -> str:
    """If command is PATH pytest and project has .venv/bin/pytest, prefer the venv binary."""
    if not command or not cwd:
        return command
    parts = command.split()
    if not parts or parts[0] != "pytest":
        return command
    venv_pytest = Path(cwd) / ".venv" / "bin" / "pytest"
    if not venv_pytest.is_file():
        return command
    return " ".join([".venv/bin/pytest", *parts[1:]])


def is_pytest_command(command: str) -> bool:
    if not (command or "").strip():
        return False
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return False
    return bool(parts) and Path(parts[0]).name.lower() == "pytest"


def scope_pytest_command(command: str, files_touched: list[str] | None) -> str:
    """Scope a bare pytest suite to newly touched test files (greenfield-friendly).

    Leaves the command unchanged when it already has path args, is not pytest,
    or no test files appear in ``files_touched``.
    """
    if not command or not files_touched or not is_pytest_command(command):
        return command
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return command
    # Already targeted (path args after flags).
    if any(not a.startswith("-") for a in parts[1:]):
        return command
    tests = sorted(
        {
            f.replace("\\", "/")
            for f in files_touched
            if f and not str(f).startswith(".voly/") and _TEST_FILE_RE.search(f.replace("\\", "/"))
        }
    )
    if not tests:
        return command
    return " ".join([*parts, *tests[:24]])


@dataclass
class PlanSuggestions:
    """Suggested defaults for a project cwd — always reviewable."""

    test_command: str = ""
    lint_command: str = ""
    acceptance_tester: list[AcceptanceCheck] = field(default_factory=list)
    acceptance_executor: list[AcceptanceCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    profile_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_command": self.test_command,
            "lint_command": self.lint_command,
            "acceptance_tester": [c.to_dict() for c in self.acceptance_tester],
            "acceptance_executor": [c.to_dict() for c in self.acceptance_executor],
            "notes": list(self.notes),
            "profile": self.profile_summary,
        }


def suggest_test_command(profile: Any) -> str:
    """Pick a default test command from ProjectProfile (or dict-like)."""
    if profile is None:
        return ""

    test_fw = [str(x).lower() for x in (getattr(profile, "test_frameworks", None) or [])]
    langs = []
    for lang in getattr(profile, "languages", None) or []:
        name = getattr(lang, "name", lang) if not isinstance(lang, str) else lang
        langs.append(str(name).lower())
    pms = [str(x).lower() for x in (getattr(profile, "package_managers", None) or [])]

    if any("pytest" in t for t in test_fw) or "python" in langs:
        return "pytest -q"
    if any(t in ("jest", "vitest", "mocha") for t in test_fw) or "npm" in pms or "pnpm" in pms:
        if "pnpm" in pms:
            return "pnpm test"
        if "yarn" in pms:
            return "yarn test"
        return "npm test -- --watchAll=false"
    if "cargo" in pms or "rust" in langs:
        return "cargo test"
    if "go" in langs:
        return "go test ./..."
    if "dotnet" in pms or "csharp" in langs:
        return "dotnet test"
    if "maven" in pms or "java" in langs:
        return "mvn test -q"
    return ""


def suggest_lint_command(profile: Any) -> str:
    if profile is None:
        return ""
    linters = [str(x).lower() for x in (getattr(profile, "linter_tools", None) or [])]
    langs = []
    for lang in getattr(profile, "languages", None) or []:
        name = getattr(lang, "name", lang) if not isinstance(lang, str) else lang
        langs.append(str(name).lower())
    if any("ruff" in x for x in linters) or "python" in langs:
        return "ruff check ."
    if any("eslint" in x for x in linters):
        return "npx eslint ."
    if "rust" in langs:
        return "cargo clippy -- -D warnings"
    return ""


def suggest_from_cwd(cwd: str) -> PlanSuggestions:
    """Scan project at ``cwd`` and return draft acceptance suggestions."""
    out = PlanSuggestions()
    if not cwd:
        out.notes.append("no cwd — cannot scan")
        return out
    try:
        from voly.scanner import ProjectScanner

        profile = ProjectScanner(cwd).scan()
    except Exception as exc:  # noqa: BLE001
        out.notes.append(f"scan failed: {exc}")
        return out

    out.profile_summary = {
        "name": profile.name,
        "languages": [l.name for l in profile.languages[:5]],
        "test_frameworks": list(profile.test_frameworks[:8]),
        "package_managers": list(profile.package_managers[:6]),
        "linter_tools": list(profile.linter_tools[:6]),
    }
    out.test_command = _prefer_venv_pytest(suggest_test_command(profile), cwd)
    out.lint_command = suggest_lint_command(profile)
    venv_pytest = Path(cwd) / ".venv" / "bin" / "pytest"
    if out.test_command.startswith("pytest") and not venv_pytest.is_file():
        out.notes.append(
            "no .venv/bin/pytest — full-suite verify may fail on greenfield; "
            "plan verify will scope pytest to touched test_*.py when available"
        )

    if out.test_command:
        out.acceptance_tester.append(
            AcceptanceCheck(type="command", run=out.test_command, expect_exit=0)
        )
        out.notes.append(f"tester draft: command {out.test_command!r}")
    else:
        out.notes.append("no test command inferred — set plan.tester_command manually")

    # Executor default draft: require some file change (opt-in style note)
    out.acceptance_executor.append(AcceptanceCheck(type="git_diff_nonempty"))
    out.notes.append(
        "executor draft: git_diff_nonempty (enable plan.executor_require_git_diff to auto-attach)"
    )
    out.notes.insert(0, "DRAFT suggestions from ProjectScanner — review before active mode")
    return out


def apply_suggestions_to_plan_config(plan_cfg: Any, suggestions: PlanSuggestions) -> list[str]:
    """Fill empty plan_cfg.tester_command from suggestions. Returns notes of changes."""
    notes: list[str] = []
    if plan_cfg is None:
        return notes
    if not (getattr(plan_cfg, "tester_command", "") or "").strip() and suggestions.test_command:
        plan_cfg.tester_command = suggestions.test_command
        notes.append(f"set plan.tester_command={suggestions.test_command!r}")
    return notes
