"""Tests for persistent workflow client and backend."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from voly.workflow.backend import (
    instance_from_remote_payload,
    instance_to_remote_payload,
)
from voly.workflow.client import (
    WorkflowClient,
    WorkflowClientError,
    create_workflow_client,
    resolve_workflow_url,
)


REMOTE_START_PAYLOAD = {
    "id": "wf-123",
    "workflow": "bugfix",
    "state": "created",
    "task": "Fix login bug",
    "inputs": {},
    "definition": {
        "name": "bugfix",
        "description": "Bugfix flow",
        "steps": [
            {
                "name": "analyze",
                "agent": "developer",
                "task_template": "Analyze: {task}",
                "depends_on": [],
                "approval": "auto",
                "max_retries": 3,
            },
            {
                "name": "fix",
                "agent": "bugfixer",
                "task_template": "Fix: {task}",
                "depends_on": ["analyze"],
                "approval": "auto",
                "max_retries": 3,
            },
        ],
    },
    "steps": {
        "analyze": {"state": "pending", "result": "", "error": "", "retries": 0},
        "fix": {"state": "pending", "result": "", "error": "", "retries": 0},
    },
    "approvals_pending": [],
    "created_at": 1_700_000_000_000,
}


def test_resolve_workflow_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_WORKFLOW_URL", raising=False)
    assert resolve_workflow_url("") == ""

    monkeypatch.setenv("CF_WORKER_WORKFLOW_URL", "https://wf.example.com")
    assert resolve_workflow_url("") == "https://wf.example.com"
    assert resolve_workflow_url("${CF_WORKER_WORKFLOW_URL}") == "https://wf.example.com"


def test_create_workflow_client_none_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_WORKER_WORKFLOW_URL", raising=False)
    assert create_workflow_client() is None


def test_instance_roundtrip_remote_payload() -> None:
    instance = instance_from_remote_payload(REMOTE_START_PAYLOAD)
    assert instance.id == "wf-123"
    assert instance.definition.name == "bugfix"
    assert "analyze" in instance.steps
    assert "fix" in instance.steps

    payload = instance_to_remote_payload(instance, task="Fix login bug")
    assert payload["id"] == "wf-123"
    assert payload["task"] == "Fix login bug"
    assert isinstance(payload["definition"]["steps"], list)
    assert payload["definition"]["steps"][0]["name"] == "analyze"


def test_workflow_client_start_posts_json() -> None:
    client = WorkflowClient("https://wf.example.com", token="secret")
    captured: dict = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["method"] = req.method
        resp = MagicMock()
        resp.read.return_value = json.dumps({"instance_id": "new-id", "state": "created"}).encode()
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        instance_id = client.start("bugfix", "Fix auth", {"priority": "high"})

    assert instance_id == "new-id"
    assert captured["url"] == "https://wf.example.com/workflow/start"
    assert captured["method"] == "POST"
    body = json.loads(captured["data"].decode())
    assert body["workflow_name"] == "bugfix"
    assert body["task"] == "Fix auth"
    assert body["inputs"]["priority"] == "high"


def test_workflow_client_http_error() -> None:
    client = WorkflowClient("https://wf.example.com")

    def fake_urlopen(req, timeout=30):
        raise HTTPError(
            req.full_url, 404, "Not Found", hdrs=None, fp=MagicMock(read=lambda: b'{"error":"missing"}')
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        with pytest.raises(WorkflowClientError, match="HTTP 404"):
            client.get_status("missing-id")
