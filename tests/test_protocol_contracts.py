"""Этап 3 — контракты публичных протоколов ядра.

Ядро общается с внешними потребителями (CF Pipelines, R2, hosted-дашборды,
self-hosted spend-сервисы) через версионируемые интерфейсы:

  1. TaskEvent (schema_version) — формат события телеметрии.
  2. Spend-протокол (/spend/record, /spend/check, ...) — HTTP-интерфейс
     spend-сервиса; см. docs/backend/spend-protocol.md.

Эти тесты — замороженные снимки контрактов. Если тест упал из-за изменения
набора полей или путей — это НЕ повод молча поправить снимок: сначала бамп
версии схемы + обновление docs, затем снимок.
"""

from __future__ import annotations

import json
from dataclasses import fields
from unittest.mock import patch

from voly.spend.client import SpendClient
from voly.telemetry import (
    TASK_EVENT_SCHEMA_VERSION,
    TaskEvent,
    event_to_pipeline_record,
)


# ─── TaskEvent schema v1 ───────────────────────────────────────────────────────

# Замороженный набор полей схемы v1. Добавление/удаление/переименование поля
# без бампа TASK_EVENT_SCHEMA_VERSION ломает внешних потребителей молча —
# поэтому сначала версия и docs/backend/api.md, потом этот список.
_V1_FIELDS = {
    "task_id", "agent", "status", "schema_version",
    "tokens", "gateway", "skill_ids", "memory_hits", "workflow",
    "routing_score", "cost_usd", "duration_ms",
    "model", "provider", "executor", "task_type",
    "automation_score", "manual_steps_removed",
    "retry_count", "retry_cost_usd", "error", "error_class",
    "dspy_enabled", "dspy_used", "dspy_mode", "dspy_program_id",
    "dspy_program_version", "dspy_program_tag", "dspy_optimizer",
    "dspy_dataset", "dspy_compile_id", "dspy_score", "dspy_shadow_delta",
    "task_prompt", "result", "stage_log", "report", "chain_timelog",
    "a2a_dispatched", "a2a_subtask_count", "a2a_agents_used", "a2a_assignments",
}


def test_task_event_schema_v1_frozen():
    actual = {f.name for f in fields(TaskEvent)}
    assert TASK_EVENT_SCHEMA_VERSION == 1, (
        "Версия схемы изменилась — обнови _V1_FIELDS→_V2_FIELDS и docs/backend/api.md"
    )
    missing = _V1_FIELDS - actual
    added = actual - _V1_FIELDS
    assert not missing and not added, (
        f"Схема TaskEvent разошлась с v1: added={sorted(added)}, missing={sorted(missing)}. "
        "Изменение схемы = бамп TASK_EVENT_SCHEMA_VERSION + docs/backend/api.md + этот снимок."
    )


def test_task_event_serializes_schema_version():
    ev = TaskEvent(task_id="t1", agent="a", status="completed")
    d = ev.to_dict()
    assert d["schema_version"] == 1
    # И в плоской записи для CF Pipelines
    rec = event_to_pipeline_record(ev)
    assert rec["schema_version"] == 1
    # Ключевые плоские поля pipeline-записи (контракт SQL-трансформации)
    for key in ("ts_us", "tokens_input", "tokens_output", "cache_hit", "fallback_used"):
        assert key in rec


def test_task_event_json_roundtrip_types():
    ev = TaskEvent(task_id="t1", agent="a", status="failed",
                   cost_usd=0.5, retry_count=2, error_class="billing")
    data = json.loads(ev.to_json())
    assert isinstance(data["schema_version"], int)
    assert isinstance(data["cost_usd"], float)
    assert isinstance(data["retry_count"], int)
    assert data["error_class"] == "billing"


# ─── Spend protocol v1 ─────────────────────────────────────────────────────────

class _Captured:
    def __init__(self):
        self.url = ""
        self.method = ""
        self.body: dict = {}


def _capture_request(client_call):
    """Run a SpendClient call with urlopen mocked; return captured request."""
    cap = _Captured()

    class _Resp:
        def read(self):
            return b"{}"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        cap.url = req.full_url
        cap.method = req.get_method()
        cap.body = json.loads(req.data.decode()) if req.data else {}
        return _Resp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client_call()
    return cap


def test_spend_protocol_record_contract():
    client = SpendClient("http://spend.example")
    cap = _capture_request(lambda: client.record(
        "developer", 0.25, task_id="t1", model="m", provider="p",
    ))
    assert cap.url == "http://spend.example/spend/record"
    assert cap.method == "POST"
    # Замороженный состав тела /spend/record (v1)
    assert set(cap.body) == {"agent", "cost_usd", "task_id", "model", "provider"}
    assert cap.body["agent"] == "developer"
    assert cap.body["cost_usd"] == 0.25


def test_spend_protocol_check_contract():
    client = SpendClient("http://spend.example")
    cap = _capture_request(lambda: client.check("developer", 20.0))
    assert cap.method == "GET"
    assert cap.url == "http://spend.example/spend/check?agent=developer&limit=20.0"


def test_spend_protocol_summary_and_recent_paths():
    client = SpendClient("http://spend.example")
    cap = _capture_request(lambda: client.summary(days=7))
    assert cap.url == "http://spend.example/spend/summary?days=7"
    cap = _capture_request(lambda: client.recent(limit=5))
    assert cap.url == "http://spend.example/spend/recent?limit=5"
    cap = _capture_request(lambda: client.health())
    assert cap.url == "http://spend.example/health"


def test_spend_protocol_auth_header():
    client = SpendClient("http://spend.example", token="sekret")
    headers = client._headers()
    assert headers["Authorization"] == "Bearer sekret"
    assert headers["Content-Type"] == "application/json"
