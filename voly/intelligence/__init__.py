"""Repository intelligence — pre-run analysis of external repositories."""

from voly.intelligence.repo_analyzer import AnalyzeConfig, analyze, check_drift
from voly.intelligence.schema import (
    AdmissionResult,
    LicenseInfo,
    QualityInfo,
    RepositoryIntelligence,
    StackInfo,
)

__all__ = [
    "AdmissionResult",
    "AnalyzeConfig",
    "LicenseInfo",
    "QualityInfo",
    "RepositoryIntelligence",
    "StackInfo",
    "analyze",
    "check_drift",
]
