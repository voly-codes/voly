"""Routes: /api/run (SSE stream) + pipeline/executor runner helpers."""

from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()
_THREAD_POOL = ThreadPoolExecutor(max_workers=4)


class RunRequest(BaseModel):
    task: str
    agent: str = ""
    model: str = ""
    executor: str = "pipeline"
    cwd: str = ""
    max_turns: int = 30


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


def _pipeline_run(req: RunRequest, config: Any) -> dict[str, Any]:
    from codeops.pipeline import Pipeline

    cfg = config
    if cfg is None:
        from codeops.config import load_config
        cfg = load_config()

    pipeline = Pipeline(cfg)
    pipeline.setup_environment()
    try:
        result = pipeline.run(
            req.task,
            force_model=req.model or None,
            force_agent=req.agent or None,
        )
    finally:
        pipeline.shutdown()

    out: dict[str, Any] = {
        "success": result.success,
        "stage": result.stage.value,
        "duration_ms": result.duration_ms,
        "error": result.error,
        "injected_skills": result.injected_skills,
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
    return out


def _executor_run(req: RunRequest, config: Any) -> dict[str, Any]:
    from codeops.runner.agent_runner import AgentRunner

    cfg = config
    if cfg is None:
        from codeops.config import load_config
        cfg = load_config()

    runner = AgentRunner(cfg)
    work_dir = req.cwd or os.getcwd()
    result = runner.run(req.task, req.executor, cwd=work_dir, max_turns=req.max_turns, model=req.model or "")
    return {
        "success": result.success,
        "executor": result.executor,
        "agent": result.agent,
        "task_id": result.task_id,
        "content": result.result.output or "",
        "error": result.result.error,
        "cost_usd": result.result.cost_usd,
        "duration_ms": result.result.duration_ms,
        "num_turns": result.result.num_turns,
        "automation_score": result.automation_score,
    }


@router.post("/api/run")
async def run_task(req: RunRequest, request: Request) -> StreamingResponse:
    config = request.app.state.app.config

    async def generate():
        loop = asyncio.get_event_loop()
        yield _sse("start", {"task": req.task, "executor": req.executor})
        try:
            if req.executor == "pipeline":
                result = await loop.run_in_executor(
                    _THREAD_POOL, _pipeline_run, req, config
                )
            else:
                result = await loop.run_in_executor(
                    _THREAD_POOL, _executor_run, req, config
                )
            yield _sse("done", result)
        except Exception as exc:
            yield _sse("error", {"error": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
