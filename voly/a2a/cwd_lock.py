"""Exclusive lock so concurrent ``voly run`` processes do not share one cwd."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_log = logging.getLogger("voly.a2a")


@contextmanager
def cwd_executor_lock(cwd: str, *, timeout: float = 900.0) -> Iterator[None]:
    """Serialize executor work on ``cwd`` across processes (P4 same-cwd isolation).

    Chat-only parallel waves inside one run stay lock-free; this guards the
    file-writing executor so ``files_touched`` / git deltas are not mixed with
    another run on the same tree.
    """
    if not cwd:
        yield
        return
    root = Path(cwd)
    lock_dir = root / ".voly"
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log.debug("cwd lock mkdir skipped: %s", exc)
        yield
        return

    lock_path = lock_dir / "executor.lock"
    deadline = time.monotonic() + max(1.0, float(timeout))
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, f"{os.getpid()}\n".encode())
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"cwd executor lock busy for {timeout:.0f}s: {lock_path}"
                ) from None
            # Stale lock: owner gone → steal.
            try:
                text = lock_path.read_text(encoding="utf-8").strip()
                owner = int(text.splitlines()[0]) if text else 0
            except (OSError, ValueError):
                owner = 0
            if owner and owner != os.getpid():
                try:
                    os.kill(owner, 0)
                except OSError:
                    try:
                        lock_path.unlink(missing_ok=True)
                    except OSError:
                        pass
            time.sleep(0.25)
        except OSError as exc:
            _log.debug("cwd lock open skipped: %s", exc)
            yield
            return
    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
