"""
Pipeline HTTP server — exposes CodeOps pipeline to CF agent workers.

Secrets (API keys) and git repo stay on this host.
Expose via cloudflared tunnel: cloudflared tunnel --url http://127.0.0.1:9202
Then set PIPELINE_RUNNER_URL on the codeops-agent worker secret.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from codeops.config import CodeOpsConfig

logger = logging.getLogger(__name__)


def _authorized(headers: dict[str, str], token: str) -> bool:
    if not token:
        return True
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() == token
    return False


def _is_nested_a2a_request(body: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Detect A2A subtask runs that must not re-enter auto-dispatch."""
    a2a_parent = str(body.get("a2a_parent_task_id", "")).strip()
    task_id = str(body.get("task_id", "")).strip()
    nested = (
        bool(a2a_parent)
        or bool(task_id)
        or os.environ.get("CODEOPS_A2A_NESTED") == "1"
    )
    context: dict[str, Any] = {}
    if a2a_parent:
        context["a2a_parent_task_id"] = a2a_parent
    elif task_id:
        context["a2a_parent_task_id"] = task_id
    return nested, context


def create_pipeline_handler(config: CodeOpsConfig, token: str = "", default_cwd: str = ""):
    class PipelineHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _json_response(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/health":
                self._json_response(200, {"status": "ok", "service": "codeops-pipeline"})
                return
            self._json_response(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not _authorized(dict(self.headers.items()), token):
                self._json_response(401, {"error": "unauthorized"})
                return

            path = urlparse(self.path).path
            if path != "/run":
                self._json_response(404, {"error": "not found"})
                return

            body = self._read_json()
            task = str(body.get("task", "")).strip()
            agent = str(body.get("agent", config.default_agent)).strip()
            cwd = str(body.get("cwd") or default_cwd or os.getcwd()).strip()
            task_id = str(body.get("task_id", ""))

            if not task:
                self._json_response(400, {"error": "task required"})
                return

            nested, context = _is_nested_a2a_request(body)
            prev_nested = os.environ.get("CODEOPS_A2A_NESTED")
            if nested:
                os.environ["CODEOPS_A2A_NESTED"] = "1"

            from codeops.pipeline import Pipeline

            pipeline = Pipeline(config)
            if cwd:
                os.chdir(cwd)
            try:
                pipeline.setup_environment()
                result = pipeline.run(
                    task,
                    force_agent=agent,
                    delegate_to_a2a=False,
                    context=context or None,
                )
                payload = {
                    "success": result.success,
                    "response": result.response.content if result.response else "",
                    "error": result.error,
                    "agent": agent,
                    "task_id": task_id,
                    "duration_ms": result.duration_ms,
                }
                self._json_response(200 if result.success else 500, payload)
            except Exception as exc:
                self._json_response(500, {"success": False, "error": str(exc), "agent": agent})
            finally:
                pipeline.shutdown()
                if nested:
                    if prev_nested is None:
                        os.environ.pop("CODEOPS_A2A_NESTED", None)
                    else:
                        os.environ["CODEOPS_A2A_NESTED"] = prev_nested

        def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
            pass

    return PipelineHandler


def run_pipeline_server(
    config: CodeOpsConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 9202,
    token: str = "",
    default_cwd: str = "",
    block: bool = True,
) -> ThreadingHTTPServer:
    token = token or os.environ.get("PIPELINE_RUNNER_TOKEN", "").strip()
    handler = create_pipeline_handler(config, token=token, default_cwd=default_cwd)
    server = ThreadingHTTPServer((host, port), handler)
    logger.info("Pipeline server listening on http://%s:%s", host, port)

    if block:
        server.serve_forever()
    else:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    return server
