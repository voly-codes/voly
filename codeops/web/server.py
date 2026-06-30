"""CodeOps FastAPI server — creates app and wires routers."""

from __future__ import annotations

import os
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeops.config import CodeOpsConfig

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

_STATIC = pathlib.Path(__file__).parent / "static"


def _load_dotenv_once() -> None:
    """Load .env from repo root into os.environ (first-set wins, no deps)."""
    env_file = pathlib.Path(__file__).parent.parent.parent / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val


def _resolve_events_dir() -> pathlib.Path:
    candidates = [
        pathlib.Path.cwd() / ".codeops" / "events",
        pathlib.Path.home() / ".codeops" / "events",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


_load_dotenv_once()


def create_app(
    events_dir: pathlib.Path | None = None,
    config: "CodeOpsConfig | None" = None,
) -> "FastAPI":
    if not HAS_FASTAPI:
        raise ImportError("Install UI dependencies: pip install 'codeops[ui]'")

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles

    from codeops.web.deps import AppState
    from codeops.web.routes import cf, dspy, marketplace, registry, run, tasks, gateway, telemetry

    app = FastAPI(title="CodeOps UI", version="0.1.0", docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.app = AppState(
        ev_dir=events_dir or _resolve_events_dir(),
        config=config,
    )

    app.include_router(tasks.router)
    app.include_router(run.router)
    app.include_router(registry.router)
    app.include_router(marketplace.router)
    app.include_router(cf.router)
    app.include_router(dspy.router)
    app.include_router(gateway.router)
    app.include_router(telemetry.router)

    if _STATIC.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")

    return app


# Entry point for uvicorn --reload: codeops ui --reload
_dev_app = create_app()
