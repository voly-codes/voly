"""
CfContainersExecutor — PoC cloud-native executor via Cloudflare Containers.

Talks to the VOLY sandbox-spike Worker (or any compatible endpoint):

  GET  /health  → availability
  POST /runs    → run task inside a CF Container (Sandbox SDK)

Default modes:
  - probe        — smoke exec (uname/python) inside the container
  - claude-code  — run Claude Code inside the container (needs Worker secrets)

Env:
  VOLY_CF_CONTAINERS_URL   — default http://127.0.0.1:8791
  VOLY_CF_CONTAINERS_TOKEN — Bearer JWT (same secret as sandbox-spike JWT_SECRET)
  VOLY_CF_CONTAINERS_MODE  — probe | claude-code (default probe)

This is intentionally HTTP-only on the VOLY side: container lifecycle lives in
the Worker (see voly-cloud/cf-workers/sandbox-spike).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from voly.executor.base import Executor, ExecutorResult, _is_billing_error

_log = logging.getLogger("voly.executor.cf_containers")

_DEFAULT_URL = "http://127.0.0.1:8791"
_DEFAULT_MODE = "probe"
_VALID_MODES = frozenset({"probe", "claude-code"})


class CfContainersExecutor(Executor):
    """Run a task inside a Cloudflare Container via the sandbox-spike HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        mode: str | None = None,
        repo: str | None = None,
    ):
        self._base_url = (
            base_url or os.getenv("VOLY_CF_CONTAINERS_URL", _DEFAULT_URL)
        ).rstrip("/")
        self._token = token or os.getenv("VOLY_CF_CONTAINERS_TOKEN", "")
        raw_mode = (mode or os.getenv("VOLY_CF_CONTAINERS_MODE", _DEFAULT_MODE)).lower()
        self._mode = raw_mode if raw_mode in _VALID_MODES else _DEFAULT_MODE
        self._repo = repo or os.getenv("VOLY_CF_CONTAINERS_REPO", "") or None

    @property
    def name(self) -> str:
        return "cf-containers"

    def is_available(self) -> bool:
        """True when the Containers Worker answers GET /health."""
        try:
            req = urllib.request.Request(f"{self._base_url}/health")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def run(
        self,
        task: str,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
        timeout: int = 300,
    ) -> ExecutorResult:
        del allowed_tools, max_turns, cwd  # remote container owns the workspace

        if not self._token:
            return ExecutorResult(
                success=False,
                error=(
                    "VOLY_CF_CONTAINERS_TOKEN is not set. "
                    "Mint a tenant JWT (voly-cloud tenant-token) matching the "
                    "sandbox-spike JWT_SECRET."
                ),
                metadata=self._meta(),
            )

        if not self.is_available():
            _log.warning("cf-containers Worker not reachable at %s", self._base_url)
            return ExecutorResult(
                success=False,
                error=(
                    f"Cloudflare Containers Worker not reachable at {self._base_url}. "
                    "Run: cd voly-cloud/cf-workers/sandbox-spike && "
                    "npx wrangler dev --ip 127.0.0.1 --port 8791 --local"
                ),
                not_available=True,
                metadata=self._meta(),
            )

        started = time.monotonic()
        payload = self._post_run(task, timeout=timeout)
        duration_ms = (time.monotonic() - started) * 1000

        if payload.get("_http_error"):
            err = str(payload.get("error") or "cf-containers request failed")
            return ExecutorResult(
                success=False,
                error=err,
                duration_ms=duration_ms,
                billing_error=_is_billing_error(err),
                not_available="connection" in err.lower() or "not reachable" in err.lower(),
                metadata={**self._meta(), "response": _safe_meta(payload)},
            )

        success = bool(payload.get("success"))
        # Prefer explicit sandbox_error / note, else compact JSON summary.
        error = ""
        if not success:
            error = str(
                payload.get("sandbox_error")
                or payload.get("error")
                or payload.get("note")
                or "Cloudflare Containers run failed"
            )

        output = _format_output(payload)
        return ExecutorResult(
            success=success,
            output=output if success else "",
            error=error,
            duration_ms=duration_ms,
            num_turns=1,
            session_id=str(payload.get("run_id") or ""),
            billing_error=_is_billing_error(error) if error else False,
            metadata={
                **self._meta(),
                "stub": bool(payload.get("stub")),
                "worker_mode": payload.get("mode"),
                "tenant_id": payload.get("tenant_id"),
                "probes": payload.get("probes"),
                "response": _safe_meta(payload),
            },
        )

    def _meta(self) -> dict[str, Any]:
        return {
            "executor": "cf-containers",
            "provider": "cloudflare-containers",
            "mode": self._mode,
            "base_url": self._base_url,
        }

    def _post_run(self, task: str, *, timeout: int) -> dict[str, Any]:
        body: dict[str, Any] = {"task": task, "mode": self._mode}
        if self._repo:
            body["repo"] = self._repo

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        from voly.correlation import correlation_headers
        headers = correlation_headers(headers)
        req = urllib.request.Request(
            f"{self._base_url}/runs",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
                raw = resp.read().decode()
                data = json.loads(raw) if raw else {}
                if not isinstance(data, dict):
                    return {"_http_error": True, "error": f"unexpected response: {raw[:200]}"}
                return data
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                parsed = json.loads(body_text)
                if isinstance(parsed, dict):
                    # 401/403 are auth; 502 may still carry a structured body.
                    if e.code in (401, 403):
                        parsed["_http_error"] = True
                        parsed.setdefault("error", f"HTTP {e.code}: authentication failed")
                    else:
                        # Prefer Worker body (success/sandbox_error) when present.
                        parsed.setdefault("error", f"HTTP {e.code}")
                    return parsed
                msg = body_text
            except Exception:
                msg = body_text
            return {"_http_error": True, "error": f"HTTP {e.code}: {msg}", "success": False}
        except urllib.error.URLError as e:
            return {
                "_http_error": True,
                "success": False,
                "error": f"connection error: {e.reason}",
            }
        except Exception as e:
            return {"_http_error": True, "success": False, "error": str(e)}


def _format_output(payload: dict[str, Any]) -> str:
    """Human-readable summary for CLI/UI from Worker response."""
    parts: list[str] = []
    mode = payload.get("mode") or ""
    if payload.get("stub"):
        parts.append(f"[stub] Cloudflare Containers receipt (mode={mode})")
    else:
        parts.append(f"Cloudflare Containers run ok (mode={mode})")

    if payload.get("run_id"):
        parts.append(f"run_id: {payload['run_id']}")
    if payload.get("tenant_id"):
        parts.append(f"tenant_id: {payload['tenant_id']}")

    probes = payload.get("probes")
    if isinstance(probes, dict):
        parts.append("probes:")
        for key, val in probes.items():
            parts.append(f"  {key}: {val}")

    if payload.get("diff"):
        parts.append("\n--- git diff ---\n" + str(payload["diff"])[:4000])
    elif payload.get("stdout"):
        parts.append("\n" + str(payload["stdout"])[:4000])
    elif payload.get("note"):
        parts.append(str(payload["note"]))
    elif payload.get("task"):
        parts.append(f"task: {payload['task']}")

    return "\n".join(parts)


def _safe_meta(payload: dict[str, Any]) -> dict[str, Any]:
    """Trim bulky fields before stuffing into ExecutorResult.metadata."""
    skip = {"diff", "stdout", "stderr", "probes"}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k.startswith("_") or k in skip:
            continue
        if isinstance(v, str) and len(v) > 500:
            out[k] = v[:500] + "…"
        else:
            out[k] = v
    return out
