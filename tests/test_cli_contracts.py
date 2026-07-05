"""Этап 6 — контрактные тесты CLI-обёрток (риск R4: дрейф форматов вывода).

Фикстуры сняты с РЕАЛЬНЫХ CLI (2026-07-05):
  - claude CLI 2.1.170: `claude --print --output-format json`
  - opencode CLI 1.17.13: `opencode run --format json` (NDJSON-события)

Контракт: парсеры executor-ов распознают эти форматы (текст, токены, стоимость,
billing-ошибки). Если апстрим меняет формат — падает этот файл, а не молча
перестаёт срабатывать billing fallback. Вторая линия защиты — метрика
error_class="unrecognized" в телеметрии (voly telemetry errors).
"""

from __future__ import annotations

import json
import types

import voly.executor.claude_code as claude_mod
from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult, _extract_cli_error, _oc_event_error, classify_failure
from voly.executor.claude_code import ClaudeCodeExecutor
from voly.executor.cursor import CursorExecutor, _status_name
from voly.executor.zen import ZenExecutor
from voly.telemetry import TaskEvent, summarize_error_classes
import voly.runner.agent_runner as runner_mod


# ─── claude CLI (2.1.170): --print --output-format json ───────────────────────

# Реальный success-ответ (усечён: убраны iterations/server_tool_use, сокращён uuid).
_CLAUDE_SUCCESS = json.dumps({
    "type": "result", "subtype": "success", "is_error": False,
    "api_error_status": None,
    "duration_ms": 3764, "duration_api_ms": 4600, "num_turns": 1,
    "result": "OK", "stop_reason": "end_turn",
    "session_id": "dc567d7a-31fc-4430-abe3-746478092ff8",
    "total_cost_usd": 0.176238,
    "usage": {
        "input_tokens": 4579, "cache_creation_input_tokens": 9764,
        "cache_read_input_tokens": 7697, "output_tokens": 4,
        "service_tier": "standard",
    },
    # Контракт 2.1.x: ключи modelUsage — camelCase.
    "modelUsage": {
        "claude-haiku-4-5-20251001": {
            "inputTokens": 441, "outputTokens": 12, "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0, "costUSD": 0.000501,
        },
        "claude-fable-5[1m]": {
            "inputTokens": 4579, "outputTokens": 4, "cacheReadInputTokens": 7697,
            "cacheCreationInputTokens": 9764, "costUSD": 0.175737,
        },
    },
    "permission_denials": [], "terminal_reason": "completed",
})


def _claude() -> ClaudeCodeExecutor:
    return ClaudeCodeExecutor(claude_bin="claude")


def test_claude_success_contract():
    r = _claude()._parse_output(_CLAUDE_SUCCESS, "", 100.0)
    assert r.success is True
    assert r.output == "OK"
    assert r.cost_usd == 0.176238
    assert r.input_tokens == 4579 and r.output_tokens == 4
    assert r.num_turns == 1
    assert r.session_id == "dc567d7a-31fc-4430-abe3-746478092ff8"
    assert r.duration_ms == 3764
    assert r.metadata["stop_reason"] == "end_turn"
    assert r.metadata["terminal_reason"] == "completed"
    assert r.billing_error is False


def test_claude_model_usage_camelcase_fallback():
    """usage пуст → токены агрегируются из camelCase modelUsage (контракт 2.1.x)."""
    data = json.loads(_CLAUDE_SUCCESS)
    data["usage"] = {}
    r = _claude()._parse_output(json.dumps(data), "", 100.0)
    assert r.input_tokens == 441 + 4579
    assert r.output_tokens == 12 + 4


def test_claude_model_usage_snake_case_still_supported():
    """Старый snake_case modelUsage продолжает работать."""
    data = json.loads(_CLAUDE_SUCCESS)
    data["usage"] = {}
    data["modelUsage"] = {"claude-sonnet-4-6": {"input_tokens": 100, "output_tokens": 7}}
    r = _claude()._parse_output(json.dumps(data), "", 100.0)
    assert r.input_tokens == 100 and r.output_tokens == 7


def test_claude_billing_error_in_result_text():
    """is_error=true + billing-текст в result → billing_error=True."""
    data = json.loads(_CLAUDE_SUCCESS)
    data["is_error"] = True
    data["result"] = "Your credit balance is too low to access the Anthropic API."
    r = _claude()._parse_output(json.dumps(data), "", 100.0)
    assert r.success is False
    assert r.billing_error is True


def test_claude_api_error_status_wins_over_result():
    data = json.loads(_CLAUDE_SUCCESS)
    data["is_error"] = True
    data["api_error_status"] = "insufficient_quota"
    data["result"] = "request failed"
    r = _claude()._parse_output(json.dumps(data), "", 100.0)
    assert r.success is False
    assert r.error == "insufficient_quota"
    assert r.billing_error is True


def test_claude_rate_limit_is_not_billing():
    """Transient 429 НЕ должен уводить задачу по billing-цепочке."""
    data = json.loads(_CLAUDE_SUCCESS)
    data["is_error"] = True
    data["result"] = "429 Too Many Requests: rate limit exceeded, retry after 12s"
    r = _claude()._parse_output(json.dumps(data), "", 100.0)
    assert r.success is False
    assert r.billing_error is False


def test_claude_non_json_stdout_passthrough():
    """Стриминг/plain-вывод без JSON — не ошибка парсинга, а сырой output."""
    r = _claude()._parse_output("plain text answer\nwith lines", "", 50.0)
    assert r.success is True
    assert r.output.startswith("plain text answer")


def _fake_proc(returncode: int, stdout: str = "", stderr: str = ""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_claude_exit_nonzero_with_json_stdout_parsed(monkeypatch):
    """exit≠0, но stdout несёт JSON с is_error — парсим его, а не generic-ошибку."""
    data = json.loads(_CLAUDE_SUCCESS)
    data["is_error"] = True
    data["result"] = "Credit balance is too low"
    monkeypatch.setattr(
        claude_mod.subprocess, "run",
        lambda *a, **k: _fake_proc(1, stdout=json.dumps(data)),
    )
    r = _claude().run("do it", cwd="/tmp")
    assert r.success is False
    assert r.billing_error is True


def test_claude_exit_nonzero_plain_stderr(monkeypatch):
    monkeypatch.setattr(
        claude_mod.subprocess, "run",
        lambda *a, **k: _fake_proc(1, stderr="You have exceeded your current quota."),
    )
    r = _claude().run("do it", cwd="/tmp")
    assert r.success is False
    assert r.billing_error is True
    assert classify_failure(r) == "billing"


def test_claude_exit_nonzero_unrecognized_stderr(monkeypatch):
    """Неизвестная ошибка: billing fallback НЕ дёргается, метрика видит drift."""
    monkeypatch.setattr(
        claude_mod.subprocess, "run",
        lambda *a, **k: _fake_proc(1, stderr="segfault in wasm runtime (0xdead)"),
    )
    r = _claude().run("do it", cwd="/tmp")
    assert r.success is False
    assert r.billing_error is False
    assert classify_failure(r) == "unrecognized"


# ─── opencode CLI (1.17.13): NDJSON события run --format json ──────────────────

# Реальный success-стрим (усечены только id/timestamp).
_OC_SUCCESS_STREAM = "\n".join([
    json.dumps({"type": "step_start", "timestamp": 1783203454462,
                "sessionID": "ses_0d0cab0cdffe",
                "part": {"id": "prt_1", "messageID": "msg_1",
                         "sessionID": "ses_0d0cab0cdffe", "type": "step-start"}}),
    json.dumps({"type": "text", "timestamp": 1783203455452,
                "sessionID": "ses_0d0cab0cdffe",
                "part": {"id": "prt_2", "messageID": "msg_1",
                         "sessionID": "ses_0d0cab0cdffe", "type": "text", "text": "OK",
                         "time": {"start": 1783203455365, "end": 1783203455419}}}),
    json.dumps({"type": "step_finish", "timestamp": 1783203455452,
                "sessionID": "ses_0d0cab0cdffe",
                "part": {"id": "prt_3", "reason": "stop", "messageID": "msg_1",
                         "sessionID": "ses_0d0cab0cdffe", "type": "step-finish",
                         "tokens": {"total": 9522, "input": 9508, "output": 2,
                                    "reasoning": 12, "cache": {"write": 0, "read": 0}},
                         "cost": 0}}),
])

# Реальное error-событие (exit=1, stdout).
_OC_ERROR_LINE = json.dumps({
    "type": "error", "timestamp": 1783203468933,
    "sessionID": "ses_0d0ca6ccaffe",
    "error": {"name": "UnknownError",
              "data": {"message": "Unexpected server error. Check server logs for details.",
                       "ref": "err_51f32eca"}},
})


def test_zen_parse_success_stream_contract():
    r = ZenExecutor()._parse_json_events(_OC_SUCCESS_STREAM, "", 900.0,
                                         model_id="opencode/deepseek-v4-flash-free")
    assert r.success is True
    assert r.output == "OK"
    assert r.input_tokens == 9508 and r.output_tokens == 2
    assert r.num_turns == 1
    assert r.session_id == "ses_0d0cab0cdffe"
    # free-модель: стоимость 0 и не подменяется оценкой
    assert r.cost_usd == 0.0


def test_oc_error_event_nested_contract():
    err = _oc_event_error(json.loads(_OC_ERROR_LINE))
    assert err == "Unexpected server error. Check server logs for details. (err_51f32eca)"


def test_oc_error_event_flat_and_name_shapes():
    assert _oc_event_error({"type": "error", "message": "boom"}) == "boom"
    assert _oc_event_error(
        {"name": "ProviderAuthError", "data": {"message": "invalid api key", "ref": "err_1"}}
    ) == "invalid api key (err_1)"
    assert _oc_event_error({"type": "text", "part": {"text": "hi"}}) is None


def test_zen_parse_error_stream_billing():
    line = json.dumps({"type": "error",
                       "error": {"name": "APIError",
                                 "data": {"message": "You have run out of credits.",
                                          "ref": "err_x"}}})
    r = ZenExecutor()._parse_json_events(line, "", 100.0, model_id="opencode/gpt-5.4")
    assert r.success is False
    assert "out of credits" in r.error
    assert r.billing_error is True


def test_extract_cli_error_prefers_json_event():
    err = _extract_cli_error(_OC_ERROR_LINE, "", 1)
    assert "Unexpected server error" in err
    assert "err_51f32eca" in err
    assert "exited with code" not in err


def test_extract_cli_error_strips_ansi_plain_text():
    stderr = "\x1b[31mError:\x1b[0m model not found\n\x1b[2K"
    err = _extract_cli_error("", stderr, 1)
    assert "Error: model not found" in err
    assert "\x1b" not in err


def test_extract_cli_error_falls_back_to_exit_code():
    assert _extract_cli_error("", "", 137) == "opencode exited with code 137"


# ─── cursor (cursor-sdk) ───────────────────────────────────────────────────────

def test_cursor_status_name_contract():
    class _Enum:
        name = "FINISHED"
    assert _status_name(_Enum()) == "finished"
    assert _status_name("AgentStatus.failed") == "failed"
    assert _status_name(None) == ""


def test_cursor_missing_api_key_is_clear_error(monkeypatch):
    # Герметизация: другие тесты могут подгрузить .env с реальным ключом —
    # без delenv этот тест запустит НАСТОЯЩИЙ Cursor-агент.
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    r = CursorExecutor(api_key="").run("do it", cwd="/tmp")
    assert r.success is False
    assert "CURSOR_API_KEY" in r.error
    assert classify_failure(r) == "unrecognized"  # конфиг-ошибка, не billing


# ─── classify_failure / метрика нераспознанных ошибок ──────────────────────────

def test_classify_failure_marker_priority():
    ok = ExecutorResult(success=True)
    assert classify_failure(ok) is None
    assert classify_failure(ExecutorResult(success=False, billing_error=True)) == "billing"
    assert classify_failure(ExecutorResult(success=False, not_available=True)) == "not_available"
    assert classify_failure(
        ExecutorResult(success=False, metadata={"timeout": True})
    ) == "timeout"
    assert classify_failure(
        ExecutorResult(success=False, metadata={"deadline_exhausted": True})
    ) == "timeout"


def test_classify_failure_semantic_and_unrecognized():
    assert classify_failure(
        ExecutorResult(success=False, error="Daily limit exceeded, try again tomorrow")
    ) == "quota_exhausted"
    assert classify_failure(
        ExecutorResult(success=False, error="prompt too large: context window exceeded")
    ) == "context_overflow"
    assert classify_failure(
        ExecutorResult(success=False, error="wasm trap: unreachable executed")
    ) == "unrecognized"


class _FakeExec:
    def __init__(self, result: ExecutorResult):
        self._result = result

    def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kw):
        return self._result

    def is_available(self) -> bool:
        return True


def test_agent_runner_emits_error_class(monkeypatch, tmp_path):
    """Неопознанный отказ финального executor-а → error_class в TaskEvent и timelog."""
    failing = ExecutorResult(success=False, error="wasm trap: unreachable", duration_ms=5)
    monkeypatch.setattr(runner_mod, "_build_executor",
                        lambda name, model=None: _FakeExec(failing))
    events: list = []
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda ev, cfg: events.append(ev))

    out = runner_mod.AgentRunner(VOLYConfig()).run("fix", "zen", cwd=str(tmp_path))
    assert out.success is False
    assert events[0].error_class == "unrecognized"


def test_agent_runner_error_class_none_on_success(monkeypatch, tmp_path):
    ok = ExecutorResult(success=True, output="done", duration_ms=5)
    monkeypatch.setattr(runner_mod, "_build_executor", lambda name, model=None: _FakeExec(ok))
    events: list = []
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda ev, cfg: events.append(ev))

    runner_mod.AgentRunner(VOLYConfig()).run("fix", "zen", cwd=str(tmp_path))
    assert events[0].error_class is None


def test_summarize_error_classes_share():
    events = [
        TaskEvent(task_id="1", agent="a", status="completed"),
        TaskEvent(task_id="2", agent="a", status="failed", error_class="billing"),
        TaskEvent(task_id="3", agent="a", status="failed", error_class="unrecognized"),
        TaskEvent(task_id="4", agent="a", status="failed", error_class="unrecognized"),
        TaskEvent(task_id="5", agent="a", status="failed", error_class="timeout"),
        # событие до появления поля — не искажает долю
        TaskEvent(task_id="6", agent="a", status="failed"),
    ]
    s = summarize_error_classes(events)
    assert s["failed"] == 5
    assert s["by_class"] == {"billing": 1, "unrecognized": 2, "timeout": 1, "(unclassified)": 1}
    assert s["unrecognized_share"] == 0.5
