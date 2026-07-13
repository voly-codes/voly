from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from voly.pxpipe.artifacts import (
    artifact_dir,
    capture_pxpipe_artifacts,
    collect_pxpipe_artifacts,
    inbox_dir,
)
from voly.pxpipe.proxy import PxpipeManager, apply_pxpipe_env


class FakeManager:
    started = False

    def __init__(self, port: int = 47821, models: str = "", dump_dir=None):
        self.port = port
        self.models = models
        self.proxy_url = f"http://127.0.0.1:{port}"

    def is_running(self) -> bool:
        return self.started

    def start(self, wait: bool = True) -> bool:
        self.started = True
        return True


def _cfg(**overrides):
    defaults = {
        "enabled": True,
        "port": 47821,
        "models": "claude-fable-5,gpt-5.6",
        "auto_start": False,
        "override_anthropic_base_url": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_pxpipe_manager_proxy_url() -> None:
    assert PxpipeManager(port=47822).proxy_url == "http://127.0.0.1:47822"


def test_apply_pxpipe_env_noop_when_disabled() -> None:
    env = {"ANTHROPIC_API_KEY": "sk-test"}
    out = apply_pxpipe_env(env, config=_cfg(enabled=False), manager_cls=FakeManager)
    assert out is env
    assert "ANTHROPIC_BASE_URL" not in out


def test_apply_pxpipe_env_skips_when_proxy_not_running() -> None:
    FakeManager.started = False
    env = {"ANTHROPIC_API_KEY": "sk-test"}
    out = apply_pxpipe_env(env, config=_cfg(auto_start=False), manager_cls=FakeManager)
    assert out is env
    assert "ANTHROPIC_BASE_URL" not in out


def test_apply_pxpipe_env_auto_start_sets_base_url() -> None:
    FakeManager.started = False
    env = {"ANTHROPIC_API_KEY": "sk-test"}
    out = apply_pxpipe_env(env, config=_cfg(auto_start=True), manager_cls=FakeManager)
    assert out is not env
    assert out["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:47821"
    assert out["PXPIPE_MODELS"] == "claude-fable-5,gpt-5.6"


def test_apply_pxpipe_env_keeps_existing_base_url_without_override() -> None:
    FakeManager.started = True
    env = {"ANTHROPIC_BASE_URL": "https://existing.example"}
    out = apply_pxpipe_env(env, config=_cfg(), manager_cls=FakeManager)
    assert out["ANTHROPIC_BASE_URL"] == "https://existing.example"
    assert out["PXPIPE_MODELS"] == "claude-fable-5,gpt-5.6"


def test_apply_pxpipe_env_can_override_existing_base_url() -> None:
    FakeManager.started = True
    env = {"ANTHROPIC_BASE_URL": "https://existing.example"}
    out = apply_pxpipe_env(
        env,
        config=_cfg(override_anthropic_base_url=True, port=47822),
        manager_cls=FakeManager,
    )
    assert out["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:47822"


def test_capture_pxpipe_artifacts_collects_task_png(tmp_path: Path) -> None:
    config = SimpleNamespace(
        pxpipe=_cfg(enabled=True),
        telemetry=SimpleNamespace(events_dir=str(tmp_path / ".voly" / "events")),
    )

    with capture_pxpipe_artifacts(config, "task-1"):
        dump = Path(os.environ["PXPIPE_DUMP_DIR"])
        (dump / "rendered.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    artifacts = collect_pxpipe_artifacts(config, "task-1")
    assert artifacts == [{
        "kind": "pxpipe_image",
        "media_type": "image/png",
        "name": "rendered.png",
        "bytes": 8,
        "url": "/api/tasks/task-1/artifacts/rendered.png",
    }]
    assert (artifact_dir(config, "task-1") / "rendered.png").exists()


def test_capture_pxpipe_artifacts_moves_new_inbox_png(tmp_path: Path) -> None:
    config = SimpleNamespace(
        pxpipe=_cfg(enabled=True),
        telemetry=SimpleNamespace(events_dir=str(tmp_path / ".voly" / "events")),
    )
    inbox = inbox_dir(config)
    inbox.mkdir(parents=True)
    (inbox / "old.png").write_bytes(b"old")

    with capture_pxpipe_artifacts(config, "task-2"):
        (inbox / "new.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    assert (inbox / "old.png").exists()
    assert not (inbox / "new.png").exists()
    assert (artifact_dir(config, "task-2") / "new.png").exists()
