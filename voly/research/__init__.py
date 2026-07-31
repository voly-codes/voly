"""Offline, research-first shadow pilot."""

from .pilot import run_research, save_report
from .types import ResearchCandidate, ResearchDecision, ResearchReport

__all__ = [
    "ResearchCandidate",
    "ResearchDecision",
    "ResearchReport",
    "run_research",
    "save_report",
]
