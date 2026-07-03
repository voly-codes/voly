"""Tests for the semantic provider-error classifier (VOLY risk R4/R1)."""

from __future__ import annotations

import pytest

from voly.ai_gateway.error_classifier import (
    ErrorType,
    classify_provider_error,
    is_context_overflow,
    is_empty_content_response,
    is_terminal_billing_error,
    looks_like_quota_exhausted,
)
from voly.executor.base import _is_billing_error


# ─── Backward compatibility: every old billing pattern still detected ────────
@pytest.mark.parametrize(
    "text",
    [
        "your credit balance is too low",
        "credit balance is too low",
        "credit_balance_too_low",
        "insufficient credits",
        "insufficient balance",
        "exceeded your current quota",
        "insufficient_quota",
        "Error 402: payment required",
        "billing issue on your account",
    ],
)
def test_legacy_billing_patterns_still_flagged(text):
    assert _is_billing_error(text) is True


# ─── The core R4 improvement: rate-limit is NOT a billing error ──────────────
def test_bare_rate_limit_is_not_billing():
    # A plain per-minute 429 must not skip the executor down the billing chain.
    assert _is_billing_error("HTTP 429: too many requests, retry in 20s") is False
    assert classify_provider_error(429, "too many requests") == ErrorType.RATE_LIMITED


def test_429_with_quota_keyword_is_quota_exhausted():
    body = "429: You have hit your daily limit. Try again tomorrow."
    assert classify_provider_error(429, body) == ErrorType.QUOTA_EXHAUSTED
    assert is_terminal_billing_error(body, 429) is True


def test_quota_keywords_detected():
    assert looks_like_quota_exhausted("monthly quota exceeded") is True
    assert looks_like_quota_exhausted("individual quota reached, enable overages") is True
    assert looks_like_quota_exhausted("too many requests this minute") is False


# ─── Status-code semantics ───────────────────────────────────────────────────
def test_402_always_terminal():
    assert classify_provider_error(402, "") == ErrorType.QUOTA_EXHAUSTED
    assert is_terminal_billing_error("", 402) is True


def test_401_unauthorized_vs_deactivated():
    assert classify_provider_error(401, "nope") == ErrorType.UNAUTHORIZED
    assert (
        classify_provider_error(401, "your account has been suspended")
        == ErrorType.ACCOUNT_DEACTIVATED
    )


def test_account_deactivated_is_terminal_billing():
    assert is_terminal_billing_error("this account is deactivated") is True


def test_server_error_and_none():
    assert classify_provider_error(503, "upstream down") == ErrorType.SERVER_ERROR
    assert classify_provider_error(200, "all good") is None


def test_context_overflow():
    assert is_context_overflow("prompt too large for context window") is True
    assert classify_provider_error(400, "input too long") == ErrorType.CONTEXT_OVERFLOW


# ─── Empty-content guard (R1/step 2): legit terminals are NOT fake success ──
def test_empty_content_flagged_when_truly_empty():
    assert is_empty_content_response({"choices": [{"message": {"content": ""}}]}) is True
    assert is_empty_content_response({"content": []}) is True
    assert is_empty_content_response({"choices": []}) is True


def test_empty_content_not_flagged_for_legit_terminals():
    # Claude tool_use / max_tokens with empty content is a valid completion.
    assert is_empty_content_response({"content": [], "stop_reason": "tool_use"}) is False
    assert is_empty_content_response({"content": [], "stop_reason": "max_tokens"}) is False
    # OpenAI finish_reason length / tool_calls likewise.
    assert (
        is_empty_content_response(
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        )
        is False
    )


def test_empty_content_not_flagged_when_tool_calls_present():
    body = {"choices": [{"message": {"content": "", "tool_calls": [{"id": "x"}]}}]}
    assert is_empty_content_response(body) is False


def test_non_dict_body_is_not_empty_content():
    assert is_empty_content_response("plain string") is False
    assert is_empty_content_response(None) is False
