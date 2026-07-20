"""SPDX license analysis and policy gate."""

from __future__ import annotations

import re
from pathlib import Path

from voly.intelligence.schema import LicenseInfo

_PERMISSIVE = dict(
    commercial_use=True,
    modification=True,
    distribution=True,
    notice_required=True,
    copyleft=False,
    risk="low",
)
_PERMISSIVE_NO_NOTICE = {**_PERMISSIVE, "notice_required": False}
_WEAK_COPYLEFT = dict(
    commercial_use=True,
    modification=True,
    distribution=True,
    notice_required=True,
    copyleft=True,
    risk="medium",
)
_STRONG_COPYLEFT = dict(
    commercial_use=True,
    modification=True,
    distribution=True,
    notice_required=True,
    copyleft=True,
    risk="high",
)

SPDX_MATRIX: dict[str, dict] = {
    "mit": _PERMISSIVE,
    "apache-2.0": _PERMISSIVE,
    "bsd-2-clause": _PERMISSIVE,
    "bsd-3-clause": _PERMISSIVE,
    "isc": _PERMISSIVE,
    "unlicense": _PERMISSIVE_NO_NOTICE,
    "0bsd": _PERMISSIVE_NO_NOTICE,
    "cc0-1.0": _PERMISSIVE_NO_NOTICE,
    "lgpl-2.1": _WEAK_COPYLEFT,
    "lgpl-3.0": _WEAK_COPYLEFT,
    "mpl-2.0": _WEAK_COPYLEFT,
    "gpl-2.0": _STRONG_COPYLEFT,
    "gpl-3.0": _STRONG_COPYLEFT,
    "agpl-3.0": _STRONG_COPYLEFT,
}

_UNKNOWN = LicenseInfo(
    spdx=None,
    commercial_use=False,
    modification=False,
    distribution=False,
    notice_required=False,
    copyleft=False,
    risk="unknown",
)

_TEXT_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bMIT License\b", re.I), "mit"),
    (re.compile(r"Apache License[, ]+Version 2\.0", re.I), "apache-2.0"),
    (re.compile(r"BSD 3-Clause", re.I), "bsd-3-clause"),
    (re.compile(r"BSD 2-Clause", re.I), "bsd-2-clause"),
    (re.compile(r"\bISC License\b", re.I), "isc"),
    (re.compile(r"\bUnlicense\b", re.I), "unlicense"),
    (re.compile(r"GNU AFFERO GENERAL PUBLIC LICENSE", re.I), "agpl-3.0"),
    (re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 3", re.I), "gpl-3.0"),
    (re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 2", re.I), "gpl-2.0"),
    (re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE\s+Version 3", re.I), "lgpl-3.0"),
    (re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE\s+Version 2", re.I), "lgpl-2.1"),
    (re.compile(r"Mozilla Public License[, ]+Version 2\.0", re.I), "mpl-2.0"),
    (re.compile(r"Creative Commons Zero", re.I), "cc0-1.0"),
    (re.compile(r"\b0BSD\b"), "0bsd"),
]

_ALIASES = {
    "apache-2": "apache-2.0",
    "apache2": "apache-2.0",
    "bsd-3": "bsd-3-clause",
    "bsd-2": "bsd-2-clause",
    "gplv3": "gpl-3.0",
    "gplv2": "gpl-2.0",
    "agplv3": "agpl-3.0",
    "the-unlicense": "unlicense",
}


def _normalize_spdx(value: str | None) -> str:
    if not value:
        return ""
    key = value.strip().lower().replace(" ", "-")
    return _ALIASES.get(key, key)


def _from_matrix(spdx: str) -> LicenseInfo | None:
    key = _normalize_spdx(spdx)
    row = SPDX_MATRIX.get(key)
    if not row:
        return None
    return LicenseInfo(spdx=key, **row)


def _detect_from_text(text: str) -> str:
    head = (text or "")[:8000]
    for pat, spdx in _TEXT_HINTS:
        if pat.search(head):
            return spdx
    return ""


def analyze(license_path: str | None, spdx_hint: str | None = None) -> LicenseInfo:
    """Resolve license from SPDX hint and/or LICENSE file content."""
    if spdx_hint:
        info = _from_matrix(spdx_hint)
        if info:
            return info

    if license_path:
        path = Path(license_path)
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return _UNKNOWN
            detected = _detect_from_text(text)
            if detected:
                info = _from_matrix(detected)
                if info:
                    return info

    return _UNKNOWN


def is_allowed(
    info: LicenseInfo,
    policy: str,
    allowed: list[str],
    deny: list[str],
) -> bool:
    """Policy gate: allow_permissive | allow_all | strict."""
    spdx = _normalize_spdx(info.spdx)
    allow_set = {_normalize_spdx(x) for x in allowed if x}
    deny_set = {_normalize_spdx(x) for x in deny if x}

    if spdx and spdx in deny_set:
        return False

    if policy == "allow_all":
        return True
    if policy == "allow_permissive":
        return info.risk == "low" and bool(spdx) and spdx in allow_set
    if policy == "strict":
        return bool(spdx) and spdx in allow_set
    return False
