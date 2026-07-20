"""Unit tests for voly.reuse (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from voly.reuse.apply import ApplyError, _safe_join, apply_picks
from voly.reuse.github_search import RepoHit, search_repositories, task_to_query
from voly.reuse.license import (
    detect_license_from_text,
    is_allowed,
    normalize_spdx,
    resolve_license,
)
from voly.reuse.pack import build_tree, pack_repo, score_relevant_files
from voly.reuse.report import (
    CandidatePack,
    PickedModule,
    ReuseReport,
    load_report,
    save_report,
)


def test_import_reuse_without_token():
    import voly.reuse  # noqa: F401
    from voly.reuse import ReuseReport as RR

    assert RR is not None


def test_normalize_and_allow_deny():
    assert normalize_spdx("MIT") == "mit"
    assert normalize_spdx("Apache-2.0") == "apache-2.0"
    assert is_allowed("mit")
    assert is_allowed("apache-2.0")
    assert not is_allowed("gpl-3.0")
    assert not is_allowed("agpl-3.0")
    assert not is_allowed("")
    assert not is_allowed(None)


def test_format_reuse_context(tmp_path: Path):
    from voly.reuse.context import format_reuse_context

    reports = tmp_path / ".voly" / "reuse" / "reports"
    report = ReuseReport(
        task="retry helper",
        candidates=[CandidatePack(full_name="a/b", stars=10, license_spdx="mit", license_allowed=True)],
        picked=[PickedModule(path="retry.py", repo="a/b", confidence=0.7)],
    )
    save_report(report, reports)
    block = format_reuse_context(tmp_path)
    assert "Code reuse report" in block
    assert "a/b" in block
    assert "retry.py" in block


def test_detect_license_from_text():
    mit = "MIT License\n\nCopyright (c) 2020"
    assert detect_license_from_text(mit) == "mit"
    gpl = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007"
    assert detect_license_from_text(gpl) == "gpl-3.0"


def test_resolve_license_prefers_github(tmp_path: Path):
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    assert resolve_license(github_spdx="apache-2.0", repo_dir=tmp_path) == "apache-2.0"
    assert resolve_license(github_spdx="", repo_dir=tmp_path) == "mit"


def test_report_serialize_roundtrip(tmp_path: Path):
    report = ReuseReport(
        task="add jwt auth",
        query="jwt auth",
        candidates=[
            CandidatePack(
                full_name="acme/jwt",
                stars=100,
                license_spdx="mit",
                license_allowed=True,
            )
        ],
        picked=[PickedModule(path="src/jwt.py", repo="acme/jwt", confidence=0.8)],
    )
    path = save_report(report, tmp_path)
    assert path.is_file()
    assert (tmp_path / "latest.json").is_file()
    loaded = load_report(path)
    assert loaded.task == "add jwt auth"
    assert loaded.candidates[0].full_name == "acme/jwt"
    assert loaded.picked[0].path == "src/jwt.py"
    assert json.loads(path.read_text())["report_id"] == loaded.report_id


def test_task_to_query():
    q = task_to_query("Implement JWT authentication middleware for FastAPI")
    assert "jwt" in q.lower() or "authentication" in q.lower() or "fastapi" in q.lower()
    assert "in:name,description" in q
    assert "readme" not in q


def test_task_to_query_cyrillic_and_tech_normalize():
    from voly.reuse.github_search import infer_language

    q = task_to_query("Создай 3D игру танчики в браузере на Three.js с физикой и HUD")
    low = q.lower()
    assert "tank" in low
    assert "game" in low or "browser" in low
    assert "threejs" in low
    assert "language:typescript" in low
    assert "library utility" not in low
    assert infer_language("Three.js tank game") == "TypeScript"
    ru_only = task_to_query("Нужен симулятор завода с датчиками")
    assert "factory" in ru_only or "sensor" in ru_only or "simulation" in ru_only
    assert "library utility" not in ru_only


def test_github_search_mocked():
    payload = {
        "items": [
            {
                "full_name": "tiangolo/fastapi",
                "html_url": "https://github.com/tiangolo/fastapi",
                "clone_url": "https://github.com/tiangolo/fastapi.git",
                "description": "FastAPI framework",
                "stargazers_count": 70000,
                "language": "Python",
                "license": {"spdx_id": "MIT"},
                "default_branch": "master",
                "topics": ["fastapi"],
            }
        ]
    }

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode()

    with patch("voly.reuse.github_search.urllib.request.urlopen", return_value=FakeResp()):
        hits = search_repositories("fastapi", limit=3, min_stars=0)
    assert len(hits) == 1
    assert hits[0].full_name == "tiangolo/fastapi"
    assert hits[0].license_spdx == "mit"
    assert hits[0].stars == 70000


def test_pack_fixture_repo(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth_jwt.py").write_text(
        "def create_token():\n    return 'jwt'\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Auth JWT helper\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    tree = build_tree(tmp_path)
    assert "src/" in tree
    assert "auth_jwt.py" in tree

    files = score_relevant_files(tmp_path, ["jwt", "auth"])
    assert any("auth_jwt" in f for f in files)

    cand = CandidatePack(full_name="demo/auth", stars=1, license_spdx="mit", license_allowed=True)
    packed = pack_repo(tmp_path, task="add JWT auth helper", candidate=cand)
    assert packed.relevant_files
    assert packed.pack_chars > 0


def test_safe_join_blocks_escape(tmp_path: Path):
    with pytest.raises(ApplyError):
        _safe_join(tmp_path, "../outside")
    with pytest.raises(ApplyError):
        _safe_join(tmp_path, "foo/../../etc/passwd")
    ok = _safe_join(tmp_path, "vendor/reuse/x.py")
    assert str(ok).startswith(str(tmp_path.resolve()))


def test_apply_dry_run_and_write(tmp_path: Path):
    src_repo = tmp_path / "cache" / "acme__lib"
    (src_repo / "pkg").mkdir(parents=True)
    (src_repo / "pkg" / "util.py").write_text("X = 1\n", encoding="utf-8")
    (src_repo / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    dest_cwd = tmp_path / "project"
    dest_cwd.mkdir()

    report = ReuseReport(
        task="reuse util",
        candidates=[
            CandidatePack(
                full_name="acme/lib",
                license_spdx="mit",
                license_allowed=True,
                cache_path=str(src_repo),
                html_url="https://github.com/acme/lib",
            )
        ],
        picked=[PickedModule(path="pkg/util.py", repo="acme/lib", confidence=0.9)],
    )

    dry = apply_picks(report, cwd=dest_cwd, dest_rel="vendor/reuse", dry_run=True)
    assert dry.apply_actions[0].status == "planned"
    assert not (dest_cwd / "vendor").exists()

    # GPL block
    report.candidates[0].license_spdx = "gpl-3.0"
    blocked = apply_picks(report, cwd=dest_cwd, dry_run=False)
    assert blocked.apply_actions[0].status == "blocked"

    report.candidates[0].license_spdx = "mit"
    written = apply_picks(report, cwd=dest_cwd, dest_rel="vendor/reuse", dry_run=False)
    assert written.apply_actions[0].status == "copied"
    assert (dest_cwd / "vendor/reuse/acme__lib/pkg/util.py").is_file()
    assert (dest_cwd / "vendor/reuse/acme__lib/NOTICE").is_file()


def test_reuse_config_parsed():
    from voly.config._parser import _parse_config

    cfg = _parse_config({
        "reuse": {
            "enabled": True,
            "max_repos": 3,
            "min_stars": 50,
            "allowed_licenses": ["mit"],
            "deny_licenses": ["gpl-3.0"],
            "auto": True,
            "auto_max_repos": 2,
            "auto_max_age_seconds": 3600,
        }
    })
    assert cfg.reuse.max_repos == 3
    assert cfg.reuse.min_stars == 50
    assert "mit" in cfg.reuse.allowed_licenses
    assert cfg.reuse.auto is True
    assert cfg.reuse.auto_max_repos == 2
    assert cfg.reuse.auto_max_age_seconds == 3600


def test_auto_reuse_skips_only_usable_fresh_report(tmp_path: Path):
    """Empty / all-denied fresh reports must not block a new search."""
    from voly.config import VOLYConfig
    from voly.reuse.pipeline import auto_reuse

    reports = tmp_path / ".voly" / "reuse" / "reports"
    empty = ReuseReport(task="old", query="x", candidates=[])
    save_report(empty, reports)

    cfg = VOLYConfig()
    cfg.reuse.auto = True
    cfg.reuse.auto_max_age_seconds = 604800
    cfg.reuse.reports_dir = ".voly/reuse/reports"

    with patch("voly.reuse.pipeline.search_and_pack") as sp, patch(
        "voly.reuse.pipeline.pick_modules", return_value=[]
    ):
        sp.return_value = ReuseReport(
            task="new",
            query="browser tank game",
            candidates=[
                CandidatePack(
                    full_name="acme/tanks",
                    stars=40,
                    license_spdx="mit",
                    license_allowed=True,
                )
            ],
        )
        out = auto_reuse("browser tank game", cwd=tmp_path, config=cfg, gateway=None)
        assert out is not None
        assert sp.called
        assert any(c.full_name == "acme/tanks" for c in out.candidates)

    # Usable fresh report → skip
    with patch("voly.reuse.pipeline.search_and_pack") as sp2:
        skipped = auto_reuse("again", cwd=tmp_path, config=cfg, gateway=None)
        assert skipped is None
        assert not sp2.called
