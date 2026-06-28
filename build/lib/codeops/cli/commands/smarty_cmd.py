"""CLI: codeops smarty — Smarty CRM combat missions."""

from __future__ import annotations

import sys
from pathlib import Path

# projects/ lives at repo root, sibling to codeops package
_CODEOPS_ROOT = Path(__file__).resolve().parents[3]
if str(_CODEOPS_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODEOPS_ROOT))

from projects.smarty.cli_commands import smarty  # noqa: E402

__all__ = ["smarty"]
