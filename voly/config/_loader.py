"""Config file discovery, .env loading, and top-level load_config() entry point."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from voly.config._types import VOLYConfig, DEFAULT_CONFIG_FILENAME
from voly.config._parser import _parse_config


# VOLY runs against arbitrary external projects via --cwd. Walking all the way
# to the filesystem root risks silently picking up an unrelated ancestor
# directory's voly.yaml/.env (and its credentials) on a multi-project machine.
# Stop at the target project's own VCS root, with a fixed depth cap as a
# backstop for --cwd paths that aren't inside a git repo at all.
_MAX_UPWARD_LEVELS = 20


def _is_repo_root(path: Path) -> bool:
    """True once we've reached the top of the target project (git root)."""
    return (path / ".git").exists()


def _find_config_path(start_dir: Path | None = None) -> Path | None:
    current = start_dir or Path.cwd()
    for _ in range(_MAX_UPWARD_LEVELS):
        candidate = current / DEFAULT_CONFIG_FILENAME
        if candidate.exists():
            return candidate
        if _is_repo_root(current):
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def _load_dotenv(start_dir: Path | None = None) -> None:
    """Load .env file(s) into os.environ (only sets vars that aren't already set).

    Loads in order: VOLY package root .env first (always), then walks up from
    start_dir/cwd to merge project-level .env. First loaded value wins.
    """
    def _apply(env_file: Path) -> None:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value

    # Always load VOLY package root .env first (contains API credentials)
    package_root = Path(__file__).parent.parent.parent
    pkg_env = package_root / ".env"
    if pkg_env.exists():
        _apply(pkg_env)

    # Also walk up from start_dir/cwd to merge any project-level .env, bounded
    # the same way as _find_config_path (see _MAX_UPWARD_LEVELS above).
    current = start_dir or Path.cwd()
    visited = {pkg_env.resolve()} if pkg_env.exists() else set()
    for _ in range(_MAX_UPWARD_LEVELS):
        env_file = current / ".env"
        if env_file.exists() and env_file.resolve() not in visited:
            _apply(env_file)
        if _is_repo_root(current):
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def load_config(config_path: str | Path | None = None) -> VOLYConfig:
    if config_path:
        path = Path(config_path)
    else:
        path = _find_config_path()

    # Load .env before expanding ${VAR} placeholders in YAML
    _load_dotenv(path.parent if path else None)

    if path and path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return _parse_config(raw)

    return VOLYConfig()
