"""Local multi-agent execution: a strong lead orchestrator assigns a model tier
and skills to each decomposed sub-agent, then each sub-agent runs in-process
through ``AIGateway.chat()``.

Flow (used by the pipeline's A2A auto-dispatch when ``a2a.execution_mode == 'local'``):

    task → TaskDecomposer → [architect, developer, tester, reviewer, devops]
         → LeadOrchestrator.assign()   # strong model picks tier + skills per role
         → run_local()                 # each role → AIGateway.chat(model=tier, skills)
         → per-agent results + merged report + telemetry assignments

The model pool is the set of *real* configured providers (``router._PROVIDER_MODELS``)
filtered by ``ProviderHealthChecker`` — strong = anthropic/claude, weak = the free/cheap
providers (workers-ai, deepseek, opencode-zen, mimo, omniroute).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from voly.ai_gateway.health import get_checker
from voly.router import _PROVIDER_MODELS

_log = logging.getLogger("voly.a2a.multiagent")

# ── Model tiers → ordered real-provider preference (filtered by health) ──────────
_STRONG = ["anthropic", "cloudflare-dynamic"]
_STANDARD = ["cloudflare-dynamic", "deepseek", "anthropic", "workers-ai"]
_WEAK = ["workers-ai", "deepseek", "opencode-zen", "mimo", "omniroute"]

_TIER_PROVIDERS: dict[str, list[str]] = {
    "premium": _STRONG,
    "strong": _STRONG,
    "standard": _STANDARD,
    "cheap": _WEAK,
    "weak": _WEAK,
    "free": _WEAK,
}

# Role → default tier (fallback when the lead orchestrator is unavailable) + persona.
_ROLE_TIER: dict[str, str] = {
    "architect": "premium",
    "developer": "standard",
    "tester": "cheap",
    "reviewer": "premium",
    "devops": "cheap",
    "security": "premium",
}

_ROLE_PROMPT: dict[str, str] = {
    "architect": "Ты senior software architect. Спроектируй архитектуру: модули, "
                 "интерфейсы, поток данных, ключевые решения и риски. Кратко и по делу.",
    "developer": "Ты senior developer. Реализуй решение на основе архитектуры выше. "
                 "Выдай рабочий код с краткими пояснениями.",
    "tester": "Ты QA-инженер. Напиши тесты (pytest, если Python) для реализации выше — "
              "happy-path, граничные и негативные случаи.",
    "reviewer": "Ты code reviewer. Оцени код и тесты выше: баги, безопасность, читаемость, "
                "производительность. Дай конкретные замечания и вердикт.",
    "devops": "Ты DevOps-инженер. Подготовь деплой для реализации выше: Dockerfile/compose, "
              "CI-шаги, переменные окружения, чек-лист релиза.",
    "security": "Ты application security engineer. Найди уязвимости в коде выше и предложи фиксы.",
}
_DEFAULT_PERSONA = "Ты профильный инженер. Выполни назначенную суб-задачу качественно и кратко."

_VALID_TIERS = ("premium", "standard", "cheap")


@dataclass
class Assignment:
    """A sub-agent with its lead-assigned model tier and skills."""
    idx: int
    role: str
    description: str
    depends_on: list[int]
    tier: str
    model: str
    provider: str
    skills: list[str] = field(default_factory=list)
    # Lead may set "chat" | "executor" (hybrid policy); empty → role map.
    execution: str = ""
    # filled after execution
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    ok: bool = False
    error: str = ""
    cache_hit: bool = False       # gateway response cache hit → 0 new tokens billed
    mem_hits: int = 0             # semantic-memory entries injected into this sub-agent
    saved_tokens: int = 0        # tokens saved by Headroom compression on this sub-agent
    # Hybrid multi-agent (PR1+)
    mode: str = "chat"            # "chat" | "executor"
    mode_reason: str = ""
    executor: str = ""            # e.g. claude-code when mode=executor
    files_touched: list[str] = field(default_factory=list)

    def to_event_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "tier": self.tier,
            "model": self.model,
            "provider": self.provider,
            "skills": self.skills,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "ok": self.ok,
            "cache_hit": self.cache_hit,
            "mem_hits": self.mem_hits,
            "saved_tokens": self.saved_tokens,
            "mode": self.mode,
            "mode_reason": self.mode_reason,
            "executor": self.executor or None,
            "files_touched": list(self.files_touched),
        }


def _excluded_providers() -> set[str]:
    """Providers to skip when resolving a tier (e.g. out of credits).

    Set via VOLY_A2A_EXCLUDE_PROVIDERS="anthropic,openai" (comma-separated).
    """
    import os
    raw = os.environ.get("VOLY_A2A_EXCLUDE_PROVIDERS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


def resolve_tier_model(tier: str, checker: Any = None) -> tuple[str, str]:
    """Resolve a (model, provider) for the given tier from the healthy real pool."""
    checker = checker or get_checker()
    excluded = _excluded_providers()

    def _ok(provider: str) -> bool:
        return provider not in excluded and checker.check(provider).healthy

    for provider in _TIER_PROVIDERS.get(tier, _WEAK):
        if provider in _PROVIDER_MODELS and _ok(provider):
            return _PROVIDER_MODELS[provider]
    # No healthy provider in the requested tier → any healthy, non-excluded provider.
    for provider, pair in _PROVIDER_MODELS.items():
        if _ok(provider):
            _log.warning("tier %r: no healthy provider in tier, using %s", tier, pair[1])
            return pair
    # Last resort — anthropic (call will surface a clear auth error if unconfigured).
    return _PROVIDER_MODELS["anthropic"]


class LeadOrchestrator:
    """Strong lead agent that assigns a model tier + skills to each sub-agent."""

    def __init__(
        self,
        gateway: Any,
        skill_matcher: Callable[[str, str], list[Any]] | None = None,
        checker: Any = None,
        lead_model: str = "",
    ):
        self.gateway = gateway
        self.skill_matcher = skill_matcher
        self.checker = checker or get_checker()
        self.lead_model = lead_model

    def _candidate_skills(self, task: str, role: str) -> list[tuple[str, str]]:
        """Return [(skill_id, name)] candidates for a role, from the registry."""
        if not self.skill_matcher:
            return []
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for s in self.skill_matcher(task, role)[:6]:
            sid = getattr(s, "id", "")
            if sid and sid not in seen:
                seen.add(sid)
                out.append((sid, getattr(s, "name", sid)))
        return out

    def assign(self, task: str, subtasks: list[Any]) -> list[Assignment]:
        """Produce an Assignment per sub-task. LLM-lead first, deterministic fallback."""
        skill_candidates = {
            i: self._candidate_skills(task, st.agent) for i, st in enumerate(subtasks)
        }
        plan = self._ask_lead(task, subtasks, skill_candidates)
        assignments: list[Assignment] = []
        for i, st in enumerate(subtasks):
            entry = plan.get(i, {}) if plan else {}
            tier = entry.get("tier") or _ROLE_TIER.get(st.agent, "standard")
            if tier not in _VALID_TIERS:
                tier = _ROLE_TIER.get(st.agent, "standard")
            valid_ids = {sid for sid, _ in skill_candidates[i]}
            skills = [s for s in entry.get("skills", []) if s in valid_ids]
            if not skills:
                skills = [sid for sid, _ in skill_candidates[i][:2]]
            model, provider = resolve_tier_model(tier, self.checker)
            assignments.append(Assignment(
                idx=i, role=st.agent, description=st.description,
                depends_on=list(getattr(st, "depends_on", [])),
                tier=tier, model=model, provider=provider, skills=skills,
            ))
        return assignments

    def _ask_lead(
        self, task: str, subtasks: list[Any], skill_candidates: dict[int, list[tuple[str, str]]]
    ) -> dict[int, dict[str, Any]]:
        """Call a strong model to assign tier + skills. Returns {idx: {tier, skills}}."""
        model, provider = (
            (self.lead_model, _provider_for_model(self.lead_model))
            if self.lead_model else resolve_tier_model("premium", self.checker)
        )
        roles_block = "\n".join(
            f"{i}. role={st.agent}; task={st.description[:160]}; "
            f"skills_available={[sid for sid, _ in skill_candidates[i]] or 'none'}"
            for i, st in enumerate(subtasks)
        )
        system = (
            "Ты lead-оркестратор. Для каждой суб-задачи назначь уровень модели (tier) и "
            "релевантные скилы. Критерии: сложное проектирование/ревью/безопасность → "
            "'premium'; обычная реализация → 'standard'; рутинные тесты/деплой/батч → 'cheap'. "
            "Скилы выбирай ТОЛЬКО из skills_available каждой роли (можно пусто). "
            "Ответь СТРОГО JSON-массивом без пояснений: "
            '[{"idx":0,"tier":"premium","skills":["id1"]}, ...]'
        )
        user = f"Задача: {task}\n\nСуб-задачи:\n{roles_block}"
        try:
            resp = self.gateway.chat(
                [{"role": "user", "content": user}],
                model=model, provider_name=provider, system=system,
                agent="lead", max_tokens=1024, temperature=0.0,
            )
            content = resp.get("content", "") or ""
            if resp.get("error"):
                _log.warning("lead orchestrator error, using deterministic fallback: %s", resp["error"])
                return {}
            return _parse_plan(content)
        except Exception as e:  # noqa: BLE001 — fall back to deterministic assignment
            _log.warning("lead orchestrator call failed (%s), deterministic fallback", e)
            return {}


def _parse_plan(content: str) -> dict[int, dict[str, Any]]:
    """Extract the JSON array from the lead response into {idx: {tier, skills}}."""
    start, end = content.find("["), content.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        arr = json.loads(content[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    plan: dict[int, dict[str, Any]] = {}
    for item in arr if isinstance(arr, list) else []:
        if isinstance(item, dict) and "idx" in item:
            try:
                plan[int(item["idx"])] = {
                    "tier": item.get("tier"),
                    "skills": item.get("skills", []) if isinstance(item.get("skills"), list) else [],
                }
            except (TypeError, ValueError):
                continue
    return plan


def _provider_for_model(model: str) -> str:
    for _model, provider in _PROVIDER_MODELS.values():
        if _model == model:
            return provider
    return "anthropic"


def _skills_block(skill_ids: list[str], skill_matcher: Callable[[str, str], list[Any]] | None,
                  task: str, role: str) -> str:
    """Build a system-prompt block with the content of assigned skills."""
    if not skill_ids or not skill_matcher:
        return ""
    by_id = {getattr(s, "id", ""): s for s in skill_matcher(task, role)}
    parts: list[str] = []
    for sid in skill_ids:
        s = by_id.get(sid)
        content = getattr(s, "content", "") if s else ""
        if content and content.strip():
            parts.append(f"### {getattr(s, 'name', sid)} ({sid})\n{content.strip()[:3000]}")
    return ("# Loaded skills\n\n" + "\n\n".join(parts)) if parts else ""


def _memory_block(memory: Any, query: str, limit: int = 3) -> tuple[str, int]:
    """Retrieve semantic-memory entries relevant to a sub-task. Returns (block, hits)."""
    if memory is None:
        return "", 0
    try:
        entries = memory.search(query, limit=limit)
    except Exception as e:  # noqa: BLE001
        _log.warning("memory search failed: %s", e)
        return "", 0
    parts = [f"- [{getattr(m, 'category', '?')}] {getattr(m, 'title', '')}: "
             f"{(getattr(m, 'content', '') or '')[:600]}" for m in entries]
    if not parts:
        return "", 0
    return "# Relevant prior context (memory)\n" + "\n".join(parts), len(parts)


def run_local(
    task: str,
    assignments: list[Assignment],
    gateway: Any,
    skill_matcher: Callable[[str, str], list[Any]] | None = None,
    max_tokens: int = 4096,
    *,
    memory: Any = None,
    headroom: Any = None,
    temperature: float = 0.0,
    task_id: str = "",
    tracker: Any = None,
    # Hybrid multi-agent (docs/proposals/hybrid-multiagent-executor.md)
    cwd: str = "",
    hybrid_code_gen: bool = True,
    hybrid_require_cwd: bool = True,
    requires_code_gen: bool = True,
    executor_default: str = "claude-code",
    executor_roles: list[str] | None = None,
    executor_runner: Callable[..., Any] | None = None,
    skip_dependents_on_failure: bool = True,
) -> list[Assignment]:
    """Execute each sub-agent in dependency order.

    Default path: ``AIGateway.chat()`` (text).

    Hybrid path (when ``hybrid_code_gen`` and cwd rules allow): implement roles
    resolve to ``mode=executor``. PR1 accepts an injectable ``executor_runner``
    (tests / future AgentRunner). Without a runner, executor roles **fall back
    to chat** so behavior stays safe until PR2.

    Cost/token savings on the multi-agent path:
      - **temperature=0.0** → deterministic chain → the gateway response cache hits
        on repeat runs of the same task (each sub-agent billed 0 new tokens).
      - **memory** (MemoryStore-like): relevant prior context injected per sub-agent
        and each result stored back → cross-task reuse.
      - **headroom** (optional, when the proxy runs): compresses the sub-agent prompt.

    Sub-tasks are processed in dependency order; each dependent agent receives prior
    agents' outputs. Mutates and returns the assignments with usage/cost/savings.
    """
    from voly.a2a.decomposer import TaskDecomposer
    from voly.a2a.hybrid import hybrid_active, resolve_role_mode
    from voly.telemetry import _estimate_cost

    if tracker is not None and task_id:
        tracker.start(task_id, task, [a.role for a in assignments])

    hybrid_on = hybrid_active(
        hybrid_code_gen=hybrid_code_gen,
        has_cwd=bool((cwd or "").strip()),
        hybrid_require_cwd=hybrid_require_cwd,
    )
    if hybrid_code_gen and hybrid_require_cwd and not (cwd or "").strip():
        _log.info("multiagent hybrid: no cwd — all roles stay chat (hybrid_skipped_no_cwd)")

    done: dict[int, Assignment] = {}
    for a in assignments:
        # Skip dependents when a required prior role failed (hybrid default).
        if skip_dependents_on_failure and a.depends_on:
            failed_priors = [
                done[d].role for d in a.depends_on
                if d in done and not done[d].ok
            ]
            if failed_priors:
                a.ok = False
                a.error = f"skipped: prior role(s) failed ({', '.join(failed_priors)})"
                a.content = f"({a.error})"
                a.mode, a.mode_reason = "chat", "skipped_prior_failed"
                done[a.idx] = a
                if tracker is not None and task_id:
                    tracker.heartbeat(task_id, a.role, len(done))
                continue

        mode, reason = resolve_role_mode(
            a.role,
            hybrid_enabled=hybrid_on,
            requires_code_gen=requires_code_gen,
            lead_execution=a.execution or None,
            executor_roles=executor_roles,
        )
        a.mode = mode
        a.mode_reason = reason

        prior = [(done[d].role, done[d].content) for d in a.depends_on if d in done and done[d].ok]
        user = TaskDecomposer.inject_prior_context(a.description, prior)

        mem_block, a.mem_hits = _memory_block(memory, f"{a.role}: {a.description}")
        if mem_block:
            user = f"{mem_block}\n\n{user}"

        persona = _ROLE_PROMPT.get(a.role, _DEFAULT_PERSONA)
        skills = _skills_block(a.skills, skill_matcher, task, a.role)
        system = f"{persona}\n\n{skills}".strip() if skills else persona

        # ── Executor branch (PR1: injectable runner; PR2: AgentRunner) ────────
        if mode == "executor":
            a.executor = executor_default or "claude-code"
            if executor_runner is not None:
                _log.info(
                    "multiagent[%d] %s → EXECUTOR %s (cwd=%s, reason=%s)",
                    a.idx, a.role, a.executor, cwd or "(none)", reason,
                )
                try:
                    result = executor_runner(
                        role=a.role,
                        task=user,
                        cwd=cwd,
                        executor=a.executor,
                        system=system,
                        assignment=a,
                    )
                except Exception as e:  # noqa: BLE001
                    a.error = str(e)
                    a.content = f"(executor failed: {e})"
                    a.ok = False
                    done[a.idx] = a
                    if tracker is not None and task_id:
                        tracker.heartbeat(task_id, a.role, len(done))
                    continue

                if isinstance(result, dict):
                    a.content = str(result.get("content") or result.get("output") or "")
                    a.ok = bool(result.get("ok", result.get("success", bool(a.content.strip()))))
                    a.error = str(result.get("error") or "")
                    a.cost_usd = float(result.get("cost_usd") or 0.0)
                    a.input_tokens = int(result.get("input_tokens") or 0)
                    a.output_tokens = int(result.get("output_tokens") or 0)
                    a.files_touched = list(result.get("files_touched") or [])
                    if result.get("executor"):
                        a.executor = str(result["executor"])
                else:
                    a.content = str(result or "")
                    a.ok = bool(a.content.strip())
                done[a.idx] = a
                if tracker is not None and task_id:
                    tracker.heartbeat(task_id, a.role, len(done))
                continue

            # No runner yet — fall back to chat so production stays useful.
            _log.info(
                "multiagent[%d] %s mode=executor but no executor_runner — chat fallback",
                a.idx, a.role,
            )
            a.mode_reason = f"{reason}+chat_fallback_no_runner"

        messages = [{"role": "user", "content": user}]
        if headroom is not None:
            try:
                if headroom.is_running():
                    res = headroom.compress(messages, model=a.model)
                    messages = res.get("messages", messages)
                    a.saved_tokens = res.get("tokens_saved", 0)
            except Exception as e:  # noqa: BLE001
                _log.debug("headroom compress skipped: %s", e)

        _log.info("multiagent[%d] %s → %s/%s (tier=%s, mode=%s, skills=%s, mem=%d)",
                  a.idx, a.role, a.provider, a.model, a.tier, a.mode, a.skills, a.mem_hits)
        resp: dict[str, Any] = {}
        try:
            resp = gateway.chat(
                messages,
                model=a.model, provider_name=a.provider, system=system,
                agent=a.role, max_tokens=max_tokens, temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            a.error = str(e)
            a.content = f"(failed: {e})"
            done[a.idx] = a
            if tracker is not None and task_id:
                tracker.heartbeat(task_id, a.role, len(done))
            continue

        if resp.get("error"):
            a.error = str(resp["error"])
            a.content = f"(failed: {a.error})"
        else:
            a.content = resp.get("content", "") or ""
            usage = resp.get("usage", {}) or {}
            a.input_tokens = usage.get("input_tokens", 0)
            a.output_tokens = usage.get("output_tokens", 0)
            a.cache_hit = bool(resp.get("cache_hit"))
            # Cache hit = 0 new tokens billed → no cost this run.
            a.cost_usd = 0.0 if a.cache_hit else _estimate_cost(
                resp.get("model", a.model), a.input_tokens, a.output_tokens)
            a.ok = bool(a.content.strip())
            if a.ok and memory is not None and not a.cache_hit:
                try:
                    memory.add(
                        title=f"[{a.role}] {a.description[:80]}",
                        content=a.content[:2000], category="history",
                        metadata={"role": a.role, "model": a.model, "provider": a.provider,
                                  "task": task[:200]},
                        importance=0.5, tags=[a.role, "a2a"],
                    )
                except Exception as e:  # noqa: BLE001
                    _log.debug("memory store skipped for %s: %s", a.role, e)
        done[a.idx] = a
        if tracker is not None and task_id:
            tracker.heartbeat(task_id, a.role, len(done))

        # Spend limit is a hard stop for the WHOLE chain: remaining sub-agents
        # would only re-hit the same exhausted budget. Mark them spend-limited
        # (same observable outcome) but WITHOUT another gateway call, and stop —
        # early exit instead of walking every role. (Budget isolation, Этап 4.)
        if resp.get("spend_limited"):
            _log.info("multiagent: spend limit hit at role %s — stopping chain", a.role)
            for rest in assignments:
                if rest.idx not in done:
                    rest.error = str(resp.get("error") or "Spend limit exceeded")
                    rest.ok = False
                    done[rest.idx] = rest
            break

    if tracker is not None and task_id:
        any_ok = any(a.ok for a in assignments)
        tracker.finish(task_id, status="completed" if any_ok else "failed")
    return assignments


def merge_report(task: str, assignments: list[Assignment]) -> str:
    """Human-readable merged report: what each agent (model/tier) produced."""
    lines = [f"# Multi-agent result: {task[:120]}", ""]
    for a in assignments:
        status = "✓" if a.ok else "✗"
        skills = ", ".join(a.skills) if a.skills else "—"
        lines.append(
            f"## [{a.role}] {status}  ·  {a.provider}/{a.model} (tier={a.tier})  ·  skills: {skills}"
        )
        lines.append("")
        lines.append(a.content.strip() or "(no output)")
        lines.append("\n---\n")
    return "\n".join(lines).strip()
