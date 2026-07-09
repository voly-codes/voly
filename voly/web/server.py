"""VOLY FastAPI server — creates app and wires routers."""

from __future__ import annotations

import logging
import os
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voly.config import VOLYConfig

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

_STATIC = pathlib.Path(__file__).parent / "static"
_log = logging.getLogger("voly.web")

# Sensible defaults when auth is on and cors_origins still ["*"].
_LOCAL_CORS_ORIGINS = [
    "http://localhost:7788",
    "http://127.0.0.1:7788",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


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
        pathlib.Path.cwd() / ".voly" / "events",
        pathlib.Path.home() / ".voly" / "events",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


_load_dotenv_once()


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("voly.executor").setLevel(logging.DEBUG)


def _resolve_cors_origins(config: "VOLYConfig | None") -> list[str]:
    if config is None:
        return ["*"]
    origins = list(getattr(config.auth, "cors_origins", None) or ["*"])
    auth_on = bool(config.auth.enabled and config.auth.jwt_secret)
    if auth_on and origins == ["*"]:
        _log.warning(
            "auth is enabled with cors_origins=['*'] — "
            "restricting to localhost defaults; set auth.cors_origins explicitly for remote UI"
        )
        return list(_LOCAL_CORS_ORIGINS)
    return origins


def create_app(
    events_dir: pathlib.Path | None = None,
    config: "VOLYConfig | None" = None,
) -> "FastAPI":
    if not HAS_FASTAPI:
        raise ImportError("Install UI dependencies: pip install 'voly[ui]'")
    _configure_logging()

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles

    from voly.web.auth.middleware import JWTAuthMiddleware
    from voly.web.deps import AppState
    from voly.web.routes import auth, cf, dspy, marketplace, registry, run, tasks, gateway, telemetry

    app = FastAPI(title="VOLY UI", version="0.1.0", docs_url="/api/docs")

    cors_origins = _resolve_cors_origins(config)
    # Middleware is LIFO (last added = outermost). CORS must wrap JWT so that
    # preflight OPTIONS and 401 responses get Access-Control-* headers.
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.app = AppState(
        ev_dir=events_dir or _resolve_events_dir(),
        config=config,
    )

    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(run.router)
    app.include_router(registry.router)
    app.include_router(marketplace.router)
    app.include_router(cf.router)
    app.include_router(dspy.router)
    app.include_router(gateway.router)
    app.include_router(telemetry.router)

    auth_cfg = getattr(config, "auth", None) if config is not None else None
    if auth_cfg is None or not auth_cfg.enabled:
        _log.warning(
            "Web UI auth is DISABLED — API (including POST /api/run) is open. "
            "Use only on localhost. Enable with auth.enabled + VOLY_JWT_SECRET "
            "(see docs/backend/api.md)."
        )
    elif not auth_cfg.jwt_secret:
        _log.error(
            "auth.enabled=true but jwt_secret is empty — middleware will not enforce tokens. "
            "Set auth.jwt_secret or VOLY_JWT_SECRET."
        )
    else:
        _log.info(
            "Web UI JWT auth enabled (users=%d, cors=%s)",
            len(auth_cfg.users),
            cors_origins,
        )

    if _STATIC.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")

    return app


# Entry point for uvicorn --reload: voly ui --reload
_dev_app = create_app()
