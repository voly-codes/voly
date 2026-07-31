"""Constrained in-process hook adapter and built-in handlers."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import replace
from pathlib import Path
from typing import Any

from .schema import FailPolicy, HookEvent, HookManifest, HookResult

_HANDLER_PERMISSIONS = {
    "observe": {"observe"},
    "scoped_tests": {"execute_tests"},
    "secret_scan": {"read_project", "scan_secrets"},
    "docs_check": {"read_project", "read_docs"},
    "budget_notify": {"notify_budget"},
}
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+-]{12,}"
)


def _observe(event: HookEvent) -> dict[str, Any]:
    return {"event_type": event.event_type.value, "payload_keys": sorted(event.payload)}


def _scoped_tests(event: HookEvent) -> dict[str, Any]:
    argv = event.payload.get("test_argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        return {"skipped": "test_argv not provided"}
    executable = Path(argv[0]).name.lower()
    allowed = {
        "python", "python.exe", "python3", "python3.exe", "pytest", "pytest.exe",
        "npm", "npm.cmd", "pnpm", "pnpm.cmd", "yarn", "yarn.cmd",
        "bun", "bun.exe", "go", "go.exe", "cargo", "cargo.exe",
    }
    if executable not in allowed:
        raise RuntimeError(f"test executable is not allowlisted: {executable}")
    completed = subprocess.run(
        argv,
        cwd=event.cwd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=float(event.payload.get("test_timeout_seconds", 60)),
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"scoped tests failed with exit code {completed.returncode}")
    return {"exit_code": 0, "output": completed.stdout[-1000:]}


def _secret_scan(event: HookEvent) -> dict[str, Any]:
    root = Path(event.cwd).resolve()
    findings = []
    for relative in event.payload.get("changed_files") or []:
        path = (root / str(relative)).resolve()
        if root not in path.parents or not path.is_file() or path.stat().st_size > 512_000:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _SECRET_RE.search(text):
            findings.append(str(path.relative_to(root)).replace("\\", "/"))
    if findings:
        raise RuntimeError(f"potential secrets in: {', '.join(findings)}")
    return {"scanned": len(event.payload.get("changed_files") or []), "findings": 0}


def _docs_check(event: HookEvent) -> dict[str, Any]:
    changed = [str(item).replace("\\", "/") for item in event.payload.get("changed_files") or []]
    code_changed = any(item.startswith("voly/") and item.endswith(".py") for item in changed)
    docs_changed = any(item.startswith(("docs/", "openwiki/")) for item in changed)
    if code_changed and not docs_changed:
        raise RuntimeError("backend code changed without docs/OpenWiki update")
    return {"code_changed": code_changed, "docs_changed": docs_changed}


def _budget_notify(event: HookEvent) -> dict[str, Any]:
    return {
        "threshold": event.payload.get("threshold"),
        "spent": event.payload.get("spent"),
        "notification": "recorded",
    }


_HANDLERS: dict[str, Callable[[HookEvent], dict[str, Any]]] = {
    "observe": _observe,
    "scoped_tests": _scoped_tests,
    "secret_scan": _secret_scan,
    "docs_check": _docs_check,
    "budget_notify": _budget_notify,
}


class HookRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[HookManifest]:
        if not self.path.is_file():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [HookManifest.from_dict(item) for item in data]

    def save(self, manifests: list[HookManifest]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [manifest.to_dict() for manifest in manifests],
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)

    def import_manifest(self, data: dict[str, Any]) -> HookManifest:
        manifest = HookManifest.from_dict(data, imported=True)
        manifests = [item for item in self.load() if item.hook_id != manifest.hook_id]
        manifests.append(manifest)
        self.save(manifests)
        return manifest

    def approve(self, hook_id: str) -> HookManifest:
        manifests = self.load()
        manifest = next((item for item in manifests if item.hook_id == hook_id), None)
        if manifest is None:
            raise KeyError(hook_id)
        manifest.enabled = True
        manifest.approved_at = time.time()
        self.save(manifests)
        return manifest


class HookAdapter:
    def __init__(
        self,
        registry: HookRegistry,
        *,
        state_path: str | Path,
        evidence_log: str | Path,
        telemetry_log: str | Path,
    ):
        self.registry = registry
        self.state_path = Path(state_path)
        self.evidence_log = Path(evidence_log)
        self.telemetry_log = Path(telemetry_log)

    def _state(self) -> set[str]:
        if not self.state_path.is_file():
            return set()
        return set(json.loads(self.state_path.read_text(encoding="utf-8")))

    def _save_state(self, keys: set[str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(sorted(keys), indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _key(manifest: HookManifest, event: HookEvent) -> str:
        raw = f"{manifest.hook_id}|{manifest.idempotency}|{event.run_id}|{event.event_type.value}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _append(path: Path, result: HookResult) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

    def dispatch(self, event: HookEvent) -> list[HookResult]:
        keys = self._state()
        results = []
        for manifest in self.registry.load():
            if not manifest.enabled or event.event_type not in manifest.events:
                continue
            key = self._key(manifest, event)
            if key in keys:
                result = HookResult(
                    manifest.hook_id, event.event_id, "duplicate", True, 0,
                    idempotency_key=key,
                )
                self._append(self.evidence_log, result)
                self._append(self.telemetry_log, result)
                results.append(result)
                continue
            started = time.monotonic()
            handler = _HANDLERS.get(manifest.handler)
            expected = _HANDLER_PERMISSIONS.get(manifest.handler)
            error = ""
            output: dict[str, Any] = {}
            status = "completed"
            if handler is None:
                error = "handler is not allowlisted"
                status = "blocked"
            elif expected is None or not expected.issubset(set(manifest.permissions)):
                error = "required permissions were not granted"
                status = "blocked"
            else:
                handler_event = event
                if manifest.handler == "scoped_tests":
                    payload = dict(event.payload)
                    payload["test_timeout_seconds"] = min(
                        float(payload.get("test_timeout_seconds", manifest.timeout_seconds)),
                        manifest.timeout_seconds,
                    )
                    handler_event = replace(event, payload=payload)
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(handler, handler_event)
                try:
                    output = future.result(timeout=manifest.timeout_seconds)
                except TimeoutError:
                    error = "hook timeout"
                    status = "timeout"
                    future.cancel()
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                    status = "failed"
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
            proceed = status == "completed" or manifest.fail_policy is FailPolicy.OPEN
            result = HookResult(
                manifest.hook_id,
                event.event_id,
                status,
                proceed,
                (time.monotonic() - started) * 1000,
                output=output,
                error=error,
                idempotency_key=key,
            )
            keys.add(key)
            self._save_state(keys)
            self._append(self.evidence_log, result)
            self._append(self.telemetry_log, result)
            results.append(result)
        return results
