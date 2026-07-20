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


def test_detect_languages_empty_dir(tmp_path):
    from voly.intelligence.architecture_mapper import detect_languages

    result = detect_languages(str(tmp_path))
    assert isinstance(result, list)


def test_detect_frameworks_no_manifests(tmp_path):
    from voly.intelligence.architecture_mapper import detect_frameworks

    result = detect_frameworks(str(tmp_path))
    assert result == []


def test_map_architecture_empty(tmp_path):
    from voly.intelligence.architecture_mapper import map_architecture

    result = map_architecture(str(tmp_path))
    assert "style" in result
    assert result["ai_assisted"] is False


def test_security_scanner_no_issues(tmp_path):
    from voly.intelligence.security_scanner import scan

    (tmp_path / "clean.py").write_text("def hello(): return 42\n")
    risks = scan(str(tmp_path))
    assert isinstance(risks, list)
    assert len(risks) == 0


def test_security_scanner_detects_eval(tmp_path):
    from voly.intelligence.security_scanner import scan

    (tmp_path / "bad.py").write_text("result = eval(user_input)\n")
    risks = scan(str(tmp_path))
    assert any("eval" in r for r in risks)


def test_dep_analyzer_empty(tmp_path):
    from voly.intelligence.dependency_analyzer import analyze_dependencies

    result = analyze_dependencies(str(tmp_path))
    assert result == {}


def test_dep_analyzer_package_json(tmp_path):
    import json

    from voly.intelligence.dependency_analyzer import analyze_dependencies

    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^19.0.0", "typescript": "^5.0"}})
    )
    result = analyze_dependencies(str(tmp_path))
    assert "node" in result
    assert "react" in result["node"]
