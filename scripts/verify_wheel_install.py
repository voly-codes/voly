"""Verify that a built VOLY wheel works outside the source checkout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _wheel_path(value: str | None) -> Path:
    if value:
        wheel = Path(value).resolve()
        if not wheel.is_file():
            raise FileNotFoundError(f"Wheel does not exist: {wheel}")
        return wheel

    wheels = sorted(Path("dist").glob("voly-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected exactly one VOLY wheel in dist/, found {len(wheels)}")
    return wheels[0].resolve()


def verify(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="voly-wheel-") as raw_temp:
        root = Path(raw_temp)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)

        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        voly = scripts / ("voly.exe" if os.name == "nt" else "voly")
        repo = root / "sample repo"
        (repo / ".git").mkdir(parents=True)

        _run([str(python), "-m", "pip", "install", str(wheel)], cwd=root)
        module_path = _run(
            [str(python), "-c", "import pathlib, voly; print(pathlib.Path(voly.__file__).resolve())"],
            cwd=root,
        )
        if environment.resolve() not in Path(module_path).parents:
            raise RuntimeError(f"VOLY was imported outside the clean environment: {module_path}")

        version = _run([str(voly), "--version"], cwd=root)
        check_env = os.environ.copy()
        check_env["CURSOR_API_KEY"] = "ci-readiness-only"
        output = _run(
            [str(voly), "quickstart", "--check", "--json", "--cwd", str(repo)],
            cwd=root,
            env=check_env,
        )
        result = json.loads(output)

        if not result["ready"]:
            raise RuntimeError(f"Installed quickstart was not ready: {result['blockers']}")
        if result["config"]["status"] != "missing" or (repo / "voly.yaml").exists():
            raise RuntimeError("Read-only quickstart unexpectedly changed the sample repository")
        if "--dry-run" not in result["next_command"]:
            raise RuntimeError("Quickstart did not produce a safe dry-run handoff")

        print(f"Verified {wheel.name}: {version}; clean quickstart check passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", help="Wheel path; defaults to dist/voly-*.whl")
    args = parser.parse_args()
    verify(_wheel_path(args.wheel))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"wheel verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
