"""
Headroom Manager — управление прокси-сервером сжатия контекста.

Обеспечивает:
    - Запуск и остановку Headroom прокси
    - Конфигурацию прокси (порт, профиль сжатия, память)
    - Wrapping AI-агентов через прокси
    - Проверку здоровья прокси
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HeadroomStatus:
    running: bool
    port: int = 0
    pid: int = 0
    version: str = ""
    uptime_seconds: float = 0.0
    tokens_saved: int = 0
    active_connections: int = 0


class HeadroomManager:
    def __init__(
        self,
        port: int = 8787,
        savings_profile: str = "agent-90",
        memory_enabled: bool = False,
        code_graph: bool = False,
        backend: str | None = None,
    ):
        self.port = port
        self.savings_profile = savings_profile
        self.memory_enabled = memory_enabled
        self.code_graph = code_graph
        self.backend = backend
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
        if self.savings_profile:
            env["HEADROOM_SAVINGS_PROFILE"] = self.savings_profile
        if self.memory_enabled:
            env["HEADROOM_MEMORY"] = "1"
        if self.code_graph:
            env["HEADROOM_CODE_GRAPH"] = "1"
        if self.backend:
            env["HEADROOM_BACKEND"] = self.backend

        try:
            self._process = subprocess.Popen(
                [sys.executable, "-m", "headroom.cli", "proxy", "--port", str(self.port)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            try:
                self._process = subprocess.Popen(
                    ["headroom", "proxy", "--port", str(self.port)],
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

    def status(self) -> HeadroomStatus:
        if not self.is_running():
            return HeadroomStatus(running=False)

        try:
            import urllib.request
            req = urllib.request.Request(f"{self.proxy_url}/health")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode())
                return HeadroomStatus(
                    running=True,
                    port=self.port,
                    pid=self._process.pid if self._process else 0,
                    version=data.get("version", ""),
                    uptime_seconds=data.get("uptime", 0),
                    tokens_saved=data.get("tokens_saved", 0),
                    active_connections=data.get("active_connections", 0),
                )
        except Exception:
            return HeadroomStatus(running=True, port=self.port)

    def wrap_agent(self, agent: str, project_path: str | None = None) -> subprocess.Popen | None:
        try:
            cmd = ["headroom", "wrap", agent]
            if project_path:
                cmd.extend(["--project", project_path])

            return subprocess.Popen(cmd)
        except FileNotFoundError:
            return None

    def unwrap_agent(self, agent: str) -> bool:
        try:
            result = subprocess.run(
                ["headroom", "unwrap", agent],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def compress(
        self,
        messages: list[dict],
        model: str = "claude-sonnet-4-5-20250929",
    ) -> dict[str, Any]:
        try:
            import urllib.request

            body = json.dumps({"messages": messages, "model": model}).encode()
            req = urllib.request.Request(
                f"{self.proxy_url}/api/compress",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return {"messages": messages}

    def _wait_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_running():
                return True
            if self._process and self._process.poll() is not None:
                return False
            time.sleep(0.2)
        return self.is_running()
