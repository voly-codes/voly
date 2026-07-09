"""PR5: criteria compiler + scanner suggestions."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from voly.cli.main import main
from voly.plan.criteria import compile_success_criteria, criteria_to_acceptance
from voly.plan.loader import load_plan_file
from voly.plan.suggest import suggest_from_cwd, suggest_test_command
from voly.scanner import LanguageInfo, ProjectProfile


def test_compile_files_and_tests():
    text = """
    - create src/auth.py and src/auth_test.py
    - tests pass with pytest
    - output contains DONE
    """
    draft = compile_success_criteria(text)
    assert draft.review_required is True
    types = {c.type for c in draft.checks}
    assert "files_exist" in types
    assert "command" in types
    assert any(c.type == "command" and "pytest" in c.run for c in draft.checks)
    paths = []
    for c in draft.checks:
        paths.extend(c.paths)
    assert "src/auth.py" in paths


def test_compile_git_diff():
    draft = compile_success_criteria("code changes in lib/foo.py")
    assert any(c.type in ("git_diff_contains", "git_diff_nonempty", "files_exist") for c in draft.checks)


def test_compile_empty():
    draft = compile_success_criteria("")
    assert draft.checks == []
    assert draft.notes


def test_criteria_to_acceptance_helper():
    checks = criteria_to_acceptance("- file a.py exists\n- npm test passes")
    assert checks
    assert any(c.type == "files_exist" for c in checks)


def test_yaml_fragment():
    draft = compile_success_criteria("- create app/main.py")
    frag = draft.to_yaml_fragment()
    assert "acceptance:" in frag
    assert "files_exist" in frag


def test_suggest_test_command_python():
    profile = ProjectProfile(
        name="p",
        path="/x",
        languages=[LanguageInfo(name="python")],
        test_frameworks=["pytest"],
    )
    assert suggest_test_command(profile) == "pytest -q"


def test_suggest_test_command_npm():
    profile = ProjectProfile(
        name="p",
        path="/x",
        package_managers=["npm"],
        test_frameworks=["jest"],
    )
    assert "npm test" in suggest_test_command(profile)


def test_suggest_from_cwd_python_project(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    sug = suggest_from_cwd(str(tmp_path))
    assert sug.notes
    # may or may not detect pytest without tests dir — still returns structure
    assert isinstance(sug.test_command, str)


def test_loader_drafts_acceptance_from_success_criteria(tmp_path: Path):
    path = tmp_path / "p.yaml"
    path.write_text(
        yaml.dump({
            "plan_id": "crit",
            "steps": [
                {
                    "id": "impl",
                    "mode": "executor",
                    "task": "add file",
                    "success_criteria": "- create src/x.py\n- tests pass",
                },
            ],
        }),
        encoding="utf-8",
    )
    plan = load_plan_file(path)
    step = plan.steps[0]
    assert step.success_criteria
    assert step.acceptance  # drafted
    assert any(c.type == "files_exist" for c in step.acceptance)


def test_cli_criteria():
    r = CliRunner().invoke(
        main,
        ["plan", "criteria", "--yaml", "--", "create foo.py\npytest passes"],
    )
    assert r.exit_code == 0, r.output
    assert "acceptance:" in r.output
    assert "files_exist" in r.output or "command" in r.output


def test_cli_suggest(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    r = CliRunner().invoke(main, ["plan", "suggest", "--cwd", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "DRAFT" in r.output
