"""Role prepare / executor / chat helpers for local multi-agent runs."""
from __future__ import annotations

import logging
import time
from typing import Any

from voly.a2a.assignment import (
    Assignment,
    exclude_provider_on_gateway_error as _exclude_provider_on_gateway_error,
)
from voly.a2a.chat_fallback import chat_with_provider_fallback
from voly.a2a.context import (
    DEFAULT_PERSONA,
    ROLE_PROMPT,
    delta_for_role,
    git_diff_evidence,
    memory_block,
    project_context_block,
    skills_block,
)

_log = logging.getLogger("voly.a2a.multiagent")


class _RoleExecMixin:
    """Mixin: cascade/prompt prepare + executor/chat execution."""

    def prepare(self, a: Assignment) -> tuple[str, str, dict] | None:
        """Pre-flight: cascade/plan-gate + prompt build.

        Returns (user, system, git_before) when the role should execute, or
        None when it was finalized here (skipped/blocked).
        """
        from voly.a2a.decomposer import TaskDecomposer
        from voly.plan.bridge import assignment_step_id
        from voly.plan.types import RUNNING
        from voly.plan.verify import git_porcelain

        # Cascade policy when a required prior role failed:
        #   - executor roles need the implementation → hard skip
        #   - chat roles degrade gracefully IF at least one prior succeeded
        #     (e.g. reviewer/tester/devops run on the architect plan alone)
        #   - if ALL priors failed → hard skip regardless of mode
        if self.skip_dependents_on_failure and a.depends_on:
            failed_priors = [
                self.done[d].role for d in a.depends_on
                if d in self.done and not self.done[d].ok
            ]
            ok_priors = [
                self.done[d].role for d in a.depends_on
                if d in self.done and self.done[d].ok
            ]
            if failed_priors:
                role_mode = self.role_modes.get(a.idx, a.mode or "chat")
                # Early-exit for code_gen tasks: when all executor roles that have
                # completed produced no code, post-impl chat roles cannot act —
                # skip them. An executor that wrote files but failed soft safety
                # still counts as code produced (do not cascade-skip).
                impl_done = [
                    self.done[i] for i in self.done if self.done[i].mode == "executor"
                ]

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
                # Post-impl roles (chat or tester-executor) skip when no code exists.
                if self.requires_code_gen and ok_priors and all_impl_failed:
                    a.ok = False
                    a.error = (
                        f"skipped: no code produced — all executor roles failed "
                        f"({', '.join(d.role for d in impl_done if not d.ok)})"
                    )
                    a.content = f"({a.error})"
                    a.mode, a.mode_reason = role_mode, "skipped_no_code"
                    a.plan_status = "skipped"
                    self.done[a.idx] = a
                    self.heartbeat(a.role, len(self.done))
                    _log.info(
                        "multiagent[%d] %s early-exit: code_gen but no impl succeeded",
                        a.idx, a.role,
                    )
                    return None
                # Executor dependents (e.g. tester) may proceed when a prior wrote
                # files despite ok=False (soft safety). Chat still needs ≥1 ok prior.
                if role_mode == "executor":
                    usable_priors = [
                        self.done[d].role
                        for d in a.depends_on
                        if d in self.done and (
                            self.done[d].ok or _impl_has_code(self.done[d])
                        )
                    ]
                    hard_block = not usable_priors
                else:
                    hard_block = not ok_priors
                if hard_block:
                    a.ok = False
                    a.error = f"skipped: prior role(s) failed ({', '.join(failed_priors)})"
                    a.content = f"({a.error})"
                    a.mode, a.mode_reason = a.mode or "chat", "skipped_prior_failed"
                    a.plan_status = "skipped"
                    self.done[a.idx] = a
                    self.heartbeat(a.role, len(self.done))
                    return None
                self.degraded_notes[a.idx] = failed_priors
                a.mode_reason = (
                    f"{a.mode_reason}+degraded_prior_failed"
                    if a.mode_reason else "degraded_prior_failed"
                )
                _log.info(
                    "multiagent[%d] %s degraded: prior failed (%s), running on (%s)",
                    a.idx, a.role, ", ".join(failed_priors), ", ".join(ok_priors),
                )

        # Plan gate: only start when depends_on steps are verified.
        if self.plan is not None and self.engine is not None:
            sid = assignment_step_id(a.idx, a.role)
            if not self.engine.can_start(self.plan, sid):
                unmet = self.engine.unmet_deps(self.plan, sid)
                a.ok = False
                a.error = f"blocked: plan deps not verified ({unmet})"
                a.content = f"({a.error})"
                a.plan_status = "blocked"
                self.done[a.idx] = a
                self.heartbeat(a.role, len(self.done))
                return None
            self.engine.transition(self.plan, sid, RUNNING)
            a.plan_status = RUNNING
            if self.store is not None:
                self.store.save(self.plan)

        git_before = git_porcelain(self.cwd) if self.cwd else {}

        prior = [
            (
                self.done[d].role,
                self.done[d].content,
                list(self.done[d].files_touched or []),
            )
            for d in a.depends_on
            if d in self.done and self.done[d].ok
        ]
        user = TaskDecomposer.inject_prior_context(a.description, prior)
        # Reviewer/tester need real diffs — chat-only summaries cause hallucinations
        # ("no migration") when the developer already wrote the file.
        if a.role in ("reviewer", "tester") and self.cwd:
            evidence_files: list[str] = []
            for d in a.depends_on:
                prior_a = self.done.get(d)
                if prior_a is None:
                    continue
                evidence_files.extend(prior_a.files_touched or [])
            evidence = git_diff_evidence(self.cwd, evidence_files)
            if evidence:
                user = f"{user}\n\n{evidence}"

        if a.idx in self.degraded_notes:
            failed = ", ".join(self.degraded_notes[a.idx])
            user = (
                f"WARNING: previous roles did not complete ({failed}). "
                "Work from the available context (the architect's plan). "
                "Explicitly note in your reply that the implementation is missing or "
                "incomplete and which steps must be re-checked once it appears.\n\n"
                f"{user}"
            )

        mem_block, a.mem_hits = memory_block(self.memory, f"{a.role}: {a.description}")
        if mem_block:
            user = f"{mem_block}\n\n{user}"

        persona = ROLE_PROMPT.get(a.role, DEFAULT_PERSONA)
        skills = skills_block(a.skills, self.skill_matcher, self.task, a.role)
        system = f"{persona}\n\n{skills}".strip() if skills else persona
        # Inject project context for architect so it can give project-specific
        # answers rather than generic advice (P3: "неточный ответ architect").
        if a.role == "architect" and self.cwd:
            ctx = project_context_block(self.cwd)
            if ctx:
                system = f"{system}\n\n## Project context\n{ctx}".strip()
        return user, system, git_before

    def run_executor(self, a: Assignment, user: str, system: str, git_before: dict) -> None:
        """Executor role: run serially in the caller thread and finalize."""
        from voly.plan.verify import fingerprint_untracked, git_porcelain

        # Re-snapshot right before running — a same-wave executor may have
        # already changed the tree, and chat calls happened since prepare.
        fp_before: dict[str, str] = {}
        if self.cwd:
            git_before = git_porcelain(self.cwd)
            fp_before = fingerprint_untracked(self.cwd, git_before)
        _log.info(
            "multiagent[%d] %s → EXECUTOR %s (cwd=%s, reason=%s)",
            a.idx, a.role, a.executor, self.cwd or "(none)", a.mode_reason,
        )
        _t0 = time.monotonic()
        _wall0 = time.time()
        try:
            result = self.executor_runner(
                role=a.role,
                task=user,
                cwd=self.cwd,
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
            if self.cwd:
                delta = delta_for_role(
                    self.cwd, git_before, since=_wall0, fingerprints_before=fp_before,
                )
                if delta:
                    a.files_touched = delta
            self.finish_step_plan(a, exec_ok=False, git_before=git_before)
            self.done[a.idx] = a
            self.heartbeat(a.role, len(self.done))
            self._emit_role_evidence(a)
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
        if self.cwd and not a.files_touched:
            delta = delta_for_role(
                self.cwd, git_before, since=_wall0, fingerprints_before=fp_before,
            )
            if delta:
                a.files_touched = delta
        # Executor honesty: on a code-gen task a role that "succeeded" without
        # touching a single file only produced text — that is not an
        # implementation (e.g. cursor returning a plausible summary while the
        # bridge silently wrote nothing). Fail the role so downstream degrades
        # and the run reports partial instead of a false completed.
        if self.requires_code_gen and a.ok and not a.files_touched:
            a.ok = False
            a.error = (
                "executor reported success but changed no files "
                f"(executor={a.executor or 'unknown'})"
            )
            _log.warning(
                "multiagent[%d] %s executor success with zero files — marked failed",
                a.idx, a.role,
            )
        self.finish_step_plan(a, exec_ok=a.ok, git_before=git_before)
        self.done[a.idx] = a
        self.heartbeat(a.role, len(self.done))
        self._emit_role_evidence(a)

    def _emit_role_evidence(self, a: Assignment) -> None:
        try:
            from voly.a2a.core import emit_assignment_from_result

            emit_assignment_from_result(a)
        except Exception:  # noqa: BLE001
            pass

    def chat_call(self, a: Assignment, user: str, system: str) -> dict[str, Any]:
        """Gateway call only — the sole part that may run in a worker thread."""
        messages = [{"role": "user", "content": user}]
        if self.headroom is not None:
            try:
                if self.headroom.is_running():
                    res = self.headroom.compress(messages, model=a.model)
                    messages = res.get("messages", messages)
                    a.saved_tokens = int(res.get("tokens_saved", 0) or 0)
                else:
                    # Headroom proxy down — trim oversized user payloads locally
                    # so continuation roles still show token savings in telemetry.
                    content = messages[0].get("content") or ""
                    limit = 7000
                    if len(content) > limit:
                        saved = (len(content) - limit) // 4
                        messages[0]["content"] = content[:limit] + "\n...(trimmed)"
                        a.saved_tokens = max(0, saved)
            except Exception as e:  # noqa: BLE001
                _log.debug("headroom compress skipped: %s", e)

        _log.info(
            "multiagent[%d] %s → %s/%s (tier=%s, mode=%s, skills=%s, mem=%d)",
            a.idx, a.role, a.provider, a.model, a.tier, a.mode, a.skills, a.mem_hits,
        )
        role_max_tokens = (
            int(self.architect_max_tokens or self.max_tokens)
            if a.role == "architect"
            else self.max_tokens
        )
        _t0 = time.monotonic()
        try:
            return chat_with_provider_fallback(
                self.gateway,
                messages=messages,
                assignment=a,
                system=system,
                max_tokens=role_max_tokens,
                temperature=self.temperature,
            )
        except Exception as e:  # noqa: BLE001
            return {"__raised__": True, "error": str(e), "content": ""}
        finally:
            # Only this worker thread touches this assignment — safe mutation.
            a.duration_ms = (time.monotonic() - _t0) * 1000

    def finalize_chat(self, a: Assignment, resp: dict[str, Any], git_before: dict) -> bool:
        """Parse the response + memory/plan bookkeeping. True → spend-limited."""
        from voly.telemetry import _estimate_cost

        if resp.get("__raised__"):
            a.error = str(resp.get("error") or "")
            a.content = f"(failed: {a.error})"
            a.ok = False
            _exclude_provider_on_gateway_error(a.provider, a.error)
            self.finish_step_plan(a, exec_ok=False, git_before=git_before)
            self.done[a.idx] = a
            self.heartbeat(a.role, len(self.done))
            self._emit_role_evidence(a)
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
            a.ok = bool(a.content.strip()) if not self.gates_on else True
            if not a.content.strip():
                a.ok = False
                a.error = "empty response from provider"
            if a.content.strip() and self.memory is not None and not a.cache_hit:
                try:
                    self.memory.add(
                        title=f"[{a.role}] {a.description[:80]}",
                        content=a.content[:2000], category="history",
                        metadata={
                            "role": a.role, "model": a.model, "provider": a.provider,
                            "task": self.task[:200],
                        },
                        importance=0.5, tags=[a.role, "a2a"],
                    )
                except Exception as e:  # noqa: BLE001
                    _log.debug("memory store skipped for %s: %s", a.role, e)
        self.finish_step_plan(
            a, exec_ok=process_ok if self.gates_on else a.ok, git_before=git_before,
        )
        self.done[a.idx] = a
        self.heartbeat(a.role, len(self.done))
        self._emit_role_evidence(a)
        return bool(resp.get("spend_limited"))
