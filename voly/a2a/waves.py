"""Dependency-wave grouping for parallel multi-agent chat roles."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voly.a2a.assignment import Assignment


def build_waves(assignments: list[Assignment]) -> list[list[Assignment]]:
    """Group assignments into dependency waves (topological levels).

    Roles in the same wave have no dependencies on each other, so their chat
    calls can run concurrently. Unknown/cyclic dependencies degrade gracefully
    to one-role waves in list order.
    """
    idxs = {a.idx for a in assignments}
    placed: set[int] = set()
    remaining = list(assignments)
    waves: list[list[Assignment]] = []
    while remaining:
        wave = [
            a for a in remaining
            if all(d in placed or d not in idxs for d in a.depends_on)
        ]
        if not wave:  # dependency cycle — fall back to sequential
            wave = [remaining[0]]
        placed.update(a.idx for a in wave)
        remaining = [a for a in remaining if a.idx not in placed]
        waves.append(wave)
    return waves
