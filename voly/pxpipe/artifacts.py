"""Local artifact capture for pxpipe rendered PNGs."""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def artifact_root(config: Any) -> Path:
    telemetry = getattr(config, "telemetry", None)
    events_dir = Path(getattr(telemetry, "events_dir", ".voly/events"))
    return events_dir.parent / "pxpipe" / "images"


def artifact_dir(config: Any, task_id: str) -> Path:
    return artifact_root(config) / task_id


def inbox_dir(config: Any) -> Path:
    return artifact_root(config) / "_inbox"


def _pngs(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(p for p in path.glob("*.png") if p.is_file())


@contextmanager
def capture_pxpipe_artifacts(config: Any, task_id: str) -> Iterator[Path | None]:
    """Set PXPIPE_DUMP_DIR for this task and snapshot the shared inbox."""

    pxpipe = getattr(config, "pxpipe", None)
    if not pxpipe or not getattr(pxpipe, "enabled", False):
        yield None
        return

    target = artifact_dir(config, task_id)
    target.mkdir(parents=True, exist_ok=True)
    inbox = inbox_dir(config)
    inbox.mkdir(parents=True, exist_ok=True)
    before_inbox = {p.name for p in _pngs(inbox)}
    previous = os.environ.get("PXPIPE_DUMP_DIR")
    os.environ["PXPIPE_DUMP_DIR"] = str(target)
    try:
        yield target
    finally:
        for src in _pngs(inbox):
            if src.name in before_inbox:
                continue
            dst = target / src.name
            if dst.exists():
                dst = target / f"inbox_{src.name}"
            try:
                shutil.move(str(src), str(dst))
            except OSError:
                pass
        if previous is None:
            os.environ.pop("PXPIPE_DUMP_DIR", None)
        else:
            os.environ["PXPIPE_DUMP_DIR"] = previous


def collect_pxpipe_artifacts(config: Any, task_id: str) -> list[dict[str, Any]]:
    target = artifact_dir(config, task_id)
    if not target.exists():
        return []

    artifacts: list[dict[str, Any]] = []
    for path in sorted(target.glob("*.png")):
        if not path.is_file():
            continue
        stat = path.stat()
        artifacts.append({
            "kind": "pxpipe_image",
            "media_type": "image/png",
            "name": path.name,
            "bytes": stat.st_size,
            "url": f"/api/tasks/{task_id}/artifacts/{path.name}",
        })
    return artifacts
