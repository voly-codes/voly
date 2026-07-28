"""Diff-scoped static checks for security-task evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from voly.intelligence.security_scanner import (
    MAX_FILE_SIZE_BYTES,
    RISK_PATTERNS,
    SCAN_EXTENSIONS,
)


def scan_changed_security(
    cwd: str,
    files_touched: list[str],
) -> tuple[str, str, dict[str, Any]]:
    """Scan changed source files without returning matched source or secret values."""
    root = Path(cwd).resolve()
    scanned: list[str] = []
    skipped: list[dict[str, str]] = []
    findings: list[dict[str, str]] = []

    for relative in sorted(set(files_touched)):
        normalized = relative.replace("\\", "/")
        path = (root / normalized).resolve()
        try:
            repository_path = path.relative_to(root).as_posix()
        except ValueError:
            findings.append(
                {
                    "label": "outside_repository",
                    "path": normalized,
                    "description": "Changed path resolves outside repository",
                }
            )
            continue
        if path.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        if not path.is_file():
            skipped.append({"path": repository_path, "reason": "not_a_file"})
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                skipped.append({"path": repository_path, "reason": "too_large"})
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            findings.append(
                {
                    "label": "unreadable_source",
                    "path": repository_path,
                    "description": "Changed source file could not be scanned",
                }
            )
            continue

        scanned.append(repository_path)
        for label, pattern, description in RISK_PATTERNS:
            if pattern.search(text):
                findings.append(
                    {
                        "label": label,
                        "path": repository_path,
                        "description": description,
                    }
                )

    detail: dict[str, Any] = {
        "scanned_files": scanned,
        "skipped_files": skipped,
        "findings": findings,
    }
    if findings:
        return "failed", f"{len(findings)} security finding(s) in changed files", detail
    if not scanned:
        return "skipped", "no supported changed source files to scan", detail
    return "passed", f"{len(scanned)} changed source file(s) scanned", detail
