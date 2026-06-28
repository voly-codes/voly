"""Tests for Project Scanner."""

from pathlib import Path

import pytest

from codeops.scanner import ProjectScanner, ProjectProfile, generate_project_skills

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent


def test_scanner_detects_python_project() -> None:
    scanner = ProjectScanner(str(_PROJECT_ROOT))
    profile = scanner.scan()
    assert isinstance(profile, ProjectProfile)
    assert profile.name == _PROJECT_ROOT.name

    lang_names = [l.name for l in profile.languages]
    assert "python" in lang_names

    assert "pip" in profile.package_managers or "uv" in profile.package_managers


def test_scanner_detects_rust() -> None:
    scanner = ProjectScanner(str(_PROJECT_ROOT))
    profile = scanner.scan()
    assert isinstance(profile, ProjectProfile)
    lang_names = [l.name for l in profile.languages]
    assert "rust" in lang_names


def test_scanner_detects_headroom() -> None:
    headroom_path = _PROJECT_ROOT / "headroom"
    if not headroom_path.is_dir():
        pytest.skip("headroom directory not found")
    scanner = ProjectScanner(str(headroom_path))
    profile = scanner.scan()
    assert isinstance(profile, ProjectProfile)
    lang_names = [l.name for l in profile.languages]
    assert "python" in lang_names


def test_profile_to_dict() -> None:
    scanner = ProjectScanner(str(_PROJECT_ROOT))
    profile = scanner.scan()
    d = profile.to_dict()
    assert "languages" in d
    assert "frameworks" in d
    assert "architecture" in d


def test_generate_project_skills() -> None:
    scanner = ProjectScanner(str(_PROJECT_ROOT))
    profile = scanner.scan()
    skills = generate_project_skills(profile)
    assert len(skills) > 0
    for skill in skills:
        assert "id" in skill
        assert "name" in skill
        assert "source" in skill
