"""PR3: PlanRunner + loader + config + CLI smoke (mocked executors)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from voly.cli.main import main
from voly.config import PlanConfig, VOLYConfig, load_config
from voly.plan import (
    FAILED,
    MODE_CHAT,
    MODE_EXECUTOR,
    PLAN_COMPLETED,
    PLAN_FAILED,
    VERIFIED,
    AcceptanceCheck,
    PlanRunner,
    PlanStep,
    PlanStore,
    create_plan,
    load_plan_file,
)


@pytest.fixture()
def cfg(tmp_path: Path) -> VOLYConfig:
    c = VOLYConfig()
    c.plan = PlanConfig(
        enabled=True,
        mode="active",
        store_dir=str(tmp_path / "plans"),
        max_step_retries=0,
        default_on_verify_fail="stop",
        command_timeout_seconds=10,
    )
    c.telemetry.enabled = False
    c.default_cwd = str(tmp_path / "proj")
    (tmp_path / "proj").mkdir()
    return c


def test_load_plan_yaml(tmp_path: Path) -> None:
    path = tmp_path / "demo.yaml"
    path.write_text(
        yaml.dump({
            "plan_id": "demo",
            "cwd": str(tmp_path),
            "task": "demo task",
            "steps": [
                {
                    "id": "write",
                    "role": "developer",
                    "mode": "executor",
                    "task": "write file",
                    "acceptance": [{"type": "files_exist", "paths": ["a.txt"]}],
                },
                {
                    "id": "check",
                    "role": "reviewer",
                    "mode": "chat",
                    "depends_on": ["write"],
                    "task": "review",
                },
            ],
        }),
        encoding="utf-8",
    )
    plan = load_plan_file(path)
    assert plan.plan_id == "demo"
    assert plan.steps[0].task == "write file"
    assert plan.steps[1].depends_on == ["write"]


def test_two_step_active_success(cfg: VOLYConfig, tmp_path: Path) -> None:
    proj = Path(cfg.default_cwd)

    def exec_fn(step, plan, instruction):
        (proj / "hello.txt").write_text("hi\n", encoding="utf-8")
        return True, "wrote hello.txt", "", ["hello.txt"]

    def chat_fn(step, plan, instruction):
        return True, "looks good", ""

    plan = create_plan(
        "two",
        [
            PlanStep(
                id="write",
                role="developer",
                mode=MODE_EXECUTOR,
                task="create hello.txt",
                acceptance=[
                    AcceptanceCheck(type="files_exist", paths=["hello.txt"]),
                ],
            ),
            PlanStep(
                id="review",
                role="reviewer",
                mode=MODE_CHAT,
                depends_on=["write"],
                task="review hello.txt",
                acceptance=[AcceptanceCheck(type="output_nonempty")],
            ),
        ],
        cwd=str(proj),
        task="two-step demo",
    )

    runner = PlanRunner(
        cfg, chat_fn=chat_fn, executor_fn=exec_fn, emit_event=False
    )
    result = runner.run(plan, mode="active")
    assert result.success
    assert result.plan.status == PLAN_COMPLETED
    assert result.plan.get_step("write").status == VERIFIED
    assert result.plan.get_step("review").status == VERIFIED
    assert (proj / "hello.txt").read_text() == "hi\n"

    # persisted
    store = PlanStore(cfg.plan.store_dir)
    loaded = store.load("two")
    assert loaded is not None and loaded.status == PLAN_COMPLETED


def test_verify_fail_stops_active(cfg: VOLYConfig, tmp_path: Path) -> None:
    proj = Path(cfg.default_cwd)

    def exec_fn(step, plan, instruction):
        # claim success but do not create the file
        return True, "done", "", []

    def chat_fn(step, plan, instruction):
        return True, "should not run", ""

    plan = create_plan(
        "fail",
        [
            PlanStep(
                id="write",
                mode=MODE_EXECUTOR,
                task="should create missing.txt",
                acceptance=[
                    AcceptanceCheck(type="files_exist", paths=["missing.txt"]),
                ],
            ),
            PlanStep(
                id="next",
                mode=MODE_CHAT,
                depends_on=["write"],
                task="blocked",
            ),
        ],
        cwd=str(proj),
    )

    ran_chat = {"n": 0}

    def chat_count(step, plan, instruction):
        ran_chat["n"] += 1
        return True, "x", ""

    runner = PlanRunner(
        cfg, chat_fn=chat_count, executor_fn=exec_fn, emit_event=False
    )
    result = runner.run(plan, mode="active")
    assert not result.success
    assert result.plan.get_step("write").status == FAILED
    assert result.plan.get_step("next").status == "pending"
    assert ran_chat["n"] == 0  # gate blocked second step
    assert result.plan.status == PLAN_FAILED


def test_shadow_verify_fail_opens_gate(cfg: VOLYConfig, tmp_path: Path) -> None:
    proj = Path(cfg.default_cwd)
    cfg.plan.mode = "shadow"

    def exec_fn(step, plan, instruction):
        return True, "no file", "", []

    ran = {"chat": 0}

    def chat_fn(step, plan, instruction):
        ran["chat"] += 1
        return True, "reviewed despite missing file", ""

    plan = create_plan(
        "soft",
        [
            PlanStep(
                id="write",
                mode=MODE_EXECUTOR,
                acceptance=[AcceptanceCheck(type="files_exist", paths=["nope.txt"])],
                task="x",
            ),
            PlanStep(
                id="review",
                mode=MODE_CHAT,
                depends_on=["write"],
                task="y",
            ),
        ],
        cwd=str(proj),
    )
    runner = PlanRunner(cfg, chat_fn=chat_fn, executor_fn=exec_fn, emit_event=False)
    result = runner.run(plan, mode="shadow")
    assert result.success  # soft-opened
    assert ran["chat"] == 1
    assert result.plan.get_step("write").status == VERIFIED
    # verify_log should still show failure evidence
    assert result.plan.get_step("write").verify_log
    assert result.plan.get_step("write").verify_log[0]["ok"] is False


def test_plan_config_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yml = tmp_path / "voly.yaml"
    yml.write_text(
        """
plan:
  enabled: true
  mode: active
  store_dir: .voly/plans-x
  max_step_retries: 2
  default_on_verify_fail: retry
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    cfg = load_config(str(yml))
    assert cfg.plan.enabled is True
    assert cfg.plan.mode == "active"
    assert cfg.plan.store_dir == ".voly/plans-x"
    assert cfg.plan.max_step_retries == 2
    assert cfg.plan.default_on_verify_fail == "retry"


def test_cli_validate_and_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(
        yaml.dump({
            "plan_id": "cli-demo",
            "cwd": str(proj),
            "steps": [
                {
                    "id": "only",
                    "mode": "chat",
                    "task": "say hi",
                    "acceptance": [{"type": "output_nonempty"}],
                },
            ],
        }),
        encoding="utf-8",
    )
    # Minimal config with plan store under tmp
    conf = tmp_path / "voly.yaml"
    conf.write_text(
        f"plan:\n  mode: active\n  store_dir: {tmp_path / 'plans'}\n",
        encoding="utf-8",
    )

    # Monkeypatch PlanRunner chat via env is hard; instead call validate only
    # and run with inject through unit API. CLI validate is enough for click wiring.
    runner = CliRunner()
    r = runner.invoke(main, ["--config", str(conf), "plan", "validate", str(plan_path)])
    assert r.exit_code == 0, r.output
    assert "ok: cli-demo" in r.output

    # list empty store
    r2 = runner.invoke(main, ["--config", str(conf), "plan", "list"])
    assert r2.exit_code == 0
    assert "No plans" in r2.output


def test_cli_show_after_runner(cfg: VOLYConfig, tmp_path: Path) -> None:
    plan = create_plan(
        "showme",
        [PlanStep(id="s", mode=MODE_CHAT, task="t")],
        cwd=str(tmp_path),
    )

    def chat_fn(step, plan, instruction):
        return True, "ok", ""

    PlanRunner(cfg, chat_fn=chat_fn, emit_event=False).run(plan, mode="active")

    conf = tmp_path / "voly.yaml"
    conf.write_text(
        f"plan:\n  store_dir: {cfg.plan.store_dir}\n",
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        main, ["--config", str(conf), "plan", "status", "showme"]
    )
    assert r.exit_code == 0, r.output
    assert "showme" in r.output
    assert "completed" in r.output
