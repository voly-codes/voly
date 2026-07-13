"""Manage the pxpipe token-saving proxy for Claude Code executor runs."""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger("voly.pxpipe")


@dataclass
class PxpipeStatus:
    running: bool
    port: int = 0
    pid: int = 0
    proxy_url: str = ""
    models: str = ""


class PxpipeManager:
    """Start/status wrapper for pxpipe's Node CLI.

    pxpipe accepts runtime configuration through env vars rather than CLI flags:
    `PORT`, `HOST`, `PXPIPE_MODELS`, and upstream provider variables.
    """

    def __init__(
        self,
        port: int = 47821,
        models: str = "claude-fable-5,gpt-5.6",
        dump_dir: str | Path | None = None,
    ):
        self.port = int(port)
        self.models = models
        self.dump_dir = Path(dump_dir) if dump_dir else None
        self._process: subprocess.Popen | None = None

    @property
    def proxy_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def is_running(self) -> bool:
        try:
            sock = socket.create_connection(("127.0.0.1", self.port), timeout=1.0)
            sock.close()
            return True
        except (socket.error, OSError):
            return False

    def start(self, wait: bool = True, timeout: float = 15.0) -> bool:
        if self.is_running():
            return True

        env = os.environ.copy()
        env["PORT"] = str(self.port)
        env.setdefault("HOST", "127.0.0.1")
        if self.models:
            env["PXPIPE_MODELS"] = self.models
        if self.dump_dir:
            self.dump_dir.mkdir(parents=True, exist_ok=True)
            env["PXPIPE_DUMP_DIR"] = str(self.dump_dir)

        cmd = self._command()
        if cmd is None:
            return False

        try:
            self._process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return False

        if wait:
            return self._wait_ready(timeout)
        return True

    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None

    def status(self) -> PxpipeStatus:
        running = self.is_running()
        return PxpipeStatus(
            running=running,
            port=self.port if running else 0,
            pid=self._process.pid if running and self._process else 0,
            proxy_url=self.proxy_url if running else "",
            models=self.models,
        )

    def _command(self) -> list[str] | None:
        if shutil.which("pxpipe"):
            return ["pxpipe"]
        if shutil.which("npx"):
            return ["npx", "--yes", "pxpipe-proxy"]
        return None

    def _wait_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_running():
                return True
            if self._process and self._process.poll() is not None:
                return False
            time.sleep(0.2)
        return self.is_running()


def apply_pxpipe_env(
    env: dict[str, str],
    *,
    config: Any | None = None,
    manager_cls: type[PxpipeManager] = PxpipeManager,
) -> dict[str, str]:
    """Return an executor env with pxpipe enabled when configured and reachable."""

    cfg = config if config is not None else _load_pxpipe_config()
    if cfg is None or not getattr(cfg, "enabled", False):
        return env

    port = int(getattr(cfg, "port", 47821))
    models = str(getattr(cfg, "models", "") or "")
    manager = manager_cls(port=port, models=models)

    running = manager.is_running()
    if not running and getattr(cfg, "auto_start", False):
        running = manager.start(wait=True)
    if not running:
        _log.warning("[PXPIPE] enabled but proxy is not running on port %s", port)
        return env

    next_env = env.copy()
    if models:
        next_env["PXPIPE_MODELS"] = models

    override = bool(getattr(cfg, "override_anthropic_base_url", False))
    if override or not next_env.get("ANTHROPIC_BASE_URL"):
        next_env["ANTHROPIC_BASE_URL"] = manager.proxy_url
        _log.info("[PXPIPE] routing Claude Code via %s", manager.proxy_url)
    else:
        _log.info("[PXPIPE] kept existing ANTHROPIC_BASE_URL; override disabled")

    return next_env


def _load_pxpipe_config() -> Any | None:
    try:
        from voly.config import load_config

        return load_config().pxpipe
    except Exception as exc:
        _log.debug("[PXPIPE] config load skipped: %s", exc)
        return None
