"""Repository baseline capture before file-capable executor runs."""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voly.evidence.schema import BaselineCheck, RepositoryBaseline


@dataclass(frozen=True)
class _Command:
    name: str
    argv: list[str]

    @property
    def display(self) -> str:
        return subprocess.list2cmdline(self.argv)


def _stack_names(profile: Any) -> list[str]:
    values: list[str] = []
    for collection in (
        getattr(profile, "languages", None) or [],
        getattr(profile, "frameworks", None) or [],
    ):
        for value in collection:
            name = getattr(value, "name", value)
            if name and str(name) not in values:
                values.append(str(name))
    return values


def _package_script(cwd: Path, name: str) -> bool:
    try:
        data = json.loads((cwd / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(isinstance(data.get("scripts"), dict) and data["scripts"].get(name))


def _node_runner(package_managers: list[str]) -> str:
    lowered = {str(item).lower() for item in package_managers}
    if "pnpm" in lowered:
        return "pnpm"
    if "yarn" in lowered:
        return "yarn"
    return "npm"


def _auto_commands(cwd: Path, profile: Any) -> list[_Command]:
    """Discover deterministic checks without invoking a shell."""
    from voly.plan.suggest import suggest_test_command

    package_managers = list(getattr(profile, "package_managers", None) or [])
    commands: list[_Command] = []
    runner = _node_runner(package_managers)

    if (cwd / "package.json").is_file() and _package_script(cwd, "build"):
        commands.append(_Command("build", [runner, "run", "build"]))
    elif (cwd / "go.mod").is_file():
        commands.append(_Command("build", ["go", "build", "./..."]))
    elif (cwd / "Cargo.toml").is_file():
        commands.append(_Command("build", ["cargo", "check"]))
    elif (cwd / "pom.xml").is_file():
        commands.append(_Command("build", ["mvn", "package", "-DskipTests", "-q"]))

    test_command = suggest_test_command(profile)
    if test_command:
        commands.append(_Command("tests", _split_command(test_command)))

    linters = {str(item).lower() for item in (getattr(profile, "linter_tools", None) or [])}
    if "ruff" in linters:
        commands.append(_Command("lint", ["ruff", "check", "."]))
    elif "eslint" in linters:
        commands.append(_Command("lint", ["npx", "eslint", "."]))
    elif "golangci-lint" in linters:
        commands.append(_Command("lint", ["golangci-lint", "run"]))
    return [command for command in commands if command.argv]


def _split_command(command: str) -> list[str]:
    try:
        # Configuration commands use one documented, shell-independent quoting
        # grammar on every OS. The resulting argv is executed with shell=False.
        return shlex.split(str(command), posix=True)
    except ValueError:
        return []


def _configured_commands(raw: dict[str, str] | None) -> list[_Command]:
    commands: list[_Command] = []
    for name, command in (raw or {}).items():
        argv = _split_command(command)
        if argv:
            commands.append(_Command(str(name), argv))
    return commands


def _run_check(command: _Command, cwd: Path, timeout: float, max_chars: int) -> BaselineCheck:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command.argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        return BaselineCheck(
            name=command.name,
            command=command.display,
            status="unavailable",
            argv=list(command.argv),
            duration_ms=(time.monotonic() - started) * 1000,
            failure_kind="environment_failure",
            output_excerpt=str(exc)[:max_chars],
        )
    except subprocess.TimeoutExpired:
        return BaselineCheck(
            name=command.name,
            command=command.display,
            status="timeout",
            argv=list(command.argv),
            duration_ms=(time.monotonic() - started) * 1000,
            failure_kind="environment_failure",
            output_excerpt=f"timeout after {timeout:g}s",
        )
    except OSError as exc:
        return BaselineCheck(
            name=command.name,
            command=command.display,
            status="error",
            argv=list(command.argv),
            duration_ms=(time.monotonic() - started) * 1000,
            failure_kind="environment_failure",
            output_excerpt=str(exc)[:max_chars],
        )

    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    excerpt = output[-max_chars:] if max_chars > 0 else ""
    ok = proc.returncode == 0
    return BaselineCheck(
        name=command.name,
        command=command.display,
        status="passed" if ok else "failed",
        argv=list(command.argv),
        exit_code=proc.returncode,
        duration_ms=(time.monotonic() - started) * 1000,
        failure_kind="" if ok else "preexisting_failure",
        output_excerpt=excerpt,
    )


def capture_repository_baseline(
    cwd: str,
    *,
    auto_commands: bool = True,
    commands: dict[str, str] | None = None,
    timeout_seconds: float = 120.0,
    output_max_chars: int = 2000,
) -> RepositoryBaseline:
    """Capture stack and deterministic health checks before execution."""
    captured_at = datetime.now(timezone.utc).isoformat()
    path = Path(cwd).resolve() if cwd else None
    if path is None or not path.is_dir():
        return RepositoryBaseline(
            captured_at=captured_at,
            health="environment_failure",
            notes=["cwd is missing or is not a directory"],
        )

    try:
        from voly.scanner import ProjectScanner

        profile = ProjectScanner(str(path)).scan()
    except Exception as exc:  # noqa: BLE001
        return RepositoryBaseline(
            captured_at=captured_at,
            health="environment_failure",
            notes=[f"project scan failed: {exc}"],
        )

    selected = _configured_commands(commands)
    if auto_commands:
        configured_names = {command.name for command in selected}
        selected.extend(
            command for command in _auto_commands(path, profile)
            if command.name not in configured_names
        )

    checks = [
        _run_check(
            command,
            path,
            max(1.0, float(timeout_seconds)),
            max(0, int(output_max_chars)),
        )
        for command in selected
    ]
    if any(check.failure_kind == "environment_failure" for check in checks):
        health = "environment_failure"
    elif any(check.failure_kind == "preexisting_failure" for check in checks):
        health = "preexisting_failure"
    elif checks:
        health = "healthy"
    else:
        health = "metadata_only"

    return RepositoryBaseline(
        captured_at=captured_at,
        health=health,
        stack=_stack_names(profile),
        test_frameworks=list(getattr(profile, "test_frameworks", None) or []),
        package_managers=list(getattr(profile, "package_managers", None) or []),
        checks=checks,
        notes=[] if checks else ["no deterministic baseline commands discovered"],
    )
