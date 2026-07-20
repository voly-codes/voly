"""_PipelineStageMixin: composed from focused stage mixins.

Layout (behaviour unchanged — split for size/maintainability only):

- ``stages_a2a.py``      — AG-UI + A2A federation / local multi-agent
- ``stages_intelligence.py`` — optional repository intelligence
- ``stages_route.py``    — AgentRouter + spend check
- ``stages_context.py``  — memory, Headroom, RTK, skill suggest/inject
- ``stages_emit.py``     — builders, gateway error checks, TaskEvent emit
"""

from __future__ import annotations

from voly.pipeline.stages_a2a import _A2AStageMixin
from voly.pipeline.stages_context import _ContextStageMixin
from voly.pipeline.stages_intelligence import _IntelligenceStageMixin
from voly.pipeline.stages_emit import _EmitStageMixin
from voly.pipeline.stages_route import _RouteStageMixin

__all__ = ["_PipelineStageMixin"]


class _PipelineStageMixin(
    _A2AStageMixin,
    _IntelligenceStageMixin,
    _RouteStageMixin,
    _ContextStageMixin,
    _EmitStageMixin,
):
    """Mixin for Pipeline: all ``_stage_*`` helpers + build/check/emit helpers."""
