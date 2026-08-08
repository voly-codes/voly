from pathlib import Path

import pytest

from scripts.check_release_version import declared_version, main


def test_declared_version_reads_project_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")

    assert declared_version(pyproject) == "1.2.3"


def test_release_tag_must_match_declared_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["check_release_version", "v1.2.4", "--pyproject", str(pyproject)]
    )

    with pytest.raises(SystemExit, match="1"):
        main()
