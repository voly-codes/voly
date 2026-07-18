"""P4: exclusive cwd executor lock across processes."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from voly.a2a.cwd_lock import cwd_executor_lock


def test_cwd_executor_lock_serializes(tmp_path: Path) -> None:
    order: list[str] = []

    def worker(name: str) -> None:
        with cwd_executor_lock(str(tmp_path), timeout=5.0):
            order.append(f"{name}:in")
            time.sleep(0.15)
            order.append(f"{name}:out")

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert order in (
        ["a:in", "a:out", "b:in", "b:out"],
        ["b:in", "b:out", "a:in", "a:out"],
    )
    assert not (tmp_path / ".voly" / "executor.lock").exists()


def test_cwd_executor_lock_steals_stale(tmp_path: Path) -> None:
    lock = tmp_path / ".voly"
    lock.mkdir(parents=True)
    # PID that cannot exist on Linux (kernel reserved / unlikely).
    (lock / "executor.lock").write_text("1\n", encoding="utf-8")
    # PID 1 usually exists — write a high unused pid instead.
    dead = 2**31 - 3
    try:
        os.kill(dead, 0)
        pytest.skip("unexpected live pid")
    except OSError:
        pass
    (lock / "executor.lock").write_text(f"{dead}\n", encoding="utf-8")
    with cwd_executor_lock(str(tmp_path), timeout=2.0):
        assert (lock / "executor.lock").exists()
