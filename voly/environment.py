"""Local environment readiness — CLI binaries, provider keys, cwd, cloud link.

Used by ``GET /api/environment``, ``voly status``, and the Web UI banner.
Does not call remote provider APIs (presence of env keys / PATH only).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EnvCheck:
    id: str
    label: str
    status: str  # ok | warn | error | skip
    detail: str = ""
    hint: str = ""
    group: str = "general"  # providers | executors | cwd | cloud | runtime

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EnvironmentReport:
    ready: bool
    summary: str
    checks: list[EnvCheck] = field(default_factory=list)
    executors: dict[str, dict[str, Any]] = field(default_factory=dict)
    providers_configured: list[str] = field(default_factory=list)
    default_cwd: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
            "executors": self.executors,
            "providers_configured": self.providers_configured,
            "default_cwd": self.default_cwd,
        }


# Env vars that unlock text / gateway paths (from ai_gateway.health)
_PROVIDER_ENV: dict[str, list[str]] = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "google": ["GOOGLE_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "opencode": ["OPENCODE_API_KEY"],
    "mimo": ["MIMO_API_KEY"],
    "workers-ai": ["CLOUDFLARE_API_TOKEN"],
    "cursor": ["CURSOR_API_KEY"],
}

# File-capable / CLI executors: binary name(s) on PATH
_EXECUTOR_BINS: dict[str, list[str]] = {
    "claude-code": ["claude"],
    "opencode": ["opencode"],
    "zen": ["opencode"],  # zen path uses opencode CLI when present
    "wrangler": ["wrangler"],
    "cursor": [],  # API-key based, not a PATH binary
}

_REPO_ROOT = Path(__file__).resolve().parent.parent

_WORKING_DIRECTORY_LABEL = "Working directory"


def _command_names(binary: str, *, windows: bool | None = None) -> tuple[str, ...]:
    """Return executable names used by native and npm CLIs on this platform."""
    is_windows = os.name == "nt" if windows is None else windows
    if not is_windows:
        return (binary,)
    # npm's executable Windows entry point is the .cmd shim. Prefer it over
    # the extensionless POSIX shell script that npm also places in .bin.
    return (f"{binary}.cmd", f"{binary}.exe", f"{binary}.bat", binary)


def _local_cli_candidates(binary: str) -> list[Path]:
    """Find repo-local npm binaries without requiring node_modules on PATH."""
    bin_dirs = (
        _REPO_ROOT / "node_modules" / ".bin",
        _REPO_ROOT / "cf-workers" / "agent" / "node_modules" / ".bin",
    )
    return [directory / name for directory in bin_dirs for name in _command_names(binary)]


def _env_set(names: list[str]) -> bool:
    return any(bool(os.environ.get(n, "").strip()) for n in names)


def _which_any(bins: list[str]) -> str | None:
    for b in bins:
        for name in _command_names(b):
            path = shutil.which(name)
            if path:
                return path
        for candidate in _local_cli_candidates(b):
            if candidate.is_file():
                return str(candidate.resolve())
    return None


def _check_providers() -> tuple[list[EnvCheck], list[str]]:
    checks: list[EnvCheck] = []
    configured: list[str] = []
    for name, keys in _PROVIDER_ENV.items():
        if _env_set(keys):
            configured.append(name)
            checks.append(
                EnvCheck(
                    id=f"provider:{name}",
                    label=f"Provider {name}",
                    status="ok",
                    detail=f"{keys[0]} set",
                    group="providers",
                )
            )
    if not configured:
        checks.append(
            EnvCheck(
                id="providers",
                label="Model / API keys",
                status="error",
                detail="No provider API keys found in the environment",
                hint="Copy .env.example → .env and set at least ANTHROPIC_API_KEY or OPENAI_API_KEY (or CLOUDFLARE_API_TOKEN for Workers AI).",
                group="providers",
            )
        )
    else:
        checks.insert(
            0,
            EnvCheck(
                id="providers",
                label="Model / API keys",
                status="ok",
                detail=f"{len(configured)} provider(s): {', '.join(configured)}",
                group="providers",
            )
        )
    return checks, configured


def _check_executors() -> tuple[list[EnvCheck], dict[str, dict[str, Any]]]:
    checks: list[EnvCheck] = []
    exec_map: dict[str, dict[str, Any]] = {}

    # pipeline is always "available" as a routing mode; needs providers separately
    exec_map["pipeline"] = {
        "available": True,
        "kind": "gateway",
        "detail": "Routes via AIGateway (needs a provider key)",
    }

    for name, bins in _EXECUTOR_BINS.items():
        if name == "cursor":
            ok = _env_set(["CURSOR_API_KEY"])
            exec_map[name] = {
                "available": ok,
                "kind": "api",
                "detail": "CURSOR_API_KEY set" if ok else "CURSOR_API_KEY missing",
                "hint": "" if ok else "Set CURSOR_API_KEY in .env",
            }
            checks.append(
                EnvCheck(
                    id=f"executor:{name}",
                    label=f"Executor {name}",
                    status="ok" if ok else "warn",
                    detail=exec_map[name]["detail"],
                    hint=exec_map[name].get("hint", ""),
                    group="executors",
                )
            )
            continue

        path = _which_any(bins)
        ok = path is not None
        label_bin = bins[0] if bins else name
        exec_map[name] = {
            "available": ok,
            "kind": "cli",
            "binary": label_bin,
            "path": path or "",
            "detail": path or f"{label_bin} not found in PATH",
            "hint": "" if ok else f"Install the CLI and ensure `{label_bin}` is on PATH",
        }
        if name == "wrangler" and ok:
            exec_map[name]["hint"] = (
                "Binary found. For file writes via Workers AI, also run: "
                "cd cf-workers/agent && npm run dev"
            )
        checks.append(
            EnvCheck(
                id=f"executor:{name}",
                label=f"Executor {name}",
                status="ok" if ok else "warn",
                detail=exec_map[name]["detail"],
                hint=exec_map[name].get("hint", ""),
                group="executors",
            )
        )

    any_cli = any(
        v.get("available") for k, v in exec_map.items() if k != "pipeline"
    )
    if not any_cli:
        checks.insert(
            0,
            EnvCheck(
                id="executors",
                label="File-capable CLIs",
                status="warn",
                detail="No coding-agent CLI found (claude / opencode / wrangler)",
                hint="Install Claude Code (`claude`) for the usual file-writing path, or use pipeline with an API key for text-only.",
                group="executors",
            )
        )
    else:
        ready_names = [k for k, v in exec_map.items() if k != "pipeline" and v.get("available")]
        checks.insert(
            0,
            EnvCheck(
                id="executors",
                label="File-capable CLIs",
                status="ok",
                detail=f"Available: {', '.join(ready_names)}",
                group="executors",
            )
        )

    return checks, exec_map


def _check_cwd(cwd: str | None, default_cwd: str) -> list[EnvCheck]:
    path_str = (cwd or default_cwd or "").strip()
    if not path_str:
        return [
            EnvCheck(
                id="cwd",
                label=_WORKING_DIRECTORY_LABEL,
                status="warn",
                detail="No project cwd set",
                hint="Set Working dir in the UI, or VOLY_PROJECT_CWD / default_cwd in voly.yaml. Hybrid file writes need a cwd.",
                group="cwd",
            )
        ]
    p = Path(path_str).expanduser()
    if not p.is_dir():
        return [
            EnvCheck(
                id="cwd",
                label=_WORKING_DIRECTORY_LABEL,
                status="error",
                detail=f"Not a directory: {p}",
                hint="Pick an existing project folder.",
                group="cwd",
            )
        ]
    git = (p / ".git").exists()
    return [
        EnvCheck(
            id="cwd",
            label=_WORKING_DIRECTORY_LABEL,
            status="ok" if git else "warn",
            detail=str(p.resolve()),
            hint="" if git else "Folder exists but has no .git — plan gates / diff checks work best in a git repo.",
            group="cwd",
        )
    ]


def _check_cloud(config: Any | None) -> list[EnvCheck]:
    try:
        from voly.cloud_link import resolve_cloud_link

        link = resolve_cloud_link(config)
    except Exception:
        link = None
    if not link:
        return [
            EnvCheck(
                id="cloud",
                label="VOLY Cloud link",
                status="skip",
                detail="Not linked (optional)",
                hint="Run `voly cloud link` when you want local runs in the team dashboard.",
                group="cloud",
            )
        ]
    return [
        EnvCheck(
            id="cloud",
            label="VOLY Cloud link",
            status="ok",
            detail=f"Linked → {link.get('base_url', '')} tenant={link.get('tenant_id', '')[:8]}…",
            group="cloud",
        )
    ]


def collect_environment_report(
    config: Any | None = None,
    *,
    cwd: str | None = None,
) -> EnvironmentReport:
    """Build a readiness report for UI / CLI / API."""
    default_cwd = ""
    if config is not None:
        default_cwd = (
            getattr(config, "default_cwd", "")
            or os.environ.get("VOLY_PROJECT_CWD", "")
            or ""
        )
    else:
        default_cwd = os.environ.get("VOLY_PROJECT_CWD", "")

    checks: list[EnvCheck] = [
        EnvCheck(
            id="runtime",
            label="VOLY runtime",
            status="ok",
            detail="Python package loaded",
            group="runtime",
        )
    ]

    p_checks, providers = _check_providers()
    checks.extend(p_checks)

    e_checks, exec_map = _check_executors()
    checks.extend(e_checks)

    checks.extend(_check_cwd(cwd, default_cwd))
    checks.extend(_check_cloud(config))

    has_provider = bool(providers)
    has_cli = any(
        v.get("available") for k, v in exec_map.items() if k != "pipeline"
    )
    ready = has_provider or has_cli

    if ready and has_provider and has_cli:
        summary = "Ready — providers and at least one coding CLI are available."
    elif ready and has_cli:
        summary = "Ready for file-capable runs — install an API key for pipeline/chat roles."
    elif ready and has_provider:
        summary = "Ready for text/pipeline runs — install `claude` (or another CLI) for file writes."
    else:
        summary = "Not ready — add an API key in .env and/or install a coding-agent CLI."

    return EnvironmentReport(
        ready=ready,
        summary=summary,
        checks=checks,
        executors=exec_map,
        providers_configured=providers,
        default_cwd=default_cwd,
    )
