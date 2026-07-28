from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from voly.cli.commands.eval_cmd import eval_cmd
from voly.evaluation.golden import (
    GOLDEN_REPORT_SCHEMA_VERSION,
    GoldenDatasetError,
    load_golden_dataset,
    run_golden_dataset,
    save_golden_report,
)


def _write_dataset(
    root: Path,
    *,
    cases: list[dict] | None = None,
    extra: dict | None = None,
) -> Path:
    fixture = root / "fixtures" / "basic"
    fixture.mkdir(parents=True)
    (fixture / "run.py").write_text(
        "from pathlib import Path\n"
        "print('golden-ok')\n"
        "Path('result.txt').write_text('stable result', encoding='utf-8')\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": 1,
        "dataset_id": "core-regressions",
        "version": "2026.07.1",
        "description": "Core deterministic checks.",
        "cases": cases
        or [
            {
                "id": "basic-success",
                "category": "typical",
                "fixture": "fixtures/basic",
                "argv": ["{python}", "run.py"],
                "timeout_seconds": 10,
                "expected": {
                    "exit_code": 0,
                    "stdout_contains": ["golden-ok"],
                    "stdout_not_contains": ["traceback"],
                    "files": [
                        {
                            "path": "result.txt",
                            "exists": True,
                            "contains": ["stable result"],
                        }
                    ],
                },
            }
        ],
    }
    payload.update(extra or {})
    path = root / "dataset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_and_run_golden_dataset_in_isolated_fixture(tmp_path: Path) -> None:
    dataset = load_golden_dataset(_write_dataset(tmp_path))

    report = run_golden_dataset(dataset)

    assert report["schema_version"] == GOLDEN_REPORT_SCHEMA_VERSION
    assert report["dataset"]["id"] == "core-regressions"
    assert len(report["dataset"]["fingerprint_sha256"]) == 64
    assert report["runner"]["shell"] is False
    assert report["runner"]["network_policy"] == "not_enforced"
    assert report["runner"]["environment_policy"] == "credentials_removed"
    assert report["summary"] == {"total": 1, "passed": 1, "failed": 0}
    assert report["cases"][0]["passed"] is True
    assert report["cases"][0]["declared_argv"][0] == "{python}"
    assert not (tmp_path / "fixtures" / "basic" / "result.txt").exists()


def test_golden_replay_reports_failed_expectations(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cases"][0]["expected"]["stdout_contains"] = ["not-produced"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = run_golden_dataset(load_golden_dataset(path))

    assert report["summary"]["failed"] == 1
    result = report["cases"][0]
    assert result["passed"] is False
    assert any(check["id"] == "stdout:contains:0" for check in result["checks"])


def test_golden_fingerprint_includes_fixture_content(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path)
    before = load_golden_dataset(path).fingerprint

    (tmp_path / "fixtures" / "basic" / "run.py").write_text(
        "print('changed')\n",
        encoding="utf-8",
    )

    assert load_golden_dataset(path).fingerprint != before


def test_golden_replay_filters_by_stable_case_id(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    second = dict(payload["cases"][0])
    second["id"] = "edge-success"
    second["category"] = "edge"
    payload["cases"].append(second)
    path.write_text(json.dumps(payload), encoding="utf-8")
    dataset = load_golden_dataset(path)

    report = run_golden_dataset(dataset, case_ids={"edge-success"})

    assert report["summary"]["total"] == 1
    assert report["cases"][0]["case_id"] == "edge-success"
    with pytest.raises(GoldenDatasetError, match="unknown case ids"):
        run_golden_dataset(dataset, case_ids={"missing"})


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(schema_version=2), "schema_version"),
        (lambda payload: payload.update(version="../escape"), "dataset.version"),
        (lambda payload: payload.update(unexpected=True), "unknown keys"),
        (
            lambda payload: payload["cases"].append(dict(payload["cases"][0])),
            "duplicate ids",
        ),
        (
            lambda payload: payload["cases"][0].update(category="random"),
            "category",
        ),
        (
            lambda payload: payload["cases"][0].update(argv="python run.py"),
            "argv",
        ),
        (
            lambda payload: payload["cases"][0].update(fixture="../outside"),
            "stay inside",
        ),
    ],
)
def test_golden_dataset_rejects_invalid_contract(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    path = _write_dataset(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GoldenDatasetError, match=message):
        load_golden_dataset(path)


def test_golden_dataset_rejects_fixture_symlinks(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    link = tmp_path / "fixtures" / "basic" / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable for this user")

    with pytest.raises(GoldenDatasetError, match="contains symlink"):
        load_golden_dataset(path)


def test_golden_replay_times_out_without_shell(tmp_path: Path) -> None:
    cases = [
        {
            "id": "timeout",
            "category": "adversarial",
            "fixture": "fixtures/basic",
            "argv": ["{python}", "-c", "import time; time.sleep(5)"],
            "timeout_seconds": 1,
            "expected": {"exit_code": 0},
        }
    ]
    dataset = load_golden_dataset(_write_dataset(tmp_path, cases=cases))

    report = run_golden_dataset(dataset)

    result = report["cases"][0]
    assert result["passed"] is False
    assert result["timed_out"] is True
    assert result["checks"][0]["id"] == "process:timeout"


def test_save_golden_report_is_utf8_json(tmp_path: Path) -> None:
    report = run_golden_dataset(load_golden_dataset(_write_dataset(tmp_path)))
    target = save_golden_report(report, tmp_path / "reports" / "run.json")

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["dataset"]["id"] == "core-regressions"
    assert not list(target.parent.glob("*.tmp"))


def test_eval_cli_validate_and_run_exit_codes(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path)
    runner = CliRunner()

    validated = runner.invoke(eval_cmd, ["validate", str(path)])
    output = tmp_path / "report.json"
    replayed = runner.invoke(eval_cmd, ["run", str(path), "--output", str(output)])

    assert validated.exit_code == 0
    assert json.loads(validated.output)["valid"] is True
    assert replayed.exit_code == 0
    assert json.loads(replayed.output)["passed"] == 1
    assert output.exists()

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cases"][0]["expected"]["exit_code"] = 9
    path.write_text(json.dumps(payload), encoding="utf-8")
    failed = runner.invoke(eval_cmd, ["run", str(path), "--output", str(output)])
    assert failed.exit_code == 1
    assert json.loads(failed.output)["failed"] == 1
