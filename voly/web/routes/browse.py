"""GET /api/browse — list subdirectories for cwd picker."""

from __future__ import annotations

import os
import pathlib
from typing import Any

from fastapi import APIRouter

router = APIRouter()


def _is_subpath(path: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_browse_path(raw: str) -> pathlib.Path:
    """Resolve and validate a directory path for listing."""
    base = pathlib.Path(raw.strip()) if raw.strip() else pathlib.Path.cwd()
    if not base.is_absolute():
        base = pathlib.Path.cwd() / base

    try:
        resolved = base.resolve()
    except OSError as exc:
        raise ValueError(str(exc)) from exc

    if not resolved.is_dir():
        raise ValueError("Not a directory")

    cwd = pathlib.Path.cwd().resolve()
    path_str = str(resolved)

    if not path_str.startswith("/home") and not _is_subpath(resolved, cwd):
        raise ValueError("Path not allowed")

    return resolved


@router.get("/api/browse")
def browse_directory(path: str = "") -> dict[str, Any]:
    """Return directory entries (dirs only) under a validated path."""
    try:
        resolved = _resolve_browse_path(path)
    except ValueError as exc:
        return {"entries": [], "error": str(exc)}

    entries: list[dict[str, Any]] = []
    try:
        with os.scandir(resolved) as it:
            for entry in it:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name.startswith("."):
                    continue
                child = pathlib.Path(entry.path).resolve()
                entries.append({
                    "name": entry.name,
                    "path": str(child),
                    "is_dir": True,
                })
                if len(entries) >= 50:
                    break
    except OSError as exc:
        return {"entries": [], "error": str(exc)}

    entries.sort(key=lambda e: e["name"].lower())
    return {"entries": entries}
