from __future__ import annotations


def test_schema_instantiation() -> None:
    from voly.intelligence import (
        LicenseInfo,
        QualityInfo,
        RepositoryIntelligence,
        StackInfo,
    )

    lic = LicenseInfo(
        spdx="mit",
        commercial_use=True,
        modification=True,
        distribution=True,
        notice_required=True,
        copyleft=False,
        risk="low",
    )
    stack = StackInfo(
        languages=["python"],
        frameworks=["fastapi"],
        runtime=["python3.11"],
        versions={"python": "3.11"},
    )
    quality = QualityInfo(
        tests="good",
        ci=True,
        documentation="minimal",
        maintainability_score=0.8,
        test_types=["unit"],
        coverage_configured=True,
        test_command="pytest",
        last_commit_days_ago=3,
        open_issues=1,
        open_prs=0,
    )
    report = RepositoryIntelligence(
        repository="owner/repo",
        commit="abc123",
        analyzed_at="2026-01-01T00:00:00Z",
        api_enriched=True,
        license=lic,
        stack=stack,
        architecture={"style": "monolith"},
        quality=quality,
        reuse_candidates=[],
        risks=[],
        architect_context={},
    )
    assert report.repository == "owner/repo"
    assert report.license.risk == "low"
    roundtrip = RepositoryIntelligence.from_json(report.to_json())
    assert roundtrip.repository == "owner/repo"


def test_admission_no_github_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    from voly.intelligence.admission import AdmissionConfig, check

    result = check("https://gitlab.com/owner/repo", AdmissionConfig())
    assert result.allowed is True
    assert result.api_enriched is False


def test_license_analyzer_mit() -> None:
    from voly.intelligence.license_analyzer import analyze

    info = analyze(None, spdx_hint="MIT")
    assert info.risk == "low"
    assert info.copyleft is False
    assert info.commercial_use is True


def test_license_analyzer_gpl() -> None:
    from voly.intelligence.license_analyzer import analyze

    info = analyze(None, spdx_hint="GPL-3.0")
    assert info.risk == "high"
    assert info.copyleft is True


def test_license_unknown() -> None:
    from voly.intelligence.license_analyzer import analyze

    info = analyze(None, spdx_hint=None)
    assert info.risk == "unknown"
    assert info.spdx is None


def test_is_allowed_permissive() -> None:
    from voly.intelligence.license_analyzer import analyze, is_allowed

    info = analyze(None, spdx_hint="MIT")
    assert is_allowed(info, "allow_permissive", ["mit", "apache-2.0"], ["gpl-3.0"]) is True
