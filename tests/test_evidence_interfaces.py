from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from voly.cli.main import main
from voly.config import EvidenceConfig, VOLYConfig
from voly.evidence import (
    EvidenceOutcome,
    EvidenceRecord,
    EvidenceStore,
    ExecutionBundle,
    RepositoryBaseline,
)


def _record(task_id: str = "run-1") -> EvidenceRecord:
    return EvidenceRecord(
        task_id=task_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        task_type="backend",
        task_fingerprint="fingerprint",
        baseline=RepositoryBaseline(
            captured_at=datetime.now(timezone.utc).isoformat(),
            health="healthy",
        ),
        execution=ExecutionBundle(agent="developer", executor="zen"),
        outcome=EvidenceOutcome(success=True, state="execution_success"),
    )


def test_store_rejects_path_like_task_id(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence")

    with pytest.raises(ValueError, match="invalid task_id"):
        store.path("../outside")
    with pytest.raises(ValueError, match="invalid task_id"):
        store.path(r"..\outside")


def test_store_rejects_oversized_feedback_comment(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence")
    store.save(_record())

    with pytest.raises(ValueError, match="exceeds 2000"):
        store.add_human_feedback("run-1", "accepted", comment="x" * 2001)


def test_store_preserves_concurrent_feedback_in_one_process(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "evidence")
    store.save(_record())

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                store.add_human_feedback,
                "run-1",
                "edited",
                comment=f"edit-{index}",
            )
            for index in range(2)
        ]
        for future in futures:
            future.result()

    loaded = store.load("run-1")
    assert loaded is not None
    assert {item.comment for item in loaded.human_feedback} == {"edit-0", "edit-1"}


def test_evidence_cli_show_and_feedback(tmp_path: Path) -> None:
    store_dir = tmp_path / "evidence"
    EvidenceStore(store_dir).save(_record())
    config_path = tmp_path / "voly.yaml"
    config_path.write_text(
        f"evidence:\n  store_dir: '{store_dir.as_posix()}'\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    feedback = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "evidence",
            "feedback",
            "run-1",
            "accepted",
            "--comment",
            "merged unchanged",
        ],
    )
    assert feedback.exit_code == 0, feedback.output
    payload = json.loads(feedback.output)
    assert payload["feedback"]["kind"] == "accepted"
    assert payload["feedback"]["source"] == "cli"

    shown = runner.invoke(
        main,
        ["--config", str(config_path), "evidence", "show", "run-1"],
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["human_feedback"][0]["comment"] == "merged unchanged"


def test_evidence_cli_reports_missing_record(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "evidence",
            "show",
            "missing",
            "--store-dir",
            str(tmp_path / "evidence"),
        ],
    )

    assert result.exit_code == 1
    assert "evidence record not found" in result.output


fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from voly.web.server import create_app  # noqa: E402


def test_evidence_api_get_and_feedback(tmp_path: Path) -> None:
    store_dir = tmp_path / "evidence"
    EvidenceStore(store_dir).save(_record())
    app = create_app(
        events_dir=tmp_path / "events",
        config=VOLYConfig(evidence=EvidenceConfig(store_dir=str(store_dir))),
    )
    client = TestClient(app)

    fetched = client.get("/api/evidence/run-1")
    assert fetched.status_code == 200
    assert fetched.json()["task_id"] == "run-1"

    feedback = client.post(
        "/api/evidence/run-1/feedback",
        json={"kind": "edited", "comment": "renamed helper"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["feedback"]["source"] == "api"
    stored = EvidenceStore(store_dir).load("run-1")
    assert stored is not None
    assert stored.human_feedback[-1].comment == "renamed helper"


def test_evidence_api_validation_and_missing(tmp_path: Path) -> None:
    store_dir = tmp_path / "evidence"
    app = create_app(
        events_dir=tmp_path / "events",
        config=VOLYConfig(evidence=EvidenceConfig(store_dir=str(store_dir))),
    )
    client = TestClient(app)

    assert client.get("/api/evidence/bad$id").status_code == 400
    assert client.get("/api/evidence/missing").status_code == 404
    invalid_kind = client.post(
        "/api/evidence/missing/feedback",
        json={"kind": "liked"},
    )
    assert invalid_kind.status_code == 422
    long_comment = client.post(
        "/api/evidence/missing/feedback",
        json={"kind": "accepted", "comment": "x" * 2001},
    )
    assert long_comment.status_code == 422
