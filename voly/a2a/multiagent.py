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

import logging
from collections.abc import Callable
from typing import Any

# Re-exported for backward compatibility — external callers import these from
# voly.a2a.multiagent (pipeline/stages.py, telemetry, tests).
from voly.a2a.assignment import Assignment, resolve_tier_model  # noqa: F401
from voly.a2a.lead import LeadOrchestrator, _parse_plan  # noqa: F401

_log = logging.getLogger("voly.a2a.multiagent")

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
    # Plan gates (Rung B PR4)
    plan_config: Any = None,
    plan_store: Any = None,
) -> list[Assignment]:
    """Execute each sub-agent in dependency order.

    Default path: ``AIGateway.chat()`` (text).

    Hybrid path (when ``hybrid_code_gen`` and cwd rules allow): implement roles
    resolve to ``mode=executor``. PR1 accepts an injectable ``executor_runner``
    (tests / future AgentRunner). Without a runner, executor roles **fall back
    to chat** so behavior stays safe until PR2.

    When ``plan_config`` has gates enabled (``enabled`` + ``mode`` shadow|active
    + ``a2a_attach``), each role is mirrored as a Plan step: dependents start
    only after prior steps are **verified** (not merely process-complete).

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
    from voly.plan.bridge import (
        assignment_step_id,
        assignments_to_plan,
        plan_gates_enabled,
        sync_assignment_plan_fields,
    )
    from voly.plan.engine import PlanEngine
    from voly.plan.store import PlanStore
    from voly.plan.types import FAILED, RUNNING, VERIFIED, VERIFYING
    from voly.plan.verify import VerifyContext, complete_verification, git_porcelain
    from voly.telemetry import _estimate_cost

    has_cwd = bool((cwd or "").strip())
    hybrid_on = hybrid_active(
        hybrid_code_gen=hybrid_code_gen,
        has_cwd=has_cwd,
        hybrid_require_cwd=hybrid_require_cwd,
    )
    if hybrid_code_gen and not has_cwd:
        _log.warning("multiagent hybrid: no cwd — all roles stay chat (hybrid_skipped_no_cwd)")

    # Pre-resolve hybrid modes so the plan mirror matches execution.
    role_modes: dict[int, str] = {}
    for a in assignments:
        mode, reason = resolve_role_mode(
            a.role,
            hybrid_enabled=hybrid_on,
            requires_code_gen=requires_code_gen,
            lead_execution=a.execution or None,
            executor_roles=executor_roles,
        )
        # Executors never run without an explicit project cwd, even when
        # hybrid_require_cwd is off — never invent a project path.
        if mode == "executor" and not has_cwd:
            mode, reason = "chat", "no_cwd"
        a.mode = mode
        a.mode_reason = reason
        role_modes[a.idx] = mode

    plan = None
    engine: PlanEngine | None = None
    store = None
    plan_mode = "off"
    gates_on = plan_gates_enabled(plan_config)
    if gates_on:
        engine = PlanEngine()
        plan_mode = (getattr(plan_config, "mode", "shadow") or "shadow").lower()
        plan_id = f"a2a-{task_id}" if task_id else f"a2a-{abs(hash(task)) % 10**10}"
        plan = assignments_to_plan(
            task,
            assignments,
            plan_id=plan_id,
            task_id=task_id,
            cwd=cwd or "",
            plan_cfg=plan_config,
            role_modes=role_modes,
        )
        try:
            engine.validate(plan)
        except Exception as exc:  # noqa: BLE001
            _log.warning("plan gates disabled — invalid plan: %s", exc)
            plan = None
            engine = None
            gates_on = False
        else:
            store = plan_store or PlanStore(
                getattr(plan_config, "store_dir", None) or ".voly/plans"
            )
            store.save(plan)
            _log.info(
                "multiagent plan gates ON mode=%s plan_id=%s steps=%d",
                plan_mode, plan.plan_id, len(plan.steps),
            )

    if tracker is not None and task_id:
        tracker.start(
            task_id,
            task,
            [a.role for a in assignments],
            plan_id=plan.plan_id if plan else "",
        )

    def _step_snapshot() -> list[dict[str, Any]]:
        if plan is None:
            return []
        return [{"id": s.id, "status": s.status, "role": s.role} for s in plan.steps]

    def _hb(role: str, done_n: int) -> None:
        if tracker is not None and task_id:
            tracker.heartbeat(
                task_id, role, done_n,
                step_statuses=_step_snapshot() if plan is not None else None,
            )

    def _finish_step_plan(a: Assignment, *, exec_ok: bool, git_before: dict) -> None:
        """After role execution: mark plan step done/verified/failed."""
        if plan is None or engine is None:
            return
        sid = assignment_step_id(a.idx, a.role)
        step = plan.get_step(sid)
        step.output = a.content or ""
        step.files_touched = list(a.files_touched or [])
        if not exec_ok:
            if step.status == RUNNING:
                engine.transition(plan, sid, FAILED, error=a.error or "role failed")
            sync_assignment_plan_fields(a, plan.get_step(sid))
            if store is not None:
                store.save(plan)
            return

        engine.mark_execution_finished(
            plan, sid, success=True, output=a.content or "",
            files_touched=a.files_touched,
        )
        engine.advance_after_done(plan, sid)
        step = plan.get_step(sid)
        if step.status == VERIFYING:
            git_after = git_porcelain(cwd) if cwd else {}
            ctx = VerifyContext(
                cwd=cwd or "",
                output=a.content or "",
                files_touched=list(a.files_touched or []),
                git_before=git_before,
                git_after=git_after,
                command_timeout=float(
                    getattr(plan_config, "command_timeout_seconds", 120.0) or 120.0
                ),
            )
            step, _results = complete_verification(
                plan, sid, ctx, engine=engine
            )
            if step.status == FAILED and plan_mode == "shadow":
                _log.warning(
                    "plan step %s verify failed (shadow → force verified): %s",
                    sid, step.error,
                )
                step.status = VERIFIED
                engine.recompute_plan_status(plan)
        step = plan.get_step(sid)
        sync_assignment_plan_fields(a, step)
        # Active: failed verify → not ok (dependents skip). Shadow soft-verify → keep ok.
        if step.status == FAILED:
            a.ok = False
            if not a.error:
                a.error = step.error or "plan verification failed"
        elif step.status == VERIFIED and plan_mode == "shadow":
            # Soft-opened after verify fail: process still counts as ok for dependents.
            if step.verify_log and not all(bool(e.get("ok")) for e in step.verify_log):
                a.ok = True
        if store is not None:
            store.save(plan)

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
                a.mode, a.mode_reason = a.mode or "chat", "skipped_prior_failed"
                a.plan_status = "skipped"
                done[a.idx] = a
                _hb(a.role, len(done))
                continue

        # Plan gate: only start when depends_on steps are verified.
        if plan is not None and engine is not None:
            sid = assignment_step_id(a.idx, a.role)
            if not engine.can_start(plan, sid):
                unmet = engine.unmet_deps(plan, sid)
                a.ok = False
                a.error = f"blocked: plan deps not verified ({unmet})"
                a.content = f"({a.error})"
                a.plan_status = "blocked"
                done[a.idx] = a
                _hb(a.role, len(done))
                continue
            engine.transition(plan, sid, RUNNING)
            a.plan_status = RUNNING
            if store is not None:
                store.save(plan)

        mode = a.mode or role_modes.get(a.idx, "chat")
        reason = a.mode_reason
        git_before = git_porcelain(cwd) if cwd else {}

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
                    _finish_step_plan(a, exec_ok=False, git_before=git_before)
                    done[a.idx] = a
                    _hb(a.role, len(done))
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
                _finish_step_plan(a, exec_ok=a.ok, git_before=git_before)
                done[a.idx] = a
                _hb(a.role, len(done))
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
            a.ok = False
            _finish_step_plan(a, exec_ok=False, git_before=git_before)
            done[a.idx] = a
            _hb(a.role, len(done))
            continue

        if resp.get("error"):
            a.error = str(resp["error"])
            a.content = f"(failed: {a.error})"
            a.ok = False
            process_ok = False
        else:
            a.content = resp.get("content", "") or ""
            usage = resp.get("usage", {}) or {}
            a.input_tokens = usage.get("input_tokens", 0)
            a.output_tokens = usage.get("output_tokens", 0)
            a.cache_hit = bool(resp.get("cache_hit"))
            # Cache hit = 0 new tokens billed → no cost this run.
            a.cost_usd = 0.0 if a.cache_hit else _estimate_cost(
                resp.get("model", a.model), a.input_tokens, a.output_tokens)
            # With plan gates, empty content is an acceptance concern (output_nonempty),
            # not a hard process failure — so dependents can be soft-gated in shadow.
            process_ok = True
            a.ok = bool(a.content.strip()) if not gates_on else True
            if a.content.strip() and memory is not None and not a.cache_hit:
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
        _finish_step_plan(a, exec_ok=process_ok if gates_on else a.ok, git_before=git_before)
        done[a.idx] = a
        _hb(a.role, len(done))

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

    if plan is not None and engine is not None:
        engine.recompute_plan_status(plan)
        if store is not None:
            store.save(plan)

    if tracker is not None and task_id:
        any_ok = any(a.ok for a in assignments)
        tracker.finish(
            task_id,
            status="completed" if any_ok else "failed",
            step_statuses=_step_snapshot() if plan is not None else None,
        )
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
