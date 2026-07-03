"""Tunnel utilities — cloudflared quick tunnel + worker secret sync."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
DEFAULT_CLOUDFLARED_PATHS = (
    Path.home() / ".local/bin/cloudflared",
    Path("/usr/local/bin/cloudflared"),
    Path("/tmp/cloudflared"),
)


def find_cloudflared() -> Path | None:
    found = shutil.which("cloudflared")
    if found:
        return Path(found)
    for path in DEFAULT_CLOUDFLARED_PATHS:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def install_cloudflared(target: Path | None = None) -> Path:
    dest = target or (Path.home() / ".local/bin/cloudflared")
    dest.parent.mkdir(parents=True, exist_ok=True)

    arch = os.uname().machine
    suffix = "arm64" if arch in ("aarch64", "arm64") else "amd64"
    url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{suffix}"

    subprocess.run(["curl", "-fsSL", url, "-o", str(dest)], check=True)
    dest.chmod(0o755)
    return dest


def ensure_pipeline_token(env_path: Path) -> str:
    token = os.environ.get("PIPELINE_RUNNER_TOKEN", "").strip()
    if token:
        return token

    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("PIPELINE_RUNNER_TOKEN=") and line.split("=", 1)[1].strip():
                return line.split("=", 1)[1].strip()

    token = secrets.token_urlsafe(32)
    _upsert_env_var(env_path, "PIPELINE_RUNNER_TOKEN", token)
    os.environ["PIPELINE_RUNNER_TOKEN"] = token
    return token


def _upsert_env_var(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    found = False
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")


def update_env_pipeline_url(env_path: Path, url: str) -> None:
    _upsert_env_var(env_path, "PIPELINE_RUNNER_URL", url.rstrip("/"))
    os.environ["PIPELINE_RUNNER_URL"] = url.rstrip("/")


def wait_for_local_server(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://{host}:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.3)
    return False


def parse_tunnel_url(output: str) -> str | None:
    match = TUNNEL_URL_RE.search(output)
    return match.group(0) if match else None


def start_cloudflared_tunnel(
    cloudflared: Path,
    local_url: str,
    on_url: Callable[[str], None] | None = None,
    timeout: float = 45.0,
) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        [str(cloudflared), "tunnel", "--url", local_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    collected: list[str] = []
    deadline = time.time() + timeout
    tunnel_url: str | None = None

    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            collected.append(line)
            tunnel_url = parse_tunnel_url("".join(collected))
            if tunnel_url:
                if on_url:
                    on_url(tunnel_url)
                break

    if not tunnel_url:
        proc.terminate()
        raise RuntimeError(
            "cloudflared did not return a tunnel URL within timeout. "
            f"Output: {''.join(collected[-20:])}"
        )

    return proc


def sync_agent_worker_secrets(
    agent_worker_dir: Path,
    pipeline_url: str,
    pipeline_token: str,
    cloudflare_token: str = "",
) -> None:
    wrangler = agent_worker_dir / "node_modules/.bin/wrangler"
    if not wrangler.is_file():
        raise FileNotFoundError(f"wrangler not found at {wrangler}")

    env = os.environ.copy()
    if cloudflare_token:
        env["CLOUDFLARE_API_TOKEN"] = cloudflare_token

    for name, value in (
        ("PIPELINE_RUNNER_URL", pipeline_url.rstrip("/")),
        ("PIPELINE_RUNNER_TOKEN", pipeline_token),
    ):
        subprocess.run(
            [str(wrangler), "secret", "put", name],
            input=value,
            text=True,
            cwd=str(agent_worker_dir),
            env=env,
            check=True,
            capture_output=True,
        )


def run_pipeline_server_background(config: Any, host: str, port: int, cwd: str) -> threading.Thread:
    from voly.pipeline_server import run_pipeline_server

    thread = threading.Thread(
        target=lambda: run_pipeline_server(config, host=host, port=port, default_cwd=cwd, block=True),
        daemon=True,
        name="voly-pipeline-server",
    )
    thread.start()
    return thread
