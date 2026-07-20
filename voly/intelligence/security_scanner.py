"""Lightweight static risk detection via pure-Python regex scans."""

from __future__ import annotations

import logging
import re
from pathlib import Path

_log = logging.getLogger("voly.intelligence.security_scanner")

RISK_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "hardcoded_secret",
        re.compile(
            r'(?i)(password|secret|api_key|token)\s*=\s*["\'][^"\'\.\{]{8,}["\']'
        ),
        "Possible hardcoded secret",
    ),
    (
        "sql_injection",
        re.compile(r"execute\s*\([^)]*%\s*|format\s*\([^)]*\)\s*\)"),
        "Possible SQL injection via string formatting",
    ),
    ("eval_usage", re.compile(r"\beval\s*\("), "eval() usage detected"),
    (
        "subprocess_shell",
        re.compile(r"subprocess\..*shell\s*=\s*True"),
        "subprocess with shell=True",
    ),
    (
        "yaml_unsafe_load",
        re.compile(r"yaml\.load\s*\([^,)]+\)(?!.*Loader)"),
        "yaml.load without Loader (unsafe)",
    ),
]

SCAN_EXTENSIONS = {".py", ".js", ".ts", ".go", ".rb", ".php"}
MAX_FILE_SIZE_BYTES = 200_000
MAX_FILES_TO_SCAN = 200

_SKIP_DIRS = frozenset(
    {"node_modules", ".git", ".venv", "dist", "build", "__pycache__"}
)


def scan(repo_path: str) -> list[str]:
    """Walk repo and return deduplicated risk strings (max 20). Never raises."""
    root = Path(repo_path)
    if not root.is_dir():
        return []

    risks: list[str] = []
    seen: set[str] = set()
    scanned = 0

    try:
        for path in root.rglob("*"):
            if scanned >= MAX_FILES_TO_SCAN:
                break
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in _SKIP_DIRS for part in rel.parts):
                continue
            if path.suffix.lower() not in SCAN_EXTENSIONS:
                continue
            try:
                if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                _log.warning("security scan skip %s: %s", rel, exc)
                continue

            for label, pattern, desc in RISK_PATTERNS:
                if pattern.search(text):
                    entry = f"[{label}] {rel.as_posix()}: {desc}"
                    if entry not in seen:
                        seen.add(entry)
                        risks.append(entry)
                        if len(risks) >= 20:
                            return risks
    except Exception as exc:
        _log.warning("security scan failed: %s", exc)

    return risks
