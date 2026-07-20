"""Repository intelligence schema — dataclasses only."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class LicenseInfo:
    spdx: str | None
    commercial_use: bool
    modification: bool
    distribution: bool
    notice_required: bool
    copyleft: bool
    risk: str  # low | medium | high | unknown


@dataclass
class StackInfo:
    languages: list[str]
    frameworks: list[str]
    runtime: list[str]
    versions: dict[str, str]


@dataclass
class QualityInfo:
    tests: str  # none | partial | good
    ci: bool
    documentation: str  # none | minimal | good
    maintainability_score: float
    test_types: list[str]
    coverage_configured: bool
    test_command: str | None
    last_commit_days_ago: int | None
    open_issues: int | None
    open_prs: int | None


@dataclass
class AdmissionResult:
    allowed: bool
    private: bool
    archived: bool
    size_mb: float
    last_commit_days_ago: int | None
    stars: int
    license_file_present: bool
    api_enriched: bool
    reason: str | None


@dataclass
class RepositoryIntelligence:
    repository: str
    commit: str
    analyzed_at: str
    api_enriched: bool
    license: LicenseInfo
    stack: StackInfo
    architecture: dict
    quality: QualityInfo
    reuse_candidates: list[dict]
    risks: list[str]
    architect_context: dict

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, s: str) -> RepositoryIntelligence:
        data: dict[str, Any] = json.loads(s)
        return cls(
            repository=data["repository"],
            commit=data["commit"],
            analyzed_at=data["analyzed_at"],
            api_enriched=bool(data["api_enriched"]),
            license=LicenseInfo(**data["license"]),
            stack=StackInfo(**data["stack"]),
            architecture=dict(data.get("architecture") or {}),
            quality=QualityInfo(**data["quality"]),
            reuse_candidates=list(data.get("reuse_candidates") or []),
            risks=list(data.get("risks") or []),
            architect_context=dict(data.get("architect_context") or {}),
        )
