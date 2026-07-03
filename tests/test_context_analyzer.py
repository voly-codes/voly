"""Tests for ContextAnalyzer."""

from voly.headroom.analyzer import ContextAnalyzer


def test_analyze_counts_tokens_chars_lines() -> None:
    text = "hello world\nnice to meet you\nbye"
    result = ContextAnalyzer().analyze(text)
    assert result["chars"] == len(text)
    assert result["tokens"] == 8  # ceil(32 / 4)
    assert result["lines"] == 3
    assert "warning" not in result


def test_analyze_warns_on_large_context() -> None:
    text = "x" * 500_000
    result = ContextAnalyzer().analyze(text)
    assert result["tokens"] > 100_000
    assert "warning" in result


def test_compress_returns_unchanged_when_within_target() -> None:
    text = "short text"
    assert ContextAnalyzer().compress(text, 100) == text


def test_compress_truncates_with_marker() -> None:
    text = "A" * 200 + "\n" + "B" * 200
    compressed = ContextAnalyzer().compress(text, 50)
    assert compressed.count("\n") >= 2
    assert "lines skipped" in compressed
    assert len(compressed) < len(text)


def test_estimate_cost_with_known_model() -> None:
    cost = ContextAnalyzer.estimate_cost(1000, "gpt-4o")
    assert cost == 2.5 / 1000  # 0.0025

    cost_sonnet = ContextAnalyzer.estimate_cost(1000, "claude-sonnet-4-6")
    assert cost_sonnet == 0.003

    cost_default = ContextAnalyzer.estimate_cost(1000, "unknown")
    assert cost_default == 0.001
