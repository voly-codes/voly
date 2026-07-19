"""Routes: /api/run (SSE stream) + pipeline/executor runner helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from voly.executor.base import executor_failure_details
from voly.correlation import ensure_correlation_id, get_correlation_id

router = APIRouter()
# Executor calls are blocking (subprocess.run) but I/O-bound, not CPU-bound —
# a small fixed pool queued concurrent /api/run requests invisibly behind
# whatever was already running. VOLY_RUN_POOL_WORKERS lets deployments size
# it to their concurrency needs.
_THREAD_POOL = ThreadPoolExecutor(
    max_workers=int(os.environ.get("VOLY_RUN_POOL_WORKERS", "16"))
)
# How often to send an SSE heartbeat while waiting on the blocking call —
# keeps proxies/browsers from idling out the connection during a long queue
# wait or a long-running executor, same pattern as /api/tasks/stream.
_RUN_HEARTBEAT_SECONDS = 15
_log = logging.getLogger("voly.web.run")

# Code extensions to search when gathering context
_CODE_EXTS = ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.go", "*.rs", "*.cs", "*.java")

# Common English/Russian stop-words to skip during keyword extraction
_STOP_WORDS = frozenset({
    "the", "for", "and", "this", "that", "with", "from", "have", "будет", "нужно",
    "надо", "чтобы", "тебе", "тест", "создай", "напиши", "добавь", "сделай",
    "test", "add", "create", "make", "write", "function", "class", "file",
    "import", "return", "async", "await", "true", "false", "none",
})


class RunRequest(BaseModel):
    task: str
    agent: str = ""
    model: str = ""
    executor: str = "pipeline"
    cwd: str = ""
    max_turns: int = 30
    # Total executor deadline in seconds, incl. internal model-fallback loops.
    timeout: int = 300
    a2a_delegate: bool = False
    # Run the executor but roll back all file changes afterwards; the diff
    # preview lands in result metadata (executor safety policy).
    dry_run: bool = False
    # User-confirmed tech stack from TechSelectionModal.
    # Each entry: {name, label, version, category, notes?}
    tech_stack: list[dict] = []


class TechDetectRequest(BaseModel):
    task: str
    cwd: str = ""


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


# ── Local context gathering ───────────────────────────────────────────────────

def _gather_local_context(task: str, cwd: str, max_chars: int = 6000) -> str:
    """Find and read local files relevant to the task. Returns a compact context block."""
    cwd = os.path.expanduser(cwd)
    if not os.path.isdir(cwd):
        return ""

    # Extract identifiers: camelCase, snake_case, PascalCase — min 4 chars
    tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', task)
    keywords = [t for t in dict.fromkeys(tokens) if t.lower() not in _STOP_WORDS][:8]

    if not keywords:
        return ""

    _EXCLUDE_DIRS = ("node_modules", ".venv", "venv", "__pycache__", ".git",
                     "dist", "build", ".next", "target", ".pytest_cache")

    # Score files by how many keywords they contain
    file_scores: dict[str, int] = {}
    for kw in keywords[:5]:
        try:
            cmd = [
                "grep", "-rl",
                *[f"--include={e}" for e in _CODE_EXTS],
                *[f"--exclude-dir={d}" for d in _EXCLUDE_DIRS],
                kw, ".",
            ]
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=5)
            for path in result.stdout.strip().splitlines():
                file_scores[path] = file_scores.get(path, 0) + 1
        except Exception:
            pass

    # Top-5 most relevant files
    top_files = sorted(file_scores, key=lambda p: -file_scores[p])[:5]
    if not top_files:
        return ""

    parts: list[str] = ["## Relevant local files\n"]
    total = 0
    for rel_path in top_files:
        full_path = os.path.join(cwd, rel_path)
        try:
            content = open(full_path, encoding="utf-8", errors="replace").read()
            # Show only lines that contain a keyword (with ±3 lines context)
            snippet = _extract_relevant_lines(content, keywords, max_lines=60)
            entry = f"### {rel_path}\n```\n{snippet}\n```\n\n"
            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)
        except Exception:
            pass

    return "".join(parts) if len(parts) > 1 else ""


def _extract_relevant_lines(content: str, keywords: list[str], max_lines: int = 60) -> str:
    """Return lines containing any keyword with a small window around them."""
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content

    hit_indices: set[int] = set()
    pat = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    for i, line in enumerate(lines):
        if pat.search(line):
            for j in range(max(0, i - 2), min(len(lines), i + 4)):
                hit_indices.add(j)

    if not hit_indices:
        return "\n".join(lines[:max_lines])

    selected = sorted(hit_indices)[:max_lines]
    result: list[str] = []
    prev = -1
    for idx in selected:
        if prev >= 0 and idx > prev + 1:
            result.append("...")
        result.append(lines[idx])
        prev = idx
    return "\n".join(result)


# ── Run helpers ───────────────────────────────────────────────────────────────

def _pipeline_run(req: RunRequest, config: Any) -> dict[str, Any]:
    from voly.pipeline import Pipeline
    from voly.catalog.tech_registry import tech_stack_context

    cfg = config
    if cfg is None:
        from voly.config import load_config
        cfg = load_config()

    pipeline = Pipeline(cfg)
    pipeline.setup_environment()
    run_cwd = os.path.expanduser(req.cwd) if req.cwd else ""
    context: dict[str, Any] = {}
    if run_cwd:
        context["cwd"] = run_cwd

    task = req.task
    if req.tech_stack:
        ctx_block = tech_stack_context(req.tech_stack)
        task = f"{ctx_block}\n\n{task}"
        context["tech_stack"] = req.tech_stack

    try:
        result = pipeline.run(
            task,
            context=context or None,
            force_model=req.model or None,
            force_agent=req.agent or None,
            delegate_to_a2a=req.a2a_delegate,
        )
    finally:
        pipeline.shutdown()

    out: dict[str, Any] = {
        "success": result.success,
        "stage": result.stage.value,
        "duration_ms": result.duration_ms,
        "error": result.error,
        "injected_skills": result.injected_skills,
        "skill_suggestions": result.skill_suggestions,
        "tokens_saved_by_rtk": result.tokens_saved_by_rtk,
        "tokens_saved_by_headroom": result.tokens_saved_by_headroom,
        "dspy_used": result.dspy_used,
        "dspy_mode": result.dspy_mode,
        "tech_stack": req.tech_stack or [],
    }
    if result.route:
        out["agent"] = result.route.agent
        out["model"] = result.route.model
        out["provider"] = result.route.provider
    if result.response:
        out["content"] = result.response.content
        out["usage"] = {
            "input_tokens": result.response.usage.input_tokens,
            "output_tokens": result.response.usage.output_tokens,
        }
    if result.a2a_tasks:
        out["a2a_tasks"] = [
            {"id": t.id, "state": t.state.value, "agent": t.metadata.get("routed_to", "")}
            for t in result.a2a_tasks
        ]
    ev = result.event
    if ev is not None and getattr(ev, "a2a_dispatched", False):
        out["a2a_dispatched"] = True
        out["a2a_agents_used"] = ev.a2a_agents_used
        out["a2a_assignments"] = ev.a2a_assignments
        assigns = ev.a2a_assignments or []
        exec_n = sum(1 for a in assigns if (a or {}).get("mode") == "executor")
        chat_n = sum(1 for a in assigns if (a or {}).get("mode") == "chat")
        out["hybrid"] = {
            "cwd": run_cwd or getattr(cfg, "default_cwd", "") or "",
            "executor_roles": exec_n,
            "chat_roles": chat_n,
            "files_touched": sorted({
                f
                for a in assigns
                for f in ((a or {}).get("files_touched") or [])
                if f
            }),
        }
    return out


def _executor_run(req: RunRequest, config: Any) -> dict[str, Any]:
    from voly.runner.agent_runner import AgentRunner

    cfg = config
    if cfg is None:
        from voly.config import load_config
        cfg = load_config()

    from voly.catalog.tech_registry import tech_stack_context

    work_dir = os.path.expanduser(req.cwd) if req.cwd else os.getcwd()

    # Enrich task with local context for code tasks
    task = req.task
    if req.tech_stack:
        ctx_block = tech_stack_context(req.tech_stack)
        task = f"{ctx_block}\n\n{task}"

    if req.cwd and req.executor not in ("pipeline",):
        ctx = _gather_local_context(req.task, work_dir)
        if ctx:
            task = f"{req.task}\n\n{ctx}"
            _log.info("context gathered: %d chars added to task", len(ctx))

    runner = AgentRunner(cfg)
    result = runner.run(
        task, req.executor, cwd=work_dir,
        max_turns=req.max_turns, timeout=req.timeout, model=req.model or "",
        dry_run=req.dry_run,
        correlation_id=get_correlation_id() or "",
    )
    meta = result.result.metadata or {}
    out = {
        "success": result.success,
        "executor": result.executor,
        "agent": result.agent,
        "task_id": result.task_id,
        "content": result.result.output or "",
        "error": result.result.error or "",
        "cost_usd": result.result.cost_usd,
        "duration_ms": result.result.duration_ms,
        "num_turns": result.result.num_turns,
        "automation_score": result.automation_score,
        "billing_fallback": meta.get("billing_fallback_to"),
        "chain_timelog": meta.get("chain_timelog"),
        "artifacts": meta.get("artifacts") or [],
    }
    out["tech_stack"] = req.tech_stack or []
    if not result.success:
        out.update(executor_failure_details(result.result, executor_name=result.executor))
    # Executor safety policy artifacts (dry-run preview / rollback details).
    for key in ("dry_run", "dry_run_diff", "safety_violation", "safety_rolled_back"):
        if meta.get(key):
            out[key] = meta[key]
    # WorkReport → run report screen (files changed/created/deleted, summary).
    rep = result.result.report
    if rep is not None:
        out["report"] = rep.to_dict() if hasattr(rep, "to_dict") else rep
    return out


def _needs_executor(task: str, config: Any) -> bool:
    """True when the task requires actual file operations (code gen/edit/fix)."""
    from voly.router import AgentRouter
    router = AgentRouter(config)
    analysis = router.analyze_task(task)
    return analysis.requires_code_gen


def _would_dispatch_a2a(task: str, config: Any) -> bool:
    """True when the pipeline would auto-dispatch this task to the multi-agent path.

    Complex, multi-capability tasks stay in the pipeline (lead orchestrator + sub-agents)
    instead of being promoted to the single-executor claude-code path.
    """
    if config is None:  # --factory mode injects no config → load defaults
        from voly.config import load_config
        config = load_config()
    a2a = getattr(config, "a2a", None)
    if not a2a or not getattr(a2a, "enabled", False) or not getattr(a2a, "auto_dispatch", True):
        return False
    from voly.router import AgentRouter
    analysis = AgentRouter(config).analyze_task(task)
    flags = sum([
        bool(analysis.requires_code_gen),
        bool(analysis.requires_review),
        bool(analysis.requires_testing),
        bool(analysis.requires_deployment),
    ])
    min_flags = getattr(a2a, "min_flags_for_dispatch", 2)
    return flags >= min_flags or getattr(analysis, "complexity", "") == "high"


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/api/run")
async def run_task(req: RunRequest, request: Request) -> StreamingResponse:
    config = request.app.state.app.config

    async def generate():
        loop = asyncio.get_event_loop()

        # Smart dispatch: pipeline + code task → promote to file-writing executor
        # so the billing fallback chain can kick in; complex tasks stay multi-agent.
        effective_req = req
        start_payload: dict[str, Any] = {
            "task": req.task,
            "executor": req.executor,
            "cwd": req.cwd or "",
            "correlation_id": ensure_correlation_id(),
        }
        if req.executor == "pipeline":
            effective_cwd = (
                req.cwd
                or getattr(config, "default_cwd", "")
                or os.environ.get("VOLY_PROJECT_CWD", "")
                or ""
            )
            try:
                multiagent = await loop.run_in_executor(
                    _THREAD_POOL, _would_dispatch_a2a, req.task, config
                )
                needs_exec = await loop.run_in_executor(
                    _THREAD_POOL, _needs_executor, req.task, config
                )
                if multiagent:
                    if effective_cwd and not req.cwd:
                        effective_req = req.model_copy(update={"cwd": effective_cwd})
                    a2a_cfg = getattr(config, "a2a", None) if config is not None else None
                    cwd_eff = (effective_req.cwd or effective_cwd or "").strip()
                    hybrid_on = bool(getattr(a2a_cfg, "hybrid_code_gen", True)) and bool(cwd_eff)
                    _log.info(
                        "[DISPATCH] pipeline → multi-agent (A2A local)  task=%r  "
                        "hybrid=%s cwd=%r reason=complex_multi_capability",
                        req.task[:60], hybrid_on, cwd_eff[:80] or "(empty)",
                    )
                    start_payload = {
                        "task": effective_req.task,
                        "executor": "pipeline",
                        "a2a": True,
                        "hybrid": hybrid_on,
                        "cwd": cwd_eff,
                    }
                    if bool(getattr(a2a_cfg, "hybrid_code_gen", True)) and not cwd_eff:
                        start_payload["hybrid_warning"] = "hybrid_skipped_no_cwd"
                elif needs_exec:
                    effective_req = req.model_copy(update={
                        "executor": "claude-code",
                        "cwd": effective_cwd,
                    })
                    _log.info(
                        "[DISPATCH] pipeline → claude-code  task=%r  cwd=%r  "
                        "(set VOLY_PROJECT_CWD or cwd field to target project)",
                        req.task[:60], effective_cwd or "(empty — will use server cwd)",
                    )
                    start_payload = {
                        "task": effective_req.task,
                        "executor": "claude-code",
                        "cwd": effective_cwd,
                    }
                else:
                    _log.info(
                        "[DISPATCH] pipeline (text-only)  task=%r  reason=no_code_gen_needed",
                        req.task[:60],
                    )
                    start_payload = {
                        "task": effective_req.task,
                        "executor": "pipeline",
                        "cwd": effective_cwd,
                    }
            except Exception as exc:
                _log.debug("[DISPATCH] auto-promote check failed: %s", exc)

        start_payload["correlation_id"] = ensure_correlation_id()
        yield _sse("start", start_payload)
        try:
            fn = _pipeline_run if effective_req.executor == "pipeline" else _executor_run
            future = loop.run_in_executor(_THREAD_POOL, fn, effective_req, config)
            while True:
                done, _pending = await asyncio.wait({future}, timeout=_RUN_HEARTBEAT_SECONDS)
                if future in done:
                    result = future.result()
                    if isinstance(result, dict):
                        result = {
                            **result,
                            "correlation_id": ensure_correlation_id(),
                        }
                    yield _sse("done", result)
                    break
                if await request.is_disconnected():
                    # Python can't force-cancel a blocking subprocess.run() in
                    # the thread pool, so the underlying call still runs to
                    # completion in the background — but there's no client
                    # left to stream to, so stop here instead of holding the
                    # connection (and this generator) open indefinitely.
                    _log.info("[RUN] client disconnected, abandoning SSE stream")
                    return
                yield _sse("heartbeat", {})
        except Exception as exc:
            yield _sse("error", {"error": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/tech/detect")
async def detect_tech(req: TechDetectRequest) -> dict:
    """Detect the tech stack implied by a task description.

    Returns a list of framework/library entries with version choices the user
    can confirm or override in the UI before the run starts.
    """
    from voly.catalog.tech_registry import detect_tech_from_task
    detected = detect_tech_from_task(req.task)
    return {"detected": detected}


@router.get("/api/tech/registry")
async def get_tech_registry() -> dict:
    """Return the full tech registry with all frameworks and current versions."""
    from voly.catalog.tech_registry import get_registry
    return {"registry": get_registry()}
