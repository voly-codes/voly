"""Built-in acceptance check handlers for plan verification."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Callable

from voly.plan.types import AcceptanceCheck
from voly.plan.verify_git import changed_paths, git_porcelain, safe_join
from voly.plan.verify_types import (
    CHECK_COMMAND,
    CHECK_FILE_LINE_LIMIT,
    CHECK_FILES_EXIST,
    CHECK_FILES_MISSING,
    CHECK_GIT_DIFF_CONTAINS,
    CHECK_GIT_DIFF_NONEMPTY,
    CHECK_OUTPUT_NONEMPTY,
    CHECK_OUTPUT_REGEX,
    DEFAULT_COMMAND_TIMEOUT,
    KNOWN_CHECK_TYPES,
    VerifyContext,
    VerifyError,
    VerifyResult,
)

# Basenames of auto-generated / vendor files that must never be size-checked.
# Executor agents cannot control the byte-count of these files (npm install,
# pip install, cargo build, etc. generate them as side-effects of doing their
# actual job).  Flagging them as violations produces false negatives that hide
# real violations and confuse the agent feedback loop.
_GENERATED_BASENAMES: frozenset[str] = frozenset({
    # JavaScript / Node lockfiles
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    # Python lockfiles
    "poetry.lock",
    "Pipfile.lock",
    # Rust
    "Cargo.lock",
    # Go
    "go.sum",
    # PHP
    "composer.lock",
    # Coverage artefacts
    ".coverage",
})

# Path prefixes (always forward-slash, relative to cwd) whose contents are
# generated / vendored.  A file under any of these is always excluded.
_GENERATED_PREFIXES: tuple[str, ...] = (
    "node_modules/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".tox/",
)


def _resolve_git_after(ctx: VerifyContext) -> dict[str, str]:
    if ctx.git_after:
        return ctx.git_after
    if ctx.cwd:
        return git_porcelain(ctx.cwd)
    return {}


def _check_files_exist(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.paths:
        return VerifyResult(CHECK_FILES_EXIST, False, "files_exist requires paths[]")
    missing: list[str] = []
    try:
        for rel in check.paths:
            target = safe_join(ctx.cwd, rel)
            if not target.exists():
                missing.append(rel)
    except VerifyError as exc:
        return VerifyResult(CHECK_FILES_EXIST, False, str(exc))
    if missing:
        return VerifyResult(
            CHECK_FILES_EXIST,
            False,
            f"missing: {missing}",
            {"missing": missing},
        )
    return VerifyResult(CHECK_FILES_EXIST, True, "all paths exist", {"paths": list(check.paths)})


def _check_files_missing(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.paths:
        return VerifyResult(CHECK_FILES_MISSING, False, "files_missing requires paths[]")
    present: list[str] = []
    try:
        for rel in check.paths:
            target = safe_join(ctx.cwd, rel)
            if target.exists():
                present.append(rel)
    except VerifyError as exc:
        return VerifyResult(CHECK_FILES_MISSING, False, str(exc))
    if present:
        return VerifyResult(
            CHECK_FILES_MISSING,
            False,
            f"still present: {present}",
            {"present": present},
        )
    return VerifyResult(CHECK_FILES_MISSING, True, "all paths absent", {"paths": list(check.paths)})


def _check_git_diff_nonempty(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    after = _resolve_git_after(ctx)
    if ctx.git_before or ctx.git_after:
        changed = changed_paths(ctx.git_before, after)
    else:
        # No before snapshot: any dirty porcelain counts as change evidence.
        changed = set(after.keys())

    if check.paths:
        wanted = set(check.paths)
        changed = {p for p in changed if p in wanted or any(
            p == w or p.startswith(w.rstrip("/") + "/") for w in wanted
        )}

    if not changed:
        return VerifyResult(
            CHECK_GIT_DIFF_NONEMPTY,
            False,
            "no git changes detected",
            {"changed": []},
        )
    return VerifyResult(
        CHECK_GIT_DIFF_NONEMPTY,
        True,
        f"{len(changed)} path(s) changed",
        {"changed": sorted(changed)},
    )


def _check_git_diff_contains(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    after = _resolve_git_after(ctx)
    if ctx.git_before or ctx.git_after:
        changed = changed_paths(ctx.git_before, after)
    else:
        changed = set(after.keys())

    # Also consider files_touched as soft evidence when git is empty.
    if not changed and ctx.files_touched:
        changed = set(ctx.files_touched)

    hits: list[str] = []
    if check.paths:
        for w in check.paths:
            for p in changed:
                if p == w or p.startswith(w.rstrip("/") + "/") or w in p:
                    hits.append(p)
        hits = sorted(set(hits))
        if not hits:
            return VerifyResult(
                CHECK_GIT_DIFF_CONTAINS,
                False,
                f"none of paths {check.paths} in changed={sorted(changed)}",
                {"changed": sorted(changed)},
            )
        return VerifyResult(
            CHECK_GIT_DIFF_CONTAINS,
            True,
            f"matched paths: {hits}",
            {"hits": hits, "changed": sorted(changed)},
        )

    if check.pattern:
        try:
            rx = re.compile(check.pattern)
        except re.error as exc:
            return VerifyResult(
                CHECK_GIT_DIFF_CONTAINS,
                False,
                f"invalid pattern: {exc}",
            )
        hits = sorted(p for p in changed if rx.search(p))
        if not hits:
            return VerifyResult(
                CHECK_GIT_DIFF_CONTAINS,
                False,
                f"no changed path matches {check.pattern!r}",
                {"changed": sorted(changed)},
            )
        return VerifyResult(
            CHECK_GIT_DIFF_CONTAINS,
            True,
            f"pattern matched: {hits}",
            {"hits": hits},
        )

    return VerifyResult(
        CHECK_GIT_DIFF_CONTAINS,
        False,
        "git_diff_contains requires paths[] or pattern",
    )


def _check_command(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.run or not str(check.run).strip():
        return VerifyResult(CHECK_COMMAND, False, "command requires run")
    if not ctx.cwd:
        return VerifyResult(CHECK_COMMAND, False, "command requires cwd")
    from voly.plan.suggest import scope_pytest_command

    run = scope_pytest_command(str(check.run).strip(), list(ctx.files_touched or []))
    try:
        argv = shlex.split(run, posix=os.name != "nt")
    except ValueError as exc:
        return VerifyResult(CHECK_COMMAND, False, f"invalid run string: {exc}")
    if not argv:
        return VerifyResult(CHECK_COMMAND, False, "empty command after split")

    # Refuse shell metacharacters that only work with shell=True.
    # argv is already split; still block absolute weirdness by requiring cwd jail
    # only for relative first token paths that look like files — not PATH bins.
    timeout = ctx.command_timeout if ctx.command_timeout > 0 else DEFAULT_COMMAND_TIMEOUT
    try:
        proc = subprocess.run(
            argv,
            cwd=ctx.cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        return VerifyResult(
            CHECK_COMMAND,
            False,
            f"executable not found: {exc}",
            {"argv": argv},
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            CHECK_COMMAND,
            False,
            f"timeout after {timeout}s",
            {"argv": argv, "timeout": timeout},
        )
    except OSError as exc:
        return VerifyResult(CHECK_COMMAND, False, f"os error: {exc}", {"argv": argv})

    expected = int(check.expect_exit)
    ok = proc.returncode == expected
    stdout = (proc.stdout or "")[-2000:]
    stderr = (proc.stderr or "")[-2000:]
    msg = (
        f"exit {proc.returncode} (expected {expected})"
        if not ok
        else f"exit {proc.returncode}"
    )
    return VerifyResult(
        CHECK_COMMAND,
        ok,
        msg,
        {
            "argv": argv,
            "returncode": proc.returncode,
            "expect_exit": expected,
            "stdout_tail": stdout,
            "stderr_tail": stderr,
        },
    )


def _check_output_nonempty(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    text = ctx.output or ""
    if text.strip():
        return VerifyResult(
            CHECK_OUTPUT_NONEMPTY,
            True,
            f"output length={len(text)}",
            {"length": len(text)},
        )
    return VerifyResult(CHECK_OUTPUT_NONEMPTY, False, "output is empty")


def _check_output_regex(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    if not check.pattern:
        return VerifyResult(CHECK_OUTPUT_REGEX, False, "output_regex requires pattern")
    try:
        rx = re.compile(check.pattern, re.MULTILINE)
    except re.error as exc:
        return VerifyResult(CHECK_OUTPUT_REGEX, False, f"invalid pattern: {exc}")
    text = ctx.output or ""
    if rx.search(text):
        return VerifyResult(CHECK_OUTPUT_REGEX, True, f"matched {check.pattern!r}")
    return VerifyResult(
        CHECK_OUTPUT_REGEX,
        False,
        f"output does not match {check.pattern!r}",
        {"output_len": len(text)},
    )


def _is_generated_file(rel: str, extra_patterns: list[str] | None = None) -> bool:
    """Return True for auto-generated / vendor files that must not be size-checked.

    Checks built-in basenames and path prefixes, then any caller-supplied
    ``extra_patterns`` (each treated as a basename or path-prefix).
    """
    norm = rel.replace("\\", "/").lstrip("./")
    basename = Path(rel).name
    if basename in _GENERATED_BASENAMES:
        return True
    for prefix in _GENERATED_PREFIXES:
        if norm.startswith(prefix) or f"/{prefix}" in f"/{norm}":
            return True
    for pat in (extra_patterns or []):
        pat_norm = pat.replace("\\", "/").strip("/")
        if not pat_norm:
            continue
        if basename == pat_norm or norm == pat_norm:
            return True
        if norm.startswith(pat_norm + "/") or pat_norm in norm.split("/"):
            return True
    return False


def _line_count(path: Path) -> int | None:
    """Count physical lines; return None for binary files."""
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None
    if not raw:
        return 0
    return raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)


def _line_limit_candidates(check: AcceptanceCheck, ctx: VerifyContext) -> list[str]:
    if check.paths:
        return list(dict.fromkeys(check.paths))
    if ctx.files_touched:
        return list(dict.fromkeys(ctx.files_touched))
    after = _resolve_git_after(ctx)
    changed = (
        changed_paths(ctx.git_before, after)
        if ctx.git_before or ctx.git_after
        else set(after)
    )
    return sorted(changed)


def _check_file_line_limit(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    """Enforce per-file line limits on files changed by an executor step."""
    base_limit = int(check.max_lines or 300)
    approved_cap = int(check.approved_max_lines or base_limit)
    if base_limit <= 0:
        return VerifyResult(CHECK_FILE_LINE_LIMIT, False, "max_lines must be positive")
    if approved_cap < base_limit:
        return VerifyResult(
            CHECK_FILE_LINE_LIMIT,
            False,
            "approved_max_lines must be >= max_lines",
        )
    if not ctx.cwd:
        return VerifyResult(CHECK_FILE_LINE_LIMIT, False, "file_line_limit requires cwd")

    approved = int(ctx.approved_file_line_limit or 0)
    effective_limit = (
        min(approved, approved_cap)
        if approved > base_limit
        else base_limit
    )
    candidates = _line_limit_candidates(check, ctx)
    if not candidates:
        return VerifyResult(
            CHECK_FILE_LINE_LIMIT,
            False,
            "no changed files available for line-limit verification",
            {"limit": effective_limit, "checked": {}},
        )

    extra_exclude = list(check.exclude_patterns or [])
    checked: dict[str, int] = {}
    skipped_binary: list[str] = []
    skipped_generated: list[str] = []
    violations: dict[str, int] = {}
    try:
        for rel in candidates:
            if _is_generated_file(rel, extra_exclude):
                skipped_generated.append(rel)
                continue
            target = safe_join(ctx.cwd, rel)
            if not target.is_file():
                continue
            count = _line_count(target)
            if count is None:
                skipped_binary.append(rel)
                continue
            checked[rel] = count
            if count > effective_limit:
                violations[rel] = count
    except (OSError, VerifyError) as exc:
        return VerifyResult(CHECK_FILE_LINE_LIMIT, False, str(exc))

    detail = {
        "limit": effective_limit,
        "base_limit": base_limit,
        "architect_approved": effective_limit > base_limit,
        "checked": checked,
        "skipped_binary": skipped_binary,
        "skipped_generated": skipped_generated,
        "violations": violations,
    }
    if violations:
        summary = ", ".join(f"{path}={lines}" for path, lines in sorted(violations.items()))
        return VerifyResult(
            CHECK_FILE_LINE_LIMIT,
            False,
            f"file line limit {effective_limit} exceeded: {summary}",
            detail,
        )
    return VerifyResult(
        CHECK_FILE_LINE_LIMIT,
        True,
        f"{len(checked)} text file(s) within {effective_limit} lines",
        detail,
    )


_HANDLERS: dict[str, Callable[[AcceptanceCheck, VerifyContext], VerifyResult]] = {
    CHECK_COMMAND: _check_command,
    CHECK_FILES_EXIST: _check_files_exist,
    CHECK_FILES_MISSING: _check_files_missing,
    CHECK_GIT_DIFF_NONEMPTY: _check_git_diff_nonempty,
    CHECK_GIT_DIFF_CONTAINS: _check_git_diff_contains,
    CHECK_OUTPUT_NONEMPTY: _check_output_nonempty,
    CHECK_OUTPUT_REGEX: _check_output_regex,
    CHECK_FILE_LINE_LIMIT: _check_file_line_limit,
}


def run_check(check: AcceptanceCheck, ctx: VerifyContext) -> VerifyResult:
    """Run one acceptance check. Unknown types fail closed."""
    ctype = (check.type or "").strip()
    handler = _HANDLERS.get(ctype)
    if handler is None:
        return VerifyResult(
            ctype or "unknown",
            False,
            f"unknown check type: {ctype!r} (fail closed)",
            {"known": sorted(KNOWN_CHECK_TYPES)},
        )
    return handler(check, ctx)


def run_acceptance(
    checks: list[AcceptanceCheck],
    ctx: VerifyContext,
    *,
    stop_on_fail: bool = False,
) -> list[VerifyResult]:
    """Run all checks in order. Optionally stop after the first failure."""
    results: list[VerifyResult] = []
    for check in checks:
        result = run_check(check, ctx)
        results.append(result)
        if stop_on_fail and not result.ok:
            break
    return results


def all_passed(results: list[VerifyResult]) -> bool:
    return bool(results) and all(r.ok for r in results)
