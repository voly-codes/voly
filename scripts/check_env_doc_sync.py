#!/usr/bin/env python3
"""CI gate: every user-facing VOLY_* env var read by the code must be documented.

Prevents the doc/config drift the project keeps hitting (ports, a2a.enabled,
env-var prefix). Ported idea from OmniRoute's `check:env-doc-sync`.

A var is "user-facing" when application code references it AND it is not on the
INTERNAL_ALLOWLIST (vars that code sets for its own plumbing, never read from the
user's environment). Every user-facing var MUST appear in BOTH:
  - `.env.example`  (so operators know it exists)
  - some file under `docs/`  (so its meaning is documented)

Exit code 1 (with a list) on any gap; 0 when in sync. Fix the cause — only add
to INTERNAL_ALLOWLIST for genuinely internal vars, with a justification comment.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "voly"
ENV_EXAMPLE = ROOT / ".env.example"
DOCS_DIR = ROOT / "docs"

VAR_RE = re.compile(r"\bVOLY_[A-Z0-9_]+\b")

# Internal plumbing: set by the code for subprocesses / recursion control, never
# meant to be configured by an operator. Keep each entry justified.
INTERNAL_ALLOWLIST = {
    "VOLY_UI_API_PORT",  # set by `voly ui --dev` for the Vite subprocess (ui_cmd.py)
    "VOLY_A2A_NESTED",   # recursion guard set by the pipeline server for subtasks
}


def _real_env_names(names: set[str]) -> set[str]:
    """Drop f-string / docstring prefixes like VOLY_CLOUD_ or VOLY_A2A_EXECUTOR_."""
    return {n for n in names if not n.endswith("_")}


def scan_code_vars() -> set[str]:
    found: set[str] = set()
    for path in CODE_DIR.rglob("*.py"):
        found.update(VAR_RE.findall(path.read_text(encoding="utf-8")))
    return _real_env_names(found)


def env_example_vars() -> set[str]:
    if not ENV_EXAMPLE.exists():
        return set()
    # Accept both active (KEY=) and commented (# KEY=) declarations.
    keys = re.findall(r"(?m)^\s*#?\s*(VOLY_[A-Z0-9_]+)\s*=", ENV_EXAMPLE.read_text(encoding="utf-8"))
    return _real_env_names(set(keys))


def documented_vars() -> set[str]:
    found: set[str] = set()
    if DOCS_DIR.exists():
        for path in DOCS_DIR.rglob("*.md"):
            found.update(VAR_RE.findall(path.read_text(encoding="utf-8")))
    return _real_env_names(found)


def main() -> int:
    required = scan_code_vars() - INTERNAL_ALLOWLIST
    in_env = env_example_vars()
    in_docs = documented_vars()

    missing_env = sorted(required - in_env)
    missing_docs = sorted(required - in_docs)
    # Reverse check: a documented/exampled var no longer referenced anywhere.
    stale = sorted((in_env | in_docs) - scan_code_vars() - INTERNAL_ALLOWLIST)

    ok = True
    if missing_env:
        ok = False
        print("✘ VOLY_* vars read by code but MISSING from .env.example:")
        for v in missing_env:
            print(f"    {v}")
    if missing_docs:
        ok = False
        print("✘ VOLY_* vars read by code but NOT documented under docs/:")
        for v in missing_docs:
            print(f"    {v}")
    if stale:
        # Warning only — a var may be documented ahead of use.
        print("⚠ VOLY_* vars in .env.example/docs but not referenced in code:")
        for v in stale:
            print(f"    {v}")

    if ok:
        print(f"✓ env-doc-sync: {len(required)} user-facing VOLY_* vars in sync "
              f"(.env.example + docs).")
        return 0
    print("\nFix: add the var to .env.example and docs/backend/config.md, "
          "or add it to INTERNAL_ALLOWLIST with justification.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
