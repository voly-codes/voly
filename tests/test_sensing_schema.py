from __future__ import annotations

import pytest

from voly.sensing import ActionReport, Option, Signal


def test_signal_round_trip() -> None:
    signal = Signal(
        signal_id="rss-a1b2c3",
        source="rss",
        source_ref="https://example.com/feed.xml#entry-42",
        captured_at="2026-08-27T10:03:00Z",
        dedup_key="sha256:abc",
        payload={"title": "Pricing changed", "raw": {"id": "entry-42"}},
        confidence=0.8,
    )

    assert Signal.from_dict(signal.to_dict()) == signal


def test_option_round_trip_and_closed_vocabularies() -> None:
    option = Option(
        option_id="opt-1",
        signal_id="rss-a1b2c3",
        title="Review pricing",
        rationale="A competitor changed its enterprise tier.",
        urgency="high",
        estimated_impact="Potential enterprise churn",
        action_kind="business",
    )

    assert Option.from_dict(option.to_dict()) == option
    with pytest.raises(ValueError, match="urgency"):
        Option.from_dict({**option.to_dict(), "urgency": "critical"})
    with pytest.raises(ValueError, match="action_kind"):
        Option.from_dict({**option.to_dict(), "action_kind": "shell"})


def test_action_report_round_trip() -> None:
    report = ActionReport(
        action_kind="http_call",
        target="https://api.example.com/v1/deals/123",
        request_summary="PATCH deals/123 status=won",
        result="200 OK",
        metadata={"idempotency_key": "decision-opt-1"},
    )

    assert ActionReport.from_dict(report.to_dict()) == report
