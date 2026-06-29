"""CodeOps FastAPI server — serves REST API + built Svelte UI."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import pathlib
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from codeops.config import CodeOpsConfig

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

_STATIC = pathlib.Path(__file__).parent / "static"
_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def create_app(
    events_dir: pathlib.Path | None = None,
    config: "CodeOpsConfig | None" = None,
) -> "FastAPI":
    if not HAS_FASTAPI:
        raise ImportError("Install UI dependencies: pip install 'codeops[ui]'")

    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel

    app = FastAPI(title="CodeOps UI", version="0.1.0", docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ev_dir = events_dir or _resolve_events_dir()
    _cfg = config

    # ------------------------------------------------------------------ #
    # Pydantic models
    # ------------------------------------------------------------------ #

    class RunRequest(BaseModel):
        task: str
        agent: str = ""
        model: str = ""
        executor: str = "pipeline"  # pipeline | cursor | claude-code | opencode | ...
        cwd: str = ""
        max_turns: int = 30

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _load_events() -> list[dict[str, Any]]:
        if not ev_dir.exists():
            return []
        out = []
        for f in ev_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                d["_mtime"] = f.stat().st_mtime
                out.append(d)
            except Exception:
                pass
        return sorted(out, key=lambda x: x.get("_mtime", 0), reverse=True)

    def _sse(event_type: str, data: Any) -> str:
        return f"data: {json.dumps({'type': event_type, **data})}\n\n"

    def _do_pipeline_run(req: RunRequest) -> dict[str, Any]:
        from codeops.pipeline import Pipeline

        cfg = _cfg
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

    def _do_executor_run(req: RunRequest) -> dict[str, Any]:
        from codeops.runner.agent_runner import AgentRunner

        cfg = _cfg
        if cfg is None:
            from codeops.config import load_config
            cfg = load_config()

        runner = AgentRunner(cfg)
        work_dir = req.cwd or os.getcwd()
        result = runner.run(req.task, req.executor, cwd=work_dir, max_turns=req.max_turns)
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

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        events = list(ev_dir.glob("*.json")) if ev_dir.exists() else []
        cfg_info: dict[str, Any] = {}
        if _cfg:
            cfg_info["marketplace_url"] = bool(getattr(getattr(_cfg, "registry", None), "marketplace_url", ""))
            cfg_info["spend_url"] = bool(getattr(getattr(_cfg, "spend", None), "remote_url", ""))
        return {
            "version": "0.1.0",
            "tasks_count": len(events),
            "events_dir": str(ev_dir),
            "cf": cfg_info,
        }

    @app.get("/api/tasks")
    def list_tasks(limit: int = 100, agent: str = "", status: str = "") -> list[dict[str, Any]]:
        tasks = _load_events()
        if agent:
            tasks = [t for t in tasks if t.get("agent") == agent]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks[:limit]

    @app.get("/api/tasks/stats/summary")
    def get_summary() -> dict[str, Any]:
        tasks = _load_events()
        if not tasks:
            return {
                "total_tasks": 0, "total_cost_usd": 0,
                "total_input_tokens": 0, "total_output_tokens": 0,
                "total_saved_tokens": 0, "avg_duration_ms": 0,
                "by_agent": {}, "by_status": {}, "by_model": {},
            }
        total_cost = 0.0
        total_in = total_out = total_saved = 0
        durations: list[float] = []
        by_agent: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_model: dict[str, int] = {}

        for t in tasks:
            total_cost += t.get("cost_usd") or 0
            tok = t.get("tokens") or {}
            total_in += tok.get("input") or 0
            total_out += tok.get("output") or 0
            total_saved += (tok.get("saved_rtk") or 0) + (tok.get("saved_headroom") or 0)
            if d := t.get("duration_ms"):
                durations.append(d)
            by_agent[(t.get("agent") or "unknown")] = by_agent.get(t.get("agent") or "unknown", 0) + 1
            by_status[(t.get("status") or "unknown")] = by_status.get(t.get("status") or "unknown", 0) + 1
            by_model[(t.get("model") or "unknown")] = by_model.get(t.get("model") or "unknown", 0) + 1

        return {
            "total_tasks": len(tasks),
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_saved_tokens": total_saved,
            "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0,
            "by_agent": by_agent,
            "by_status": by_status,
            "by_model": by_model,
        }

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        path = ev_dir / f"{task_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Task not found")
        return json.loads(path.read_text())

    # ------------------------------------------------------------------ #
    # Run endpoint (SSE stream)
    # ------------------------------------------------------------------ #

    @app.post("/api/run")
    async def run_task(req: RunRequest) -> StreamingResponse:
        async def generate():
            loop = asyncio.get_event_loop()
            yield _sse("start", {"task": req.task, "executor": req.executor})

            try:
                if req.executor == "pipeline":
                    result = await loop.run_in_executor(
                        _THREAD_POOL, _do_pipeline_run, req
                    )
                else:
                    result = await loop.run_in_executor(
                        _THREAD_POOL, _do_executor_run, req
                    )
                yield _sse("done", result)
            except Exception as exc:
                yield _sse("error", {"error": str(exc)})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------------------ #
    # Registry (local agents + skills)
    # ------------------------------------------------------------------ #

    @app.get("/api/registry/agents")
    def registry_agents() -> list[dict[str, Any]]:
        try:
            from codeops.registry.agents import AgentRegistry
            reg = AgentRegistry()
            return [a.to_dict() for a in reg.list_agents()]
        except Exception as exc:
            return [{"error": str(exc)}]

    @app.get("/api/registry/skills")
    def registry_skills(source: str = "", status: str = "active") -> list[dict[str, Any]]:
        try:
            from codeops.registry.skills import SkillRegistry
            reg = SkillRegistry()
            skills = reg.search(source=source or None, status=status or None)
            return [s.to_dict() for s in skills]
        except Exception as exc:
            return [{"error": str(exc)}]

    # ------------------------------------------------------------------ #
    # CF Marketplace
    # ------------------------------------------------------------------ #

    def _marketplace_url() -> str:
        if _cfg and getattr(getattr(_cfg, "registry", None), "marketplace_url", ""):
            return _cfg.registry.marketplace_url
        for key in ("CF_WORKER_MARKETPLACE_URL", "MARKETPLACE_URL"):
            u = os.environ.get(key, "").strip()
            if u:
                return u
        return ""

    @app.get("/api/marketplace/skills")
    def marketplace_skills(
        page: int = 1, limit: int = 24, agent: str = "", source: str = ""
    ) -> dict[str, Any]:
        url = _marketplace_url()
        if not url:
            return {"skills": [], "total": 0, "configured": False,
                    "hint": "Set CF_WORKER_MARKETPLACE_URL to enable"}
        try:
            from codeops.registry.marketplace import MarketplaceClient
            client = MarketplaceClient(url)
            result = client.list_skills(
                page=page, limit=limit,
                agent=agent or None, source=source or None,
            )
            result["configured"] = True
            return result
        except Exception as exc:
            return {"skills": [], "total": 0, "configured": True, "error": str(exc)}

    @app.get("/api/marketplace/skills/search")
    def marketplace_search(q: str = "", limit: int = 20) -> dict[str, Any]:
        url = _marketplace_url()
        if not url or not q:
            return {"skills": [], "total": 0, "configured": bool(url)}
        try:
            from codeops.registry.marketplace import MarketplaceClient
            result = MarketplaceClient(url).search(q, limit=limit)
            result["configured"] = True
            return result
        except Exception as exc:
            return {"skills": [], "total": 0, "configured": True, "error": str(exc)}

    @app.post("/api/marketplace/skills/{skill_id}/install")
    def marketplace_install(skill_id: str) -> dict[str, Any]:
        url = _marketplace_url()
        if not url:
            raise HTTPException(status_code=503, detail="Marketplace not configured")
        try:
            from codeops.registry.marketplace import MarketplaceClient
            skill_data = MarketplaceClient(url).download_skill(skill_id)
            # Persist to local skills dir
            skills_dir = ev_dir.parent / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
            safe = skill_id.replace("/", "_").replace("..", "")
            (skills_dir / f"{safe}.json").write_text(
                json.dumps(skill_data, ensure_ascii=False, indent=2)
            )
            return {"installed": True, "skill_id": skill_id}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ------------------------------------------------------------------ #
    # CF Spend + Workers status
    # ------------------------------------------------------------------ #

    def _spend_url() -> str:
        if _cfg and getattr(getattr(_cfg, "spend", None), "remote_url", ""):
            raw = _cfg.spend.remote_url
            if "${" not in raw:
                return raw
        for key in ("CF_WORKER_SPEND_URL", "SPEND_URL"):
            u = os.environ.get(key, "").strip()
            if u:
                return u
        return ""

    @app.get("/api/cf/spend/summary")
    def cf_spend_summary(days: int = 7) -> dict[str, Any]:
        url = _spend_url()
        if not url:
            return {"configured": False, "hint": "Set CF_WORKER_SPEND_URL to enable",
                    "total": 0, "agents": []}
        try:
            from codeops.spend.client import SpendClient
            data = SpendClient(url).summary(days=days)
            data["configured"] = True
            return data
        except Exception as exc:
            return {"configured": True, "error": str(exc), "total": 0, "agents": []}

    @app.get("/api/cf/workers/status")
    def cf_workers_status() -> dict[str, Any]:
        workers = {
            "spend":       ("CF_WORKER_SPEND_URL",       _spend_url()),
            "marketplace": ("CF_WORKER_MARKETPLACE_URL", _marketplace_url()),
            "agui":        ("CF_WORKER_AGUI_URL",        os.environ.get("CF_WORKER_AGUI_URL", "")),
            "memory":      ("CF_WORKER_MEMORY_URL",      os.environ.get("CF_WORKER_MEMORY_URL", "")),
            "a2a":         ("CF_WORKER_A2A_URL",         os.environ.get("CF_WORKER_A2A_URL", "")),
            "workflow":    ("CF_WORKER_WORKFLOW_URL",    os.environ.get("CF_WORKER_WORKFLOW_URL", "")),
            "catalog":     ("CF_WORKER_CATALOG_URL",     os.environ.get("CF_WORKER_CATALOG_URL", "")),
            "telemetry":   ("CF_WORKER_TELEMETRY_URL",  os.environ.get("CF_WORKER_TELEMETRY_URL", "")),
        }
        result = {}
        for name, (env_key, url) in workers.items():
            result[name] = {"env_key": env_key, "url": url, "configured": bool(url)}
        return result

    # ------------------------------------------------------------------ #
    # Static files (must be last — catch-all)
    # ------------------------------------------------------------------ #

    if _STATIC.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")

    return app


def _resolve_events_dir() -> pathlib.Path:
    candidates = [
        pathlib.Path.cwd() / ".codeops" / "events",
        pathlib.Path.home() / ".codeops" / "events",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]
