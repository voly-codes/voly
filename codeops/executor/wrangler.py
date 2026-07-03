"""
WranglerExecutor — вызывает Workers AI через локальный wrangler dev сервер,
затем применяет файловые изменения через LocalPatchApplier.

Цепочка:
  1. Собирает локальный контекст (из web/routes/run._gather_local_context)
  2. POST /infer → wrangler dev (localhost:8787)
     → Workers AI (модели на CF, биллинг по CF аккаунту)
  3. LocalPatchApplier парсит FILE-блоки → пишет файлы

Требования:
  - wrangler dev запущен: cd cf-workers/agent && npm run dev
  - [ai] binding в wrangler.jsonc (уже добавлен)
  - CLOUDFLARE_ACCOUNT_ID и CLOUDFLARE_API_TOKEN в среде

Wrangler dev всё равно вызывает CF API (модели не локальны).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from voly.executor.base import Executor, ExecutorResult, _is_billing_error
from voly.executor.patch import LocalPatchApplier

_log = logging.getLogger("voly.executor.wrangler")

_DEFAULT_URL   = "http://127.0.0.1:8787"
_DEFAULT_MODEL = "@cf/moonshotai/kimi-k2.7-code"

# Fallback model if primary is unavailable
_FALLBACK_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"


class WranglerExecutor(Executor):
    """
    Code executor via wrangler dev + Workers AI.
    Inference runs on Cloudflare; file writes happen locally via LocalPatchApplier.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        token: str | None = None,
    ):
        self._base_url = (base_url or os.getenv("WRANGLER_DEV_URL", _DEFAULT_URL)).rstrip("/")
        self._model    = model or os.getenv("WRANGLER_AI_MODEL", _DEFAULT_MODEL)
        self._token    = token or os.getenv("WRANGLER_DEV_TOKEN", "")

    @property
    def name(self) -> str:
        return "wrangler"

    def is_available(self) -> bool:
        """Check if wrangler dev is running at base_url."""
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
        max_turns: int = 1,
        timeout: int = 120,
        context: str | None = None,
    ) -> ExecutorResult:
        if not self.is_available():
            _log.warning("wrangler dev not reachable at %s — skipping", self._base_url)
            return ExecutorResult(
                success=False,
                error=(
                    f"wrangler dev not reachable at {self._base_url}. "
                    "Run: cd cf-workers/agent && npm run dev"
                ),
                not_available=True,
                metadata={"executor": "wrangler", "model": self._model},
            )

        work_dir = os.path.expanduser(cwd) if cwd else os.getcwd()
        started  = time.monotonic()

        # Gather local context if not provided and cwd is known
        if context is None and cwd:
            try:
                from voly.web.routes.run import _gather_local_context
                context = _gather_local_context(task, work_dir, max_chars=5000)
            except Exception as exc:
                _log.debug("context gather failed: %s", exc)

        # Call Workers AI via wrangler dev
        infer_result = self._call_infer(task, context, timeout)
        duration_ms  = (time.monotonic() - started) * 1000

        if not infer_result.get("success"):
            err = infer_result.get("error", "wrangler inference failed")
            return ExecutorResult(
                success=False,
                error=err,
                duration_ms=duration_ms,
                billing_error=_is_billing_error(err),
                metadata={"executor": "wrangler", "model": self._model},
            )

        content = infer_result.get("content", "")
        if not content:
            return ExecutorResult(
                success=False,
                error="empty response from Workers AI",
                duration_ms=duration_ms,
                metadata={"executor": "wrangler", "model": self._model},
            )

        # Apply FILE blocks to local files
        patch_result = LocalPatchApplier(work_dir).apply(content)

        files_written = [f.path for f in patch_result.applied]
        _log.info(
            "wrangler: model=%s applied=%d errors=%d",
            self._model, len(patch_result.applied), len(patch_result.errors),
        )

        output_lines = [content]
        if files_written:
            output_lines.append(f"\n\nFiles written: {', '.join(files_written)}")
        if patch_result.errors:
            output_lines.append(f"\nPatch errors: {'; '.join(patch_result.errors)}")

        return ExecutorResult(
            success=patch_result.success or bool(files_written),
            output="\n".join(output_lines),
            error="; ".join(patch_result.errors) if patch_result.errors else "",
            duration_ms=duration_ms,
            num_turns=1,
            metadata={
                "executor": "wrangler",
                "model": infer_result.get("model", self._model),
                "files_written": files_written,
                "patch_summary": patch_result.summary(),
            },
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _call_infer(
        self,
        task: str,
        context: str | None,
        timeout: int,
    ) -> dict:
        url  = f"{self._base_url}/infer"
        body = {"task": task, "model": self._model}
        if context:
            body["context"] = context

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                msg = json.loads(body_text).get("error", body_text)
            except Exception:
                msg = body_text
            return {"success": False, "error": f"HTTP {e.code}: {msg}", "content": ""}
        except urllib.error.URLError as e:
            return {"success": False, "error": f"connection error: {e.reason}", "content": ""}
        except Exception as e:
            return {"success": False, "error": str(e), "content": ""}
