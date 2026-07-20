"""Quality signal detection for repository intelligence reports."""

from __future__ import annotations

import json
from pathlib import Path

from voly.intelligence.schema import QualityInfo


def detect_test_command(root: Path) -> str | None:
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            scripts = data.get("scripts") or {}
            for key in ("test", "test:unit", "test:ci"):
                if scripts.get(key):
                    return f"npm run {key}"
        except (json.JSONDecodeError, OSError):
            pass
    for name, cmd in (("tox.ini", "tox"), ("Makefile", "make test")):
        if (root / name).is_file():
            return cmd
    return None


def build_quality(root: Path, admission_days: int | None) -> QualityInfo:
    ci = (
        (root / ".gitlab-ci.yml").is_file()
        or (root / "Jenkinsfile").is_file()
        or (root / ".github" / "workflows").is_dir()
    )
    test_dirs = ("tests", "test", "spec", "__tests__")
    present = [d for d in test_dirs if (root / d).is_dir()]
    tests = "none" if not present else ("good" if len(present) >= 2 else "partial")
    readme = any(root.glob("README*"))
    docs = "good" if (root / "docs").is_dir() and readme else ("minimal" if readme else "none")
    coverage_files = (".coveragerc", "codecov.yml", "codecov.yaml")
    coverage = any((root / name).is_file() for name in coverage_files)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            if "coverage" in pyproject.read_text(encoding="utf-8", errors="replace").lower():
                coverage = True
        except OSError:
            pass
    score = 0.3
    if ci:
        score += 0.2
    if tests != "none":
        score += 0.25
    if docs != "none":
        score += 0.15
    if coverage:
        score += 0.1
    return QualityInfo(
        tests=tests,
        ci=ci,
        documentation=docs,
        maintainability_score=min(score, 1.0),
        test_types=["unit"] if present else [],
        coverage_configured=coverage,
        test_command=detect_test_command(root),
        last_commit_days_ago=admission_days,
        open_issues=None,
        open_prs=None,
    )


def runtime_for(languages: list[str]) -> list[str]:
    mapping = {
        "python": "python3",
        "typescript": "node",
        "javascript": "node",
        "go": "go",
        "rust": "rustc",
        "java": "jvm",
        "kotlin": "jvm",
        "ruby": "ruby",
    }
    return sorted({mapping[lang] for lang in languages if lang in mapping})
