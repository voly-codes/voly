"""PR2: plan acceptance verifiers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from voly.plan import (
    DONE,
    FAILED,
    RUNNING,
    VERIFIED,
    VERIFYING,
    AcceptanceCheck,
    PlanEngine,
    PlanStep,
    create_plan,
)
from voly.plan.verify import (
    CHECK_COMMAND,
    CHECK_FILES_EXIST,
    CHECK_FILES_MISSING,
    CHECK_GIT_DIFF_CONTAINS,
    CHECK_GIT_DIFF_NONEMPTY,
    CHECK_FILE_LINE_LIMIT,
    CHECK_OUTPUT_NONEMPTY,
    CHECK_OUTPUT_REGEX,
    VerifyContext,
    VerifyError,
    all_passed,
    changed_paths,
    complete_verification,
    run_acceptance,
    run_check,
    safe_join,
    verify_step,
)


@pytest.fixture()
def engine() -> PlanEngine:
    return PlanEngine()


@pytest.fixture()
def cwd(tmp_path: Path) -> Path:
    return tmp_path


# ── Path jail ────────────────────────────────────────────────────────────────


def test_safe_join_under_cwd(cwd: Path) -> None:
    (cwd / "src").mkdir()
    (cwd / "src" / "a.py").write_text("x")
    p = safe_join(str(cwd), "src/a.py")
    assert p.is_file()


def test_safe_join_rejects_escape(cwd: Path) -> None:
    with pytest.raises(VerifyError, match="escapes"):
        safe_join(str(cwd), "../outside")


# ── files_exist / files_missing ──────────────────────────────────────────────


def test_files_exist_pass_fail(cwd: Path) -> None:
    (cwd / "ok.txt").write_text("1")
    ctx = VerifyContext(cwd=str(cwd))
    ok = run_check(AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["ok.txt"]), ctx)
    assert ok.ok
    bad = run_check(AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["nope.txt"]), ctx)
    assert not bad.ok
    assert "missing" in bad.message


def test_files_missing_pass_fail(cwd: Path) -> None:
    (cwd / "keep.txt").write_text("1")
    ctx = VerifyContext(cwd=str(cwd))
    ok = run_check(AcceptanceCheck(type=CHECK_FILES_MISSING, paths=["gone.txt"]), ctx)
    assert ok.ok
    bad = run_check(AcceptanceCheck(type=CHECK_FILES_MISSING, paths=["keep.txt"]), ctx)
    assert not bad.ok


def test_files_exist_path_escape_fails(cwd: Path) -> None:
    ctx = VerifyContext(cwd=str(cwd))
    r = run_check(AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["../x"]), ctx)
    assert not r.ok
    assert "escapes" in r.message


# ── command ──────────────────────────────────────────────────────────────────


def test_command_success(cwd: Path) -> None:
    ctx = VerifyContext(cwd=str(cwd), command_timeout=10)
    r = run_check(AcceptanceCheck(type=CHECK_COMMAND, run="true"), ctx)
    assert r.ok
    assert r.detail["returncode"] == 0


def test_command_expect_exit(cwd: Path) -> None:
    ctx = VerifyContext(cwd=str(cwd), command_timeout=10)
    r = run_check(
        AcceptanceCheck(type=CHECK_COMMAND, run="false", expect_exit=1),
        ctx,
    )
    assert r.ok


def test_command_failure(cwd: Path) -> None:
    ctx = VerifyContext(cwd=str(cwd), command_timeout=10)
    r = run_check(AcceptanceCheck(type=CHECK_COMMAND, run="false"), ctx)
    assert not r.ok


def test_command_timeout(cwd: Path) -> None:
    ctx = VerifyContext(cwd=str(cwd), command_timeout=0.3)
    r = run_check(
        AcceptanceCheck(type=CHECK_COMMAND, run="sleep 5"),
        ctx,
    )
    assert not r.ok
    assert "timeout" in r.message


def test_command_requires_run_and_cwd() -> None:
    r = run_check(AcceptanceCheck(type=CHECK_COMMAND, run=""), VerifyContext(cwd="/tmp"))
    assert not r.ok
    r2 = run_check(AcceptanceCheck(type=CHECK_COMMAND, run="true"), VerifyContext())
    assert not r2.ok


def test_command_python_write_then_exist(cwd: Path) -> None:
    script = cwd / "w.py"
    script.write_text("open('out.txt','w').write('hi')\n")
    ctx = VerifyContext(cwd=str(cwd), command_timeout=15)
    r = run_check(
        AcceptanceCheck(type=CHECK_COMMAND, run=f"python3 {script.name}"),
        ctx,
    )
    assert r.ok
    assert (cwd / "out.txt").read_text() == "hi"


# ── output ───────────────────────────────────────────────────────────────────


def test_output_nonempty() -> None:
    assert run_check(
        AcceptanceCheck(type=CHECK_OUTPUT_NONEMPTY),
        VerifyContext(output="  hello "),
    ).ok
    assert not run_check(
        AcceptanceCheck(type=CHECK_OUTPUT_NONEMPTY),
        VerifyContext(output="  \n"),
    ).ok


def test_output_regex() -> None:
    ctx = VerifyContext(output="Status: DONE\nfiles: 3")
    assert run_check(
        AcceptanceCheck(type=CHECK_OUTPUT_REGEX, pattern=r"Status:\s*DONE"),
        ctx,
    ).ok
    assert not run_check(
        AcceptanceCheck(type=CHECK_OUTPUT_REGEX, pattern=r"FAILED"),
        ctx,
    ).ok


def test_output_regex_invalid_pattern() -> None:
    r = run_check(
        AcceptanceCheck(type=CHECK_OUTPUT_REGEX, pattern="[unterminated"),
        VerifyContext(output="x"),
    )
    assert not r.ok
    assert "invalid" in r.message


# ── file line limit ──────────────────────────────────────────────────────────


def test_file_line_limit_passes_at_300_and_fails_at_301(cwd: Path) -> None:
    path = cwd / "module.py"
    ctx = VerifyContext(cwd=str(cwd), files_touched=["module.py"])
    check = AcceptanceCheck(
        type=CHECK_FILE_LINE_LIMIT,
        max_lines=300,
        approved_max_lines=500,
    )

    path.write_text("x\n" * 300)
    passed = run_check(check, ctx)
    assert passed.ok
    assert passed.detail["checked"]["module.py"] == 300
    assert passed.detail["limit"] == 300

    path.write_text("x\n" * 301)
    failed = run_check(check, ctx)
    assert not failed.ok
    assert failed.detail["violations"] == {"module.py": 301}


def test_file_line_limit_uses_strict_architect_approval(cwd: Path) -> None:
    (cwd / "large.py").write_text("x\n" * 450)
    check = AcceptanceCheck(
        type=CHECK_FILE_LINE_LIMIT,
        max_lines=300,
        approved_max_lines=500,
    )
    plan = create_plan(
        "line-approval",
        [
            PlanStep(
                id="arch",
                role="architect",
                output=(
                    "FILE_LINE_LIMIT: 500\n"
                    "FILE_LINE_LIMIT_REASON: cohesive generated parser requires one module"
                ),
            ),
            PlanStep(
                id="dev",
                role="developer",
                depends_on=["arch"],
                acceptance=[check],
                files_touched=["large.py"],
            ),
        ],
        cwd=str(cwd),
    )

    approved = verify_step(plan, "dev")
    assert approved[0].ok
    assert approved[0].detail["limit"] == 500
    assert approved[0].detail["architect_approved"] is True

    plan.get_step("arch").output = "FILE_LINE_LIMIT: 500"  # no rationale
    rejected = verify_step(plan, "dev")
    assert not rejected[0].ok
    assert rejected[0].detail["limit"] == 300


def test_file_line_limit_fails_without_changed_file_evidence(cwd: Path) -> None:
    result = run_check(
        AcceptanceCheck(type=CHECK_FILE_LINE_LIMIT, max_lines=300),
        VerifyContext(cwd=str(cwd)),
    )
    assert not result.ok
    assert "no changed files" in result.message


# ── file_line_limit generated-file exclusions ─────────────────────────────────


def test_file_line_limit_skips_builtin_lock_files(cwd: Path) -> None:
    """package-lock.json and other lock files are always excluded regardless of size."""
    lock = cwd / "package-lock.json"
    lock.write_text("x\n" * 5000)
    real = cwd / "app.py"
    real.write_text("x\n" * 10)
    ctx = VerifyContext(cwd=str(cwd), files_touched=["package-lock.json", "app.py"])
    result = run_check(AcceptanceCheck(type=CHECK_FILE_LINE_LIMIT, max_lines=300), ctx)
    assert result.ok, result.message
    assert "package-lock.json" in result.detail["skipped_generated"]
    assert "app.py" in result.detail["checked"]


@pytest.mark.parametrize("lockfile", [
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    ".coverage",
])
def test_file_line_limit_skips_all_builtin_lockfiles(cwd: Path, lockfile: str) -> None:
    (cwd / lockfile).write_text("x\n" * 9999)
    ctx = VerifyContext(cwd=str(cwd), files_touched=[lockfile])
    result = run_check(AcceptanceCheck(type=CHECK_FILE_LINE_LIMIT, max_lines=300), ctx)
    # A single generated file produces "no changed files available" because all
    # candidates were skipped — that is also a non-violation (not a size error).
    assert not result.detail.get("violations"), result.detail


def test_file_line_limit_skips_node_modules_prefix(cwd: Path) -> None:
    nm = cwd / "node_modules" / "lodash"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("x\n" * 2000)
    ctx = VerifyContext(
        cwd=str(cwd), files_touched=["node_modules/lodash/index.js"]
    )
    result = run_check(AcceptanceCheck(type=CHECK_FILE_LINE_LIMIT, max_lines=300), ctx)
    assert not result.detail.get("violations")
    assert "node_modules/lodash/index.js" in result.detail.get("skipped_generated", [])


def test_file_line_limit_extra_exclude_patterns(cwd: Path) -> None:
    """AcceptanceCheck.exclude_patterns adds custom project-specific exclusions."""
    gen = cwd / "generated_schema.json"
    gen.write_text("x\n" * 1000)
    ctx = VerifyContext(cwd=str(cwd), files_touched=["generated_schema.json"])
    check = AcceptanceCheck(
        type=CHECK_FILE_LINE_LIMIT,
        max_lines=300,
        exclude_patterns=["generated_schema.json"],
    )
    result = run_check(check, ctx)
    assert not result.detail.get("violations")
    assert "generated_schema.json" in result.detail.get("skipped_generated", [])


def test_file_line_limit_real_violation_still_caught(cwd: Path) -> None:
    """Regular source files over the limit still fail even with generated-file exclusions."""
    (cwd / "package-lock.json").write_text("x\n" * 5000)
    (cwd / "big_module.py").write_text("x\n" * 500)
    ctx = VerifyContext(
        cwd=str(cwd),
        files_touched=["package-lock.json", "big_module.py"],
    )
    result = run_check(AcceptanceCheck(type=CHECK_FILE_LINE_LIMIT, max_lines=300), ctx)
    assert not result.ok
    assert "big_module.py" in result.detail["violations"]
    assert "package-lock.json" not in result.detail.get("violations", {})


# ── git diff ─────────────────────────────────────────────────────────────────


def test_changed_paths() -> None:
    before = {"a.py": "M", "b.py": "?"}
    after = {"a.py": "M", "c.py": "A"}
    # b disappeared, c appeared; a same
    assert changed_paths(before, after) == {"b.py", "c.py"}


def test_git_diff_nonempty_with_snapshots() -> None:
    ctx = VerifyContext(
        git_before={},
        git_after={"src/x.py": "A"},
    )
    r = run_check(AcceptanceCheck(type=CHECK_GIT_DIFF_NONEMPTY), ctx)
    assert r.ok
    assert "src/x.py" in r.detail["changed"]


def test_git_diff_nonempty_empty() -> None:
    ctx = VerifyContext(git_before={}, git_after={})
    r = run_check(AcceptanceCheck(type=CHECK_GIT_DIFF_NONEMPTY), ctx)
    assert not r.ok


def test_git_diff_nonempty_paths_filter() -> None:
    ctx = VerifyContext(
        git_before={},
        git_after={"src/a.py": "A", "docs/x.md": "A"},
    )
    r = run_check(
        AcceptanceCheck(type=CHECK_GIT_DIFF_NONEMPTY, paths=["src/"]),
        ctx,
    )
    assert r.ok
    assert r.detail["changed"] == ["src/a.py"]

    r2 = run_check(
        AcceptanceCheck(type=CHECK_GIT_DIFF_NONEMPTY, paths=["lib/"]),
        ctx,
    )
    assert not r2.ok


def test_git_diff_contains_paths() -> None:
    ctx = VerifyContext(git_before={}, git_after={"pkg/mod.py": "M", "README.md": "M"})
    r = run_check(
        AcceptanceCheck(type=CHECK_GIT_DIFF_CONTAINS, paths=["pkg/mod.py"]),
        ctx,
    )
    assert r.ok
    r2 = run_check(
        AcceptanceCheck(type=CHECK_GIT_DIFF_CONTAINS, paths=["missing.py"]),
        ctx,
    )
    assert not r2.ok


def test_git_diff_contains_pattern() -> None:
    ctx = VerifyContext(git_before={}, git_after={"tests/test_a.py": "A", "src/a.py": "M"})
    r = run_check(
        AcceptanceCheck(type=CHECK_GIT_DIFF_CONTAINS, pattern=r"^tests/"),
        ctx,
    )
    assert r.ok
    assert r.detail["hits"] == ["tests/test_a.py"]


def test_git_diff_contains_uses_files_touched_fallback() -> None:
    ctx = VerifyContext(files_touched=["generated.py"])
    r = run_check(
        AcceptanceCheck(type=CHECK_GIT_DIFF_CONTAINS, paths=["generated.py"]),
        ctx,
    )
    assert r.ok


def test_git_porcelain_live_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@test"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    (tmp_path / "f.txt").write_text("x")
    # untracked → porcelain non-empty
    ctx = VerifyContext(cwd=str(tmp_path))
    r = run_check(AcceptanceCheck(type=CHECK_GIT_DIFF_NONEMPTY), ctx)
    assert r.ok


# ── fail closed / batch ──────────────────────────────────────────────────────


def test_ensure_git_repo_seeds_commit(tmp_path: Path) -> None:
    from voly.executor.safety import git_snapshot
    from voly.plan.verify import _git_has_commits, ensure_git_repo

    # Empty dir → init + seed commit; snapshot must return a valid SHA.
    result = ensure_git_repo(str(tmp_path))
    assert result is True
    assert _git_has_commits(str(tmp_path))
    snap = git_snapshot(str(tmp_path))
    assert len(snap) == 40, f"expected 40-char SHA, got {snap!r}"


def test_ensure_git_repo_existing_with_commits(tmp_path: Path) -> None:
    from voly.plan.verify import _git_has_commits, ensure_git_repo

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    # Repo already has commits — ensure_git_repo should do nothing (return False).
    result = ensure_git_repo(str(tmp_path))
    assert result is False
    assert _git_has_commits(str(tmp_path))


def test_ensure_git_repo_git_exists_no_commits(tmp_path: Path) -> None:
    from voly.executor.safety import git_snapshot
    from voly.plan.verify import ensure_git_repo

    # .git exists but no commits yet (the pre-fix scenario for TEST_VOLY_JOB_MA).
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    result = ensure_git_repo(str(tmp_path))
    assert result is True
    snap = git_snapshot(str(tmp_path))
    assert len(snap) == 40, f"safety snapshot must be valid after seed: {snap!r}"


def test_unknown_type_fail_closed() -> None:
    r = run_check(AcceptanceCheck(type="llm_judge"), VerifyContext())
    assert not r.ok
    assert "unknown" in r.message
    assert "fail closed" in r.message


def test_run_acceptance_stop_on_fail(cwd: Path) -> None:
    (cwd / "a.txt").write_text("1")
    results = run_acceptance(
        [
            AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["missing.txt"]),
            AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["a.txt"]),
        ],
        VerifyContext(cwd=str(cwd)),
        stop_on_fail=True,
    )
    assert len(results) == 1
    assert not results[0].ok


def test_all_passed() -> None:
    ctx = VerifyContext(output="ok")
    results = run_acceptance(
        [AcceptanceCheck(type=CHECK_OUTPUT_NONEMPTY)],
        ctx,
    )
    assert all_passed(results)
    assert not all_passed([])


# ── Engine integration: complete_verification ────────────────────────────────


def test_complete_verification_pass(engine: PlanEngine, cwd: Path) -> None:
    (cwd / "mod.py").write_text("print(1)\n")
    plan = create_plan(
        "v1",
        [
            PlanStep(
                id="impl",
                acceptance=[
                    AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["mod.py"]),
                    AcceptanceCheck(type=CHECK_OUTPUT_NONEMPTY),
                ],
            ),
        ],
        cwd=str(cwd),
    )
    engine.transition(plan, "impl", RUNNING)
    engine.transition(plan, "impl", DONE)
    engine.transition(plan, "impl", VERIFYING)
    plan.get_step("impl").output = "wrote mod.py"

    step, results = complete_verification(
        plan,
        "impl",
        VerifyContext(cwd=str(cwd), output="wrote mod.py"),
        engine=engine,
    )
    assert step.status == VERIFIED
    assert all_passed(results)
    assert plan.status == "completed"
    assert len(step.verify_log) == 2


def test_complete_verification_fail(engine: PlanEngine, cwd: Path) -> None:
    plan = create_plan(
        "v2",
        [
            PlanStep(
                id="impl",
                acceptance=[AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["nope.py"])],
            ),
        ],
        cwd=str(cwd),
    )
    engine.transition(plan, "impl", RUNNING)
    engine.transition(plan, "impl", DONE)
    engine.advance_after_done(plan, "impl")
    assert plan.get_step("impl").status == VERIFYING

    step, results = complete_verification(plan, "impl", engine=engine)
    assert step.status == FAILED
    assert not all_passed(results)
    assert "files_exist" in step.error


def test_verify_step_writes_log_without_transition(engine: PlanEngine, cwd: Path) -> None:
    plan = create_plan(
        "v3",
        [PlanStep(id="s", acceptance=[AcceptanceCheck(type=CHECK_OUTPUT_NONEMPTY)])],
        cwd=str(cwd),
    )
    plan.get_step("s").output = "hi"
    plan.get_step("s").status = VERIFYING
    results = verify_step(plan, "s")
    assert all_passed(results)
    assert plan.get_step("s").status == VERIFYING  # unchanged
    assert plan.get_step("s").verify_log[0]["ok"] is True


def test_gate_still_blocks_until_verified(engine: PlanEngine, cwd: Path) -> None:
    """End-to-end: failed verify keeps next step gated."""
    plan = create_plan(
        "chain",
        [
            PlanStep(
                id="a",
                acceptance=[AcceptanceCheck(type=CHECK_FILES_EXIST, paths=["x.py"])],
            ),
            PlanStep(id="b", depends_on=["a"]),
        ],
        cwd=str(cwd),
    )
    engine.transition(plan, "a", RUNNING)
    engine.mark_execution_finished(plan, "a", success=True)
    engine.advance_after_done(plan, "a")
    complete_verification(plan, "a", engine=engine)
    assert plan.get_step("a").status == FAILED
    assert engine.can_start(plan, "b") is False
