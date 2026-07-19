"""Shared types and check-type constants for plan verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Built-in check type ids (unknown types fail closed).
CHECK_COMMAND = "command"
CHECK_FILES_EXIST = "files_exist"
CHECK_FILES_MISSING = "files_missing"
CHECK_GIT_DIFF_NONEMPTY = "git_diff_nonempty"
CHECK_GIT_DIFF_CONTAINS = "git_diff_contains"
CHECK_OUTPUT_NONEMPTY = "output_nonempty"
CHECK_OUTPUT_REGEX = "output_regex"
CHECK_FILE_LINE_LIMIT = "file_line_limit"

KNOWN_CHECK_TYPES = frozenset({
    CHECK_COMMAND,
    CHECK_FILES_EXIST,
    CHECK_FILES_MISSING,
    CHECK_GIT_DIFF_NONEMPTY,
    CHECK_GIT_DIFF_CONTAINS,
    CHECK_OUTPUT_NONEMPTY,
    CHECK_OUTPUT_REGEX,
    CHECK_FILE_LINE_LIMIT,
})

DEFAULT_COMMAND_TIMEOUT = 60.0


@dataclass
class VerifyResult:
    """Outcome of a single acceptance check."""

    type: str
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class VerifyContext:
    """Evidence available when verifying a step."""

    cwd: str = ""
    output: str = ""
    files_touched: list[str] = field(default_factory=list)
    # {path: status_code} from `git status --porcelain` (before/after step).
    git_before: dict[str, str] = field(default_factory=dict)
    git_after: dict[str, str] = field(default_factory=dict)
    command_timeout: float = DEFAULT_COMMAND_TIMEOUT
    # Raised from the default limit only by a strict architect plan marker.
    approved_file_line_limit: int = 0


class VerifyError(Exception):
    """Raised for programmer misuse (not a failed check)."""
