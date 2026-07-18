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
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Re-exported for backward compatibility — external callers import these from
# voly.a2a.multiagent (pipeline/stages.py, telemetry, tests).
from voly.a2a.assignment import (
    Assignment,
    chat_fallback_providers,
    evaluate_multiagent_outcome,
    exclude_provider_on_gateway_error as _exclude_provider_on_gateway_error,
    resolve_tier_model,
)  # noqa: F401
from voly.a2a.hybrid import resolve_role_executor
from voly.a2a.lead import LeadOrchestrator, _parse_plan  # noqa: F401

_log = logging.getLogger("voly.a2a.multiagent")

# Project doc files read into architect's context when cwd is available.
_PROJECT_CONTEXT_FILES = ("CLAUDE.md", "README.md", "ARCHITECTURE.md", "docs/ARCHITECTURE.md")
_PROJECT_CONTEXT_MAX_CHARS = 2500


def _git_diff_evidence(
    cwd: str,
    files: list[str],
    *,
    max_chars: int = 3500,
    max_files: int = 12,
) -> str:
    """Unified git diff for reviewer/tester — real file evidence, not summaries."""
    import subprocess

    if not cwd or not files:
        return ""
    paths = [
        f for f in files
        if f and not str(f).startswith(".voly/")
    ][:max_files]
    if not paths:
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "diff", "--no-color", "--", *paths],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    diff = (proc.stdout or "").strip()
    if not diff:
        # Untracked new files: show brief content heads.
        heads: list[str] = []
        for rel in paths[:8]:
            fp = Path(cwd) / rel
            if not fp.is_file():
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            heads.append(f"--- a/{rel}\n+++ b/{rel}\n@@ new file @@\n" + text[:400])
        diff = "\n".join(heads)
    if not diff:
        return ""
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n...(diff truncated)"
    return (
        "## Working-tree evidence (untrusted git diff)\n"
        "Use this as ground truth for which files exist and what changed. "
        "Do not invent missing files that appear here.\n\n"
        f"```diff\n{diff}\n```"
    )


def _delta_for_role(
    cwd: str,
    git_before: dict,
    *,
    since: float,
) -> list[str]:
    """Git paths changed since ``git_before``, excluding other runs' noise.

    Filters out ``.voly/`` and files whose mtime is older than the role start
    (same-cwd parallel ``voly run`` mix).
    """
    from voly.plan.verify import changed_paths, git_porcelain

    git_after = git_porcelain(cwd)
    raw = sorted(changed_paths(git_before, git_after))
    out: list[str] = []
    floor = since - 1.5
    for rel in raw:
        if not rel or str(rel).startswith(".voly/"):
            continue
        fp = Path(cwd) / rel
        try:
            if fp.exists() and fp.stat().st_mtime < floor:
                continue
        except OSError:
            pass
        out.append(rel)
    return out


def _project_context_block(cwd: str) -> str:
    """Read key project files to give the architect project-specific context."""
    import os
    if not cwd or not os.path.isdir(cwd):
        return ""
    parts: list[str] = []
    remaining = _PROJECT_CONTEXT_MAX_CHARS
    for name in _PROJECT_CONTEXT_FILES:
        path = os.path.join(cwd, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read(remaining)
            snippet = content.strip()
            if snippet:
                parts.append(f"## {name}\n{snippet}")
                remaining -= len(snippet)
                if remaining <= 0:
                    break
        except OSError:
            continue
    return "\n\n".join(parts)


_FILE_LINE_POLICY = (
    "File size policy: every created/modified file must stay within 300 lines of code. "
    "Up to 500 lines is allowed only when the architect explicitly approved it in the plan "
    "with two separate lines: `FILE_LINE_LIMIT: 500` and `FILE_LINE_LIMIT_REASON: <rationale>`."
)

_ROLE_PROMPT: dict[str, str] = {
    "architect": (
        "You are a senior software architect. Design the architecture: modules, interfaces, "
        "data flow, key decisions, and risks. Plan only — NO full code "
        "(no ``` blocks and no file content listings). "
        f"{_FILE_LINE_POLICY}"
    ),
    "developer": (
        "You are a senior developer. Implement the solution in the project files following "
        "the architecture plan. Do not paste the full code into your reply — give a brief "
        f"summary of the changes. {_FILE_LINE_POLICY}"
    ),
    "tester": (
        "You are a QA engineer. Write tests (pytest if Python) covering happy-path, "
        f"boundary, and negative cases. {_FILE_LINE_POLICY}"
    ),
    "reviewer": "You are a code reviewer. Assess the code and tests: bugs, security, "
                "readability, performance. Give concrete remarks and a verdict.",
    "devops": "You are a DevOps engineer. Prepare the deployment: Dockerfile/compose, "
              "CI steps, environment variables, release checklist.",
    "security": "You are an application security engineer. Find vulnerabilities in the code "
                "and propose fixes.",
}
_DEFAULT_PERSONA = (
    "You are a specialist engineer. Complete the assigned sub-task with quality and brevity."
)

def _chat_with_provider_fallback(
    gateway: Any,
    *,
    messages: list[dict[str, str]],
    assignment: Assignment,
    system: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    """Try gateway.chat on the assigned provider, then other healthy tier providers."""
    from voly.ai_gateway.health import get_checker
    from voly.router import _PROVIDER_MODELS

    providers = chat_fallback_providers(assignment.tier, assignment.role)
    assigned = assignment.provider
    if assigned:
        # The assignment was resolved before earlier roles ran; skip the assigned
        # provider when it has since been marked unhealthy (401/billing) instead
        # of burning one failed call per role on a known-dead provider.
        if get_checker().check(assigned).healthy:
            providers = [assigned] + [p for p in providers if p != assigned]
        else:
            providers = [p for p in providers if p != assigned]
    if not providers:
        providers = [assigned] if assigned else []

    last_err = ""
    for provider in providers:
        model = _PROVIDER_MODELS.get(provider, (assignment.model, provider))[0]
        try:
            resp = gateway.chat(
                messages,
                model=model,
                provider_name=provider,
                system=system,
                agent=assignment.role,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            _exclude_provider_on_gateway_error(provider, last_err)
            _log.warning(
                "multiagent[%d] %s chat %s failed (%s) — trying next provider",
                assignment.idx, assignment.role, provider, last_err[:120],
            )
            continue

        if resp.get("error"):
            # Spend limit is a budget stop, not a provider fault — retrying other
            # providers re-hits the same exhausted budget. Return as-is so
            # run_local's spend_limited early-exit can halt the whole chain.
            if resp.get("spend_limited"):
                return resp
            last_err = str(resp["error"])
            _exclude_provider_on_gateway_error(provider, last_err)
            _log.warning(
                "multiagent[%d] %s chat %s error (%s) — trying next provider",
                assignment.idx, assignment.role, provider, last_err[:120],
            )
            continue

        if provider != assignment.provider:
            assignment.provider = provider
            assignment.model = model
            assignment.mode_reason = (
                f"{assignment.mode_reason}+provider_fallback"
                if assignment.mode_reason
                else "provider_fallback"
            )
        return resp

    return {"error": last_err or "all chat providers failed", "content": ""}


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


def _build_waves(assignments: list[Assignment]) -> list[list[Assignment]]:
    """Group assignments into dependency waves (topological levels).

    Roles in the same wave have no dependencies on each other, so their chat
    calls can run concurrently. Unknown/cyclic dependencies degrade gracefully
    to one-role waves in list order.
    """
    idxs = {a.idx for a in assignments}
    placed: set[int] = set()
    remaining = list(assignments)
    waves: list[list[Assignment]] = []
    while remaining:
        wave = [
            a for a in remaining
            if all(d in placed or d not in idxs for d in a.depends_on)
        ]
        if not wave:  # dependency cycle — fall back to sequential
            wave = [remaining[0]]
        placed.update(a.idx for a in wave)
        remaining = [a for a in remaining if a.idx not in placed]
        waves.append(wave)
    return waves


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
    # Wave parallelism (P4): concurrent chat calls for independent roles.
    parallel_waves: bool = True,
    max_parallel_roles: int = 3,
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
    from voly.plan.verify import VerifyContext, changed_paths, complete_verification, git_porcelain
    from voly.telemetry import _estimate_cost

    has_cwd = bool((cwd or "").strip())
    hybrid_on = hybrid_active(
        hybrid_code_gen=hybrid_code_gen,
        has_cwd=has_cwd,
        hybrid_require_cwd=hybrid_require_cwd,
    )
    if hybrid_code_gen and not has_cwd:
        _log.warning("multiagent hybrid: no cwd — all roles stay chat (hybrid_skipped_no_cwd)")

    _log.info(
        "[PIPELINE:A2A] run_local roles=%s cwd=%s hybrid=%s task_id=%s",
        [a.role for a in assignments],
        cwd or "(none)",
        hybrid_on,
        task_id or "",
    )

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
            # Tester chat roles rarely touch files — scope pytest using prior
            # executor files_touched (greenfield: only new test_*.py).
            verify_files = list(a.files_touched or [])
            if not verify_files:
                for d in a.depends_on:
                    prior_a = done.get(d)
                    if prior_a is None:
                        continue
                    verify_files.extend(prior_a.files_touched or [])
            # de-dupe, drop .voly noise
            seen: set[str] = set()
            scoped: list[str] = []
            for f in verify_files:
                if not f or str(f).startswith(".voly/") or f in seen:
                    continue
                seen.add(f)
                scoped.append(f)
            ctx = VerifyContext(
                cwd=cwd or "",
                output=a.content or "",
                files_touched=scoped or list(a.files_touched or []),
                git_before=git_before,
                git_after=git_after,
                command_timeout=float(
                    getattr(plan_config, "command_timeout_seconds", 60.0) or 60.0
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
    # idx → failed prior roles, for chat roles that run degraded (not skipped).
    degraded_notes: dict[int, list[str]] = {}

    def _prepare(a: Assignment) -> tuple[str, str, dict] | None:
        """Pre-flight in the caller thread: cascade/plan-gate + prompt build.

        Returns (user, system, git_before) when the role should execute, or
        None when it was finalized here (skipped/blocked).
        """
        # Cascade policy when a required prior role failed:
        #   - executor roles need the implementation → hard skip
        #   - chat roles degrade gracefully IF at least one prior succeeded
        #     (e.g. reviewer/tester/devops run on the architect plan alone)
        #   - if ALL priors failed → hard skip regardless of mode
        if skip_dependents_on_failure and a.depends_on:
            failed_priors = [
                done[d].role for d in a.depends_on
                if d in done and not done[d].ok
            ]
            ok_priors = [
                done[d].role for d in a.depends_on
                if d in done and done[d].ok
            ]
            if failed_priors:
                role_mode = role_modes.get(a.idx, a.mode or "chat")
                # Early-exit for code_gen tasks: when all executor roles that have
                # completed produced no code, post-impl chat roles cannot act —
                # skip them. An executor that wrote files but failed soft safety
                # still counts as code produced (do not cascade-skip).
                impl_done = [done[i] for i in done if done[i].mode == "executor"]

                def _impl_has_code(d: Assignment) -> bool:
                    if d.ok:
                        return True
                    return any(
                        f and not str(f).startswith(".voly/")
                        for f in (d.files_touched or [])
                    )

                all_impl_failed = bool(impl_done) and not any(
                    _impl_has_code(d) for d in impl_done
                )
                if requires_code_gen and role_mode == "chat" and ok_priors and all_impl_failed:
                    a.ok = False
                    a.error = (
                        f"skipped: no code produced — all executor roles failed "
                        f"({', '.join(d.role for d in impl_done if not d.ok)})"
                    )
                    a.content = f"({a.error})"
                    a.mode, a.mode_reason = role_mode, "skipped_no_code"
                    a.plan_status = "skipped"
                    done[a.idx] = a
                    _hb(a.role, len(done))
                    _log.info(
                        "multiagent[%d] %s early-exit: code_gen but no impl succeeded",
                        a.idx, a.role,
                    )
                    return None
                hard_block = role_mode == "executor" or not ok_priors
                if hard_block:
                    a.ok = False
                    a.error = f"skipped: prior role(s) failed ({', '.join(failed_priors)})"
                    a.content = f"({a.error})"
                    a.mode, a.mode_reason = a.mode or "chat", "skipped_prior_failed"
                    a.plan_status = "skipped"
                    done[a.idx] = a
                    _hb(a.role, len(done))
                    return None
                degraded_notes[a.idx] = failed_priors
                a.mode_reason = (
                    f"{a.mode_reason}+degraded_prior_failed"
                    if a.mode_reason else "degraded_prior_failed"
                )
                _log.info(
                    "multiagent[%d] %s degraded: prior failed (%s), running on (%s)",
                    a.idx, a.role, ", ".join(failed_priors), ", ".join(ok_priors),
                )

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
                return None
            engine.transition(plan, sid, RUNNING)
            a.plan_status = RUNNING
            if store is not None:
                store.save(plan)

        git_before = git_porcelain(cwd) if cwd else {}

        prior = [
            (
                done[d].role,
                done[d].content,
                list(done[d].files_touched or []),
            )
            for d in a.depends_on
            if d in done and done[d].ok
        ]
        user = TaskDecomposer.inject_prior_context(a.description, prior)
        # Reviewer/tester need real diffs — chat-only summaries cause hallucinations
        # ("no migration") when the developer already wrote the file.
        if a.role in ("reviewer", "tester") and cwd:
            evidence_files: list[str] = []
            for d in a.depends_on:
                prior_a = done.get(d)
                if prior_a is None:
                    continue
                evidence_files.extend(prior_a.files_touched or [])
            evidence = _git_diff_evidence(cwd, evidence_files)
            if evidence:
                user = f"{user}\n\n{evidence}"

        if a.idx in degraded_notes:
            failed = ", ".join(degraded_notes[a.idx])
            user = (
                f"WARNING: previous roles did not complete ({failed}). "
                "Work from the available context (the architect's plan). "
                "Explicitly note in your reply that the implementation is missing or "
                "incomplete and which steps must be re-checked once it appears.\n\n"
                f"{user}"
            )

        mem_block, a.mem_hits = _memory_block(memory, f"{a.role}: {a.description}")
        if mem_block:
            user = f"{mem_block}\n\n{user}"

        persona = _ROLE_PROMPT.get(a.role, _DEFAULT_PERSONA)
        skills = _skills_block(a.skills, skill_matcher, task, a.role)
        system = f"{persona}\n\n{skills}".strip() if skills else persona
        # Inject project context for architect so it can give project-specific
        # answers rather than generic advice (P3: "неточный ответ architect").
        if a.role == "architect" and cwd:
            ctx = _project_context_block(cwd)
            if ctx:
                system = f"{system}\n\n## Project context\n{ctx}".strip()
        return user, system, git_before

    def _run_executor(a: Assignment, user: str, system: str, git_before: dict) -> None:
        """Executor role: run serially in the caller thread and finalize."""
        # Re-snapshot right before running — a same-wave executor may have
        # already changed the tree, and chat calls happened since _prepare.
        if cwd:
            git_before = git_porcelain(cwd)
        _log.info(
            "multiagent[%d] %s → EXECUTOR %s (cwd=%s, reason=%s)",
            a.idx, a.role, a.executor, cwd or "(none)", a.mode_reason,
        )
        _t0 = time.monotonic()
        _wall0 = time.time()
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
            a.duration_ms = (time.monotonic() - _t0) * 1000
            a.error = str(e)
            a.content = f"(executor failed: {e})"
            a.ok = False
            # Even a crashed/timed-out executor may have written files;
            # capture the git delta so files_touched reflects reality.
            if cwd:
                delta = _delta_for_role(cwd, git_before, since=_wall0)
                if delta:
                    a.files_touched = delta
            _finish_step_plan(a, exec_ok=False, git_before=git_before)
            done[a.idx] = a
            _hb(a.role, len(done))
            return
        a.duration_ms = (time.monotonic() - _t0) * 1000

        if isinstance(result, dict):
            a.content = str(result.get("content") or result.get("output") or "")
            a.ok = bool(result.get("ok", result.get("success", bool(a.content.strip()))))
            a.error = str(result.get("error") or "")
            a.cost_usd = float(result.get("cost_usd") or 0.0)
            a.input_tokens = int(result.get("input_tokens") or 0)
            a.output_tokens = int(result.get("output_tokens") or 0)
            a.files_touched = [
                f for f in (result.get("files_touched") or [])
                if f and not str(f).startswith(".voly/")
            ]
            if result.get("executor"):
                a.executor = str(result["executor"])
        else:
            a.content = str(result or "")
            a.ok = bool(a.content.strip())
        if cwd and not a.files_touched:
            delta = _delta_for_role(cwd, git_before, since=_wall0)
            if delta:
                a.files_touched = delta
        # Executor honesty: on a code-gen task a role that "succeeded" without
        # touching a single file only produced text — that is not an
        # implementation (e.g. cursor returning a plausible summary while the
        # bridge silently wrote nothing). Fail the role so downstream degrades
        # and the run reports partial instead of a false completed.
        if requires_code_gen and a.ok and not a.files_touched:
            a.ok = False
            a.error = (
                "executor reported success but changed no files "
                f"(executor={a.executor or 'unknown'})"
            )
            _log.warning(
                "multiagent[%d] %s executor success with zero files — marked failed",
                a.idx, a.role,
            )
        _finish_step_plan(a, exec_ok=a.ok, git_before=git_before)
        done[a.idx] = a
        _hb(a.role, len(done))

    def _chat_call(a: Assignment, user: str, system: str) -> dict[str, Any]:
        """Gateway call only — the sole part that may run in a worker thread."""
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
        role_max_tokens = 2048 if a.role == "architect" else max_tokens
        _t0 = time.monotonic()
        try:
            return _chat_with_provider_fallback(
                gateway,
                messages=messages,
                assignment=a,
                system=system,
                max_tokens=role_max_tokens,
                temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            return {"__raised__": True, "error": str(e), "content": ""}
        finally:
            # Only this worker thread touches this assignment — safe mutation.
            a.duration_ms = (time.monotonic() - _t0) * 1000

    def _finalize_chat(a: Assignment, resp: dict[str, Any], git_before: dict) -> bool:
        """Parse the response + memory/plan bookkeeping. True → spend-limited."""
        if resp.get("__raised__"):
            a.error = str(resp.get("error") or "")
            a.content = f"(failed: {a.error})"
            a.ok = False
            _exclude_provider_on_gateway_error(a.provider, a.error)
            _finish_step_plan(a, exec_ok=False, git_before=git_before)
            done[a.idx] = a
            _hb(a.role, len(done))
            return False

        if resp.get("error"):
            a.error = str(resp["error"])
            a.content = f"(failed: {a.error})"
            a.ok = False
            process_ok = False
            _exclude_provider_on_gateway_error(a.provider, a.error)
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
            # not a hard process failure — shadow mode keeps dependents running
            # (degraded) instead of blocking on an empty chat reply.
            process_ok = True
            a.ok = bool(a.content.strip()) if not gates_on else True
            if not a.content.strip():
                a.ok = False
                a.error = "empty response from provider"
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
        return bool(resp.get("spend_limited"))

    # ── Wave scheduling (P4): independent roles share a wave; a wave's chat
    # calls run concurrently, executor roles stay serial (shared cwd/git).
    workers_cap = max(1, int(max_parallel_roles or 1))
    use_parallel = bool(parallel_waves) and workers_cap > 1
    waves = _build_waves(assignments) if use_parallel else [[a] for a in assignments]

    spend_stop: dict[str, Any] | None = None
    for wave in waves:
        chat_items: list[tuple[Assignment, str, str, dict]] = []
        exec_items: list[tuple[Assignment, str, str, dict]] = []
        for a in wave:
            prep = _prepare(a)
            if prep is None:
                continue
            user, system, git_before = prep
            mode = a.mode or role_modes.get(a.idx, "chat")
            if mode == "executor":
                a.executor = resolve_role_executor(a.role, executor_default or "claude-code")
                if executor_runner is None:
                    # No runner yet — fall back to chat so production stays useful.
                    _log.info(
                        "multiagent[%d] %s mode=executor but no executor_runner — chat fallback",
                        a.idx, a.role,
                    )
                    a.mode_reason = f"{a.mode_reason}+chat_fallback_no_runner"
                    mode = "chat"
            if mode == "executor":
                exec_items.append((a, user, system, git_before))
            else:
                chat_items.append((a, user, system, git_before))

        resps: dict[int, dict[str, Any]] = {}
        if use_parallel and len(chat_items) > 1:
            from concurrent.futures import ThreadPoolExecutor

            _log.info(
                "multiagent wave: %d chat roles in parallel (%s)",
                len(chat_items), ", ".join(a.role for a, *_ in chat_items),
            )
            with ThreadPoolExecutor(
                max_workers=min(len(chat_items), workers_cap),
                thread_name_prefix="a2a-wave",
            ) as pool:
                futures = {
                    pool.submit(_chat_call, a, user, system): a.idx
                    for a, user, system, _ in chat_items
                }
                for fut, idx in futures.items():
                    resps[idx] = fut.result()
        else:
            for a, user, system, _ in chat_items:
                resps[a.idx] = _chat_call(a, user, system)

        for a, user, system, git_before in exec_items:
            _run_executor(a, user, system, git_before)

        for a, user, system, git_before in chat_items:
            if _finalize_chat(a, resps[a.idx], git_before):
                spend_stop = resps[a.idx]

        # Spend limit is a hard stop for the WHOLE chain: remaining sub-agents
        # would only re-hit the same exhausted budget. Mark them spend-limited
        # (same observable outcome) but WITHOUT another gateway call, and stop —
        # early exit instead of walking every wave. (Budget isolation, Этап 4.)
        if spend_stop is not None:
            _log.info("multiagent: spend limit hit — stopping chain")
            for rest in assignments:
                if rest.idx not in done:
                    rest.error = str(spend_stop.get("error") or "Spend limit exceeded")
                    rest.ok = False
                    done[rest.idx] = rest
            break

    if plan is not None and engine is not None:
        engine.recompute_plan_status(plan)
        if store is not None:
            store.save(plan)

    if tracker is not None and task_id:
        _, ma_status = evaluate_multiagent_outcome(assignments)
        tracker.finish(
            task_id,
            status=ma_status,
            step_statuses=_step_snapshot() if plan is not None else None,
        )
    return assignments


def merge_report(task: str, assignments: list[Assignment]) -> str:
    """Human-readable merged report: what each agent (model/tier) produced."""
    per_role_max = 3500
    total_max = 40000
    lines = [f"# Multi-agent result: {task[:120]}", ""]
    for a in assignments:
        status = "✓" if a.ok else "✗"
        skills = ", ".join(a.skills) if a.skills else "—"
        lines.append(
            f"## [{a.role}] {status}  ·  {a.provider}/{a.model} (tier={a.tier})  ·  skills: {skills}"
        )
        if a.error and not a.ok:
            lines.append(f"**Error:** {a.error.strip()}")
        if a.files_touched:
            shown = ", ".join(a.files_touched[:12])
            suffix = f" (+{len(a.files_touched) - 12} more)" if len(a.files_touched) > 12 else ""
            lines.append(f"**Files:** {shown}{suffix}")
        lines.append("")
        body = (a.content or "").strip() or "(no output)"
        cap = per_role_max if a.ok else per_role_max + 1500
        if len(body) > cap:
            body = body[:cap] + "\n...(truncated)"
        lines.append(body)
        lines.append("\n---\n")
    report = "\n".join(lines).strip()
    if len(report) > total_max:
        report = report[:total_max] + "\n...(report truncated)"
    return report
