"""Verified free model fallback selection.

This is a pure catalog query — it does NOT touch the global AIGateway routing
and must be wired in explicitly (opt-in) by callers.
"""

from __future__ import annotations

from voly.catalog.types import CatalogModel


def verified_free_fallback(
    catalog: list[CatalogModel],
    *,
    executor: str | None = None,
    require_tools: bool = False,
) -> CatalogModel | None:
    """Return the first verified free model eligible for the given constraints.

    Selection criteria (all must hold):
    - enabled == True
    - tier == "free"
    - verified == True  (must be explicitly set; imported models default to False)
    - executor is in executor_compat  (when executor is specified)
    - supports_tools == True  (only when require_tools=True; None is not enough)

    Returns None when no eligible model is found — callers must handle this case.
    """
    for m in catalog:
        if not m.enabled:
            continue
        if m.tier != "free":
            continue
        if not m.verified:
            continue
        if executor is not None and executor not in m.executor_compat:
            continue
        if require_tools and m.supports_tools is not True:
            continue
        return m
    return None
