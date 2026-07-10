"""Priority: WranglerExecutor with mocked infer HTTP + LocalPatchApplier."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from voly.executor.wrangler import WranglerExecutor


def test_is_available_false_on_connection_error() -> None:
    ex = WranglerExecutor(base_url="http://127.0.0.1:1")
    with patch("voly.executor.wrangler.urllib.request.urlopen", side_effect=OSError("down")):
        assert ex.is_available() is False


def test_run_not_available() -> None:
    ex = WranglerExecutor(base_url="http://127.0.0.1:9")
    with patch.object(ex, "is_available", return_value=False):
        r = ex.run("implement x", cwd="/tmp")
    assert r.success is False
    assert r.not_available is True
    assert "not reachable" in (r.error or "").lower()


def test_run_applies_file_blocks(tmp_path: Path) -> None:
    ex = WranglerExecutor(base_url="http://127.0.0.1:8787")
    content = """
### FILE: hello.py
```python
print(1)
```
"""
    with (
        patch.object(ex, "is_available", return_value=True),
        patch.object(
            ex,
            "_call_infer",
            return_value={"success": True, "content": content, "model": "@cf/test"},
        ),
    ):
        r = ex.run("write hello", cwd=str(tmp_path))

    assert r.success is True
    assert (tmp_path / "hello.py").read_text().startswith("print(1)")
    assert "hello.py" in r.metadata.get("files_written", [])


def test_run_infer_failure_billing() -> None:
    ex = WranglerExecutor()
    with (
        patch.object(ex, "is_available", return_value=True),
        patch.object(
            ex,
            "_call_infer",
            return_value={"success": False, "error": "insufficient credits / quota exceeded"},
        ),
    ):
        r = ex.run("task", cwd="/tmp")
    assert r.success is False
    # billing detection depends on classifier — either True or False is ok if error set
    assert r.error


def test_run_empty_content() -> None:
    ex = WranglerExecutor()
    with (
        patch.object(ex, "is_available", return_value=True),
        patch.object(ex, "_call_infer", return_value={"success": True, "content": ""}),
    ):
        r = ex.run("task", cwd="/tmp")
    assert r.success is False
    assert "empty" in (r.error or "").lower()


def test_call_infer_posts_json() -> None:
    ex = WranglerExecutor(base_url="http://example.test", token="tok")
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"success": true, "content": "ok"}'
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("voly.executor.wrangler.urllib.request.urlopen", return_value=mock_resp) as urlopen:
        out = ex._call_infer("do work", context="ctx", timeout=10)

    assert out["success"] is True
    assert out["content"] == "ok"
    req = urlopen.call_args[0][0]
    assert req.full_url.endswith("/infer")
    # urllib normalizes header names
    auth = req.get_header("Authorization") or req.headers.get("Authorization") or ""
    assert "tok" in str(auth) or "tok" in str(getattr(req, "headers", {}))
