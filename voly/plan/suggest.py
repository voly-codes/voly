"""Scanner-based suggestions for plan acceptance (PR5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from voly.plan.types import AcceptanceCheck


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
    out.test_command = suggest_test_command(profile)
    out.lint_command = suggest_lint_command(profile)

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
