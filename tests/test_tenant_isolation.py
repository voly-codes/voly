"""Multi-tenant isolation — gate for Этап 4 (Team tier).

A tenant is identified by its token (spend-protocol v1). These tests prove the
core's isolation primitives so a multi-tenant server built on them cannot leak
one tenant's spend, events, or cached responses to another:

  - **cache**  → the AIGateway cache key folds in ``cache_scope``; a different
                 tenant scope never returns another tenant's cached response.
  - **spend**  → SpendClient tags every request with its own bearer token; two
                 clients never cross tokens.
  - **events** → TaskEvents write to a per-tenant ``events_dir``; loading one
                 tenant's dir never surfaces another tenant's events.
"""

from __future__ import annotations

import urllib.request

from voly.ai_gateway import AIGateway
from voly.spend.client import SpendClient
from voly.telemetry import TaskEvent, emit_event, load_events


# ─── Cache: no cross-tenant leak ─────────────────────────────────────────────
def test_cache_no_cross_tenant_leak(monkeypatch) -> None:
    """Same prompt under two tenant scopes must NOT share a cached response."""
    gw = AIGateway()  # no account_id → _direct_call path
    gw.fallback.enabled = False
    calls: list[str] = []

    def fake_direct(messages, model, provider_name, *a, **k):
        calls.append(model)
        # Distinct payload per call so a leak (serving tenant A's cache to B) is
        # detectable by content, not just by cache-hit flag.
        return {"content": f"secret-{len(calls)}", "stop_reason": "end_turn",
                "usage": {"total_tokens": 3}}

    monkeypatch.setattr(gw, "_direct_call", fake_direct)
    msgs = [{"role": "user", "content": "same prompt"}]

    # Tenant A
    a1 = gw.chat(msgs, model="m", provider_name="mimo", cache_scope="tenant:A")
    a2 = gw.chat(msgs, model="m", provider_name="mimo", cache_scope="tenant:A")
    assert a1["content"] == "secret-1"
    assert a2.get("cache_hit") is True and a2["content"] == "secret-1"  # A reuses A

    # Tenant B — identical prompt, different tenant scope → MUST miss A's cache
    b1 = gw.chat(msgs, model="m", provider_name="mimo", cache_scope="tenant:B")
    assert b1.get("cache_hit") is not True          # not served from A
    assert b1["content"] == "secret-2"              # fresh call, not A's "secret-1"
    assert len(calls) == 2                           # A once, B once


def test_cache_key_includes_tenant_scope() -> None:
    gw = AIGateway()
    msgs = [{"role": "user", "content": "x"}]
    ka = gw._cache_key(msgs, "m", "mimo", "", "{}", "tenant:A")
    kb = gw._cache_key(msgs, "m", "mimo", "", "{}", "tenant:B")
    assert ka != kb


# ─── Spend: tokens never cross ───────────────────────────────────────────────
def test_spend_token_isolation(monkeypatch) -> None:
    """Each SpendClient tags requests with its OWN bearer token, never another's."""
    seen: list[tuple[str, str | None]] = []

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    def fake_urlopen(req, *a, **k):
        seen.append((req.full_url, req.get_header("Authorization")))
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    tenant_a = SpendClient("https://spend.example", token="TOK_A")
    tenant_b = SpendClient("https://spend.example", token="TOK_B")

    tenant_a.record("developer", 0.25, task_id="a-task")
    tenant_b.record("developer", 0.99, task_id="b-task")

    auths = [auth for _, auth in seen]
    assert auths == ["Bearer TOK_A", "Bearer TOK_B"]  # exact, no crossing


def test_spend_client_no_token_sends_no_auth(monkeypatch) -> None:
    captured: list[str | None] = []

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, *a, **k: captured.append(req.get_header("Authorization")) or _FakeResp())
    SpendClient("https://spend.example", token="").record("dev", 0.1)
    assert captured == [None]


# ─── Events: per-tenant dir, no cross-read ───────────────────────────────────
def test_events_isolation_by_dir(tmp_path) -> None:
    dir_a = tmp_path / "tenantA" / "events"
    dir_b = tmp_path / "tenantB" / "events"

    emit_event(TaskEvent(task_id="A-1", agent="dev", status="completed"), events_dir=dir_a)
    emit_event(TaskEvent(task_id="A-2", agent="dev", status="completed"), events_dir=dir_a)
    emit_event(TaskEvent(task_id="B-1", agent="dev", status="completed"), events_dir=dir_b)

    a_ids = {e.task_id for e in load_events(dir_a)}
    b_ids = {e.task_id for e in load_events(dir_b)}

    assert a_ids == {"A-1", "A-2"}
    assert b_ids == {"B-1"}
    assert a_ids.isdisjoint(b_ids)  # no leakage either direction


# ─── run_local stops the chain when the spend limit is hit ───────────────────
def test_run_local_stops_on_spend_limit() -> None:
    """A spend limit mid-chain stops the run — remaining roles are not executed."""
    from voly.a2a.multiagent import Assignment, run_local

    calls: list[str] = []

    class SpendCappedGateway:
        def chat(self, messages, *, model, provider_name, agent, **k):
            calls.append(agent)
            # First sub-agent succeeds, then the budget is exhausted.
            if len(calls) == 1:
                return {"content": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}
            return {"error": "Spend limit exceeded", "content": "", "spend_limited": True}

    roles = ["architect", "developer", "tester", "reviewer"]
    assignments = [
        # Linear dependency chain — with wave scheduling, independent roles
        # share a wave and are called together; the spend stop halts waves.
        Assignment(idx=i, role=r, description=r, depends_on=[i - 1] if i else [],
                   tier="cheap", model="m", provider="p", skills=[])
        for i, r in enumerate(roles)
    ]

    run_local("build", assignments, SpendCappedGateway())

    # architect ran, developer hit the limit → chain stops. tester/reviewer skipped.
    assert calls == ["architect", "developer"]
    assert assignments[0].ok is True
    assert assignments[1].ok is False
    assert assignments[2].content == "" and assignments[2].ok is False
    assert assignments[3].content == "" and assignments[3].ok is False
