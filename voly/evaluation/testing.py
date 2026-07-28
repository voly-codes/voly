"""Deterministic detection of test artifacts changed by a testing task."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

_TEST_DIRECTORIES = frozenset(
    {"test", "tests", "spec", "specs", "__tests__", "__snapshots__", "fixtures"}
)
_TEST_CONFIG_NAMES = frozenset(
    {
        "conftest.py",
        "pytest.ini",
        "tox.ini",
        "jest.config.js",
        "jest.config.ts",
        "vitest.config.js",
        "vitest.config.ts",
    }
)
_TEST_FILE_SUFFIXES = (
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
)


def is_test_artifact(path: str) -> bool:
    """Return whether a repository-relative path is a conventional test artifact."""
    normalized = path.replace("\\", "/").strip("/")
    if not normalized:
        return False
    candidate = PurePosixPath(normalized)
    name = candidate.name.lower()
    parts = {part.lower() for part in candidate.parts[:-1]}
    return (
        bool(parts & _TEST_DIRECTORIES)
        or name in _TEST_CONFIG_NAMES
        or (name.startswith("test_") and name.endswith(".py"))
        or (name.endswith("_test.py"))
        or name.endswith(_TEST_FILE_SUFFIXES)
    )


def validate_test_artifacts(
    files_touched: list[str],
) -> tuple[bool, str, dict[str, Any]]:
    """Require at least one conventional test artifact in a testing-task diff."""
    artifacts = sorted(
        {path.replace("\\", "/") for path in files_touched if is_test_artifact(path)}
    )
    detail = {"test_artifacts": artifacts}
    if artifacts:
        return True, f"{len(artifacts)} test artifact(s) changed", detail
    return False, "testing task changed no recognized test artifacts", detail
