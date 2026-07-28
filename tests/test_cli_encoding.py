"""Cross-platform console encoding bootstrap."""

from __future__ import annotations

from io import StringIO

from voly.cli._encoding import configure_utf8_stdio


class _ReconfigurableStream:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


class _BrokenStream:
    def reconfigure(self, **kwargs: str) -> None:
        raise ValueError("stream is already detached")


def test_configure_utf8_stdio_on_windows() -> None:
    stdout = _ReconfigurableStream()
    stderr = _ReconfigurableStream()

    configure_utf8_stdio(platform="win32", streams=(stdout, stderr))  # type: ignore[arg-type]

    expected = [{"encoding": "utf-8", "errors": "replace"}]
    assert stdout.calls == expected
    assert stderr.calls == expected


def test_configure_utf8_stdio_ignores_unsupported_streams() -> None:
    configure_utf8_stdio(
        platform="win32",
        streams=(StringIO(), _BrokenStream()),  # type: ignore[arg-type]
    )


def test_configure_utf8_stdio_is_noop_off_windows() -> None:
    stream = _ReconfigurableStream()

    configure_utf8_stdio(platform="linux", streams=(stream,))  # type: ignore[arg-type]

    assert stream.calls == []
