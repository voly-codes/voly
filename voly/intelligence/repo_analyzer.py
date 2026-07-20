"""Main orchestrator — full repository intelligence pipeline with SHA cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from voly.intelligence.admission import AdmissionConfig, check as admission_check, parse_github_url
from voly.intelligence.architecture_mapper import detect_frameworks, detect_languages, map_architecture
from voly.intelligence.dependency_analyzer import analyze_dependencies
from voly.intelligence.license_analyzer import analyze as analyze_license
from voly.intelligence.repo_analyzer_cache import (
    check_drift,
    clone_repository,
    find_cached_report,
    find_license,
    get_report_path,
    load_cached_report,
    resolve_head_sha,
    shallow_clone,
    slug,
)
from voly.intelligence.repo_analyzer_quality import build_quality, runtime_for
from voly.intelligence.schema import RepositoryIntelligence, StackInfo
from voly.intelligence.security_scanner import scan as security_scan

__all__ = [
    "AnalyzeConfig",
    "analyze",
    "check_drift",
    "clone_repository",
    "find_license",
]


@dataclass
class AnalyzeConfig:
    admission: AdmissionConfig = field(default_factory=AdmissionConfig)
    license_policy: str = "allow_permissive"
    allowed_licenses: list[str] = field(
        default_factory=lambda: [
            "mit",
            "apache-2.0",
            "bsd-2-clause",
            "bsd-3-clause",
            "isc",
            "unlicense",
            "0bsd",
        ]
    )
    deny_licenses: list[str] = field(
        default_factory=lambda: ["gpl-2.0", "gpl-3.0", "agpl-3.0"]
    )
    use_ai_mapper: bool = False
    cache_dir: str = ".voly/intelligence/cache"
    reports_dir: str = ".voly/intelligence/reports"
    max_cache_age_days: int = 7
    refresh: bool = False


def analyze(url: str, config: AnalyzeConfig | None = None) -> RepositoryIntelligence:
    """Run full repository intelligence pipeline."""
    cfg = config or AnalyzeConfig()
    admission = admission_check(url, cfg.admission)
    if not admission.allowed:
        raise ValueError(admission.reason or "admission denied")

    parsed = parse_github_url(url)
    owner, repo = parsed if parsed else ("local", "repo")
    repo_name = f"{owner}/{repo}"

    if not cfg.refresh:
        cached = find_cached_report(cfg.reports_dir, owner, repo, cfg.max_cache_age_days)
        if cached is not None:
            return cached

    local = Path(url)
    if local.is_dir():
        clone_path = str(local.resolve())
    else:
        clone_target = str(Path(cfg.cache_dir) / slug(owner, repo))
        if not shallow_clone(url, clone_target):
            raise ValueError(f"failed to clone {url}")
        clone_path = clone_target

    sha = resolve_head_sha(clone_path)
    report_path = get_report_path(cfg.reports_dir, owner, repo, sha)
    if not cfg.refresh:
        exact = load_cached_report(report_path, cfg.max_cache_age_days)
        if exact is not None:
            return exact

    root = Path(clone_path)
    license_info = analyze_license(find_license(root), spdx_hint=None)
    languages = detect_languages(clone_path)
    frameworks = detect_frameworks(clone_path)
    deps = analyze_dependencies(clone_path)
    versions = {eco: next(iter(pkg_map.values()), "") for eco, pkg_map in deps.items() if pkg_map}

    report = RepositoryIntelligence(
        repository=repo_name,
        commit=sha,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        api_enriched=admission.api_enriched,
        license=license_info,
        stack=StackInfo(
            languages=languages,
            frameworks=frameworks,
            runtime=runtime_for(languages),
            versions=versions,
        ),
        architecture=map_architecture(clone_path, use_ai=cfg.use_ai_mapper),
        quality=build_quality(root, admission.last_commit_days_ago),
        reuse_candidates=[],
        risks=security_scan(clone_path),
        architect_context={"dependencies": deps},
    )

    out = Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_json(), encoding="utf-8")
    return report
