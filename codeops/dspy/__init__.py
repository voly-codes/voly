"""
codeops.dspy — DSPy optimizer layer for VOLY.

Architecture:
    HEADROOM_COMPRESS
          ↓
    DSPY_PROGRAM_CALL   ← this package
          ↓
    AIGateway.chat      ← unchanged, remains the single exit to models

DSPy does NOT replace AIGateway.  It wraps it:
    VOLYDSPyLM (adapter.py) → AIGateway.chat()

Usage:
    from codeops.dspy import DSPyRunner
    runner = DSPyRunner(config, gateway)
    result = runner.run(task, messages, route, model)

Requires optional dependency:
    pip install codeops[dspy]   # or: pip install dspy>=2.5.0
"""

from __future__ import annotations

# Public surface: only import what's needed without triggering dspy import
from codeops.dspy.runner import DSPyRunner

__all__ = ["DSPyRunner"]
