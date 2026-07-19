"""Code reuse pipeline: search → clone → pack → pick → apply."""

from voly.reuse.report import ReuseReport, CandidatePack, PickedModule

__all__ = [
    "ReuseReport",
    "CandidatePack",
    "PickedModule",
    "run_reuse",
]


def __getattr__(name: str):
    if name == "run_reuse":
        from voly.reuse.pipeline import run_reuse

        return run_reuse
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
