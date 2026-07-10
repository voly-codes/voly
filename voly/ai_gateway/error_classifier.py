"""Semantic provider-error classifier.

Ported (idea + pattern tables, not code) from OmniRoute (MIT) —
`open-sse/services/errorClassifier.ts`, `open-sse/config/errorConfig.ts`,
`src/shared/utils/classify429.ts`, `open-sse/services/accountFallback.ts`.
Origin: https://github.com/diegosouzapw/OmniRoute (MIT License).

Why this exists (VOLY risk R4): billing/quota failures used to be detected by
flat substring matching over the error text (`_BILLING_PATTERNS`). That breaks
silently — a reworded upstream error looks like an ordinary executor failure and
the billing fallback chain never fires. This module replaces that with a
two-level, declarative classification:

  1. HTTP status code → coarse semantics (when a status is available).
  2. Declarative signal tables over the response body → fine semantics.

Crucially it separates *rate-limit* (HTTP 429, transient, wait seconds and retry
the SAME provider) from *quota-exhausted* (period cap hit — wait hours/days, so
fall back to the next provider instead). Treating every 429 as "wait 60s" burns
calls and alerts; treating a quota-exhaustion as a plain failure never triggers
fallback.
"""

from __future__ import annotations

import json
import re


class ErrorType:
    """Normalized provider-error categories (fixed vocabulary)."""

    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    UNAUTHORIZED = "unauthorized"
    ACCOUNT_DEACTIVATED = "account_deactivated"
    OAUTH_INVALID_TOKEN = "oauth_invalid_token"
    FORBIDDEN = "forbidden"
    CONTEXT_OVERFLOW = "context_overflow"
    SERVER_ERROR = "server_error"
    EMPTY_CONTENT = "empty_content"


# Terminal billing states: the credentials cannot serve *any* request until the
# operator tops up / the period rolls over. AgentRunner treats these as a signal
# to skip to the next executor in the billing fallback chain.
TERMINAL_BILLING_TYPES = frozenset(
    {ErrorType.QUOTA_EXHAUSTED, ErrorType.ACCOUNT_DEACTIVATED}
)


# ─── Signal tables (ported from OmniRoute accountFallback.ts) ────────────────
# Matching is substring-based, case-insensitive: the signal is contained in the
# error body. VOLY's original `_BILLING_PATTERNS` are folded in so detection
# never regresses.
_CREDITS_EXHAUSTED_SIGNALS: tuple[str, ...] = (
    # OmniRoute
    "insufficient_quota",
    "billing_hard_limit_reached",
    "exceeded your current quota",
    "exceeded your current usage quota",
    "credit_balance_too_low",
    "your credit balance is too low",
    "credits exhausted",
    "out of credits",
    "payment required",
    "free tier of the model has been exhausted",
    "insufficient balance",
    "insufficient_balance",
    "insufficient account balance",
    # VOLY originals (kept for backward compatibility)
    "credit balance is too low",
    "insufficient credits",
    "billing error",
    "billing issue",
    "billing problem",
    "update your billing",
    "billing details required",
)

_ACCOUNT_DEACTIVATED_SIGNALS: tuple[str, ...] = (
    "account_deactivated",
    "account has been deactivated",
    "account has been disabled",
    "your account has been suspended",
    "this account is deactivated",
    "verify your account to continue",
    "this service has been disabled in this account for violation",
    "this service has been disabled in this account",
)

_OAUTH_INVALID_TOKEN_SIGNALS: tuple[str, ...] = (
    "invalid authentication credentials",
    "oauth 2",
    "login cookie",
    "valid authentication credential",
    "invalid credentials",
)

# 429 disambiguation: a bare 429 is a rate-limit; only an explicit keyword makes
# it a long-period quota exhaustion. Kept specific on purpose (a bare
# "quota reached" would also flag transient per-minute limits).
_QUOTA_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"daily.*limit",
        r"daily.*quota",
        r"per.?day.*limit",
        r"monthly.*limit",
        r"monthly.*quota",
        r"per.?month.*limit",
        r"quota.*exceed",
        r"exceed.*quota",
        r"insufficient.*quota",
        r"billing.*cap",
        r"credit.*exhaust",
        r"out of credits",
        r"hard.?limit",
        r"plan.*limit",
        r"individual quota reached",
        r"enable overages",
        r"insufficient_g1_credits_balance",
    )
)

_CONTEXT_OVERFLOW_REGEX = re.compile(
    "|".join(
        (
            "context overflow",
            "prompt too large",
            "context window",
            "maximum context",
            "exceeds context",
            "input too long",
            "token limit",
            "too many tokens",
            "context length",
            "exceed.*context",
            "messages exceed",
        )
    ),
    re.IGNORECASE,
)

# A bare "402" substring matches unrelated numbers (ports, PIDs, line numbers)
# in free-form CLI error text. Only trust it in explicit HTTP-status framing or
# right next to "payment required".
_HTTP_402_REGEX = re.compile(
    r"\b(?:http|https|status(?:\s*code)?|error\s*code|code)\s*[:#]?\s*402\b"
    r"|\b402\b\s*[:\-]?\s*payment required",
    re.IGNORECASE,
)

# Terminal stop signals where empty content is a legitimate successful completion
# (truncated at token limit, or a tool-call turn) — NOT a silent fake success.
_LEGIT_EMPTY_CLAUDE_STOP = frozenset({"max_tokens", "tool_use"})
_LEGIT_EMPTY_OPENAI_FINISH = frozenset({"length", "tool_calls"})


def _to_text(body: object) -> str:
    """Coerce an unknown body to a scannable string (JSON for dict/list)."""
    if isinstance(body, str):
        return body
    if body is None:
        return ""
    try:
        return json.dumps(body, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


# ─── Predicate helpers ───────────────────────────────────────────────────────
def is_credits_exhausted(text: str) -> bool:
    low = text.lower()
    return any(sig in low for sig in _CREDITS_EXHAUSTED_SIGNALS)


def is_account_deactivated(text: str) -> bool:
    low = text.lower()
    return any(sig in low for sig in _ACCOUNT_DEACTIVATED_SIGNALS)


def is_oauth_invalid_token(text: str) -> bool:
    low = text.lower()
    return any(sig in low for sig in _OAUTH_INVALID_TOKEN_SIGNALS)


def is_daily_quota_exhausted(text: str) -> bool:
    low = text.lower()
    return (
        "today's quota" in low
        or "daily quota" in low
        or "try again tomorrow" in low
    )


def looks_like_quota_exhausted(body: object) -> bool:
    """True if a 429 body carries an explicit long-period quota keyword."""
    text = _to_text(body)
    return bool(text) and any(pat.search(text) for pat in _QUOTA_PATTERNS)


def is_context_overflow(text: str) -> bool:
    return bool(_CONTEXT_OVERFLOW_REGEX.search(text or ""))


def is_empty_content_response(body: object) -> bool:
    """Detect a "fake success": HTTP 200 with no usable content.

    Guards against false positives that a naive emptiness check would produce:
    an empty payload with a terminal ``stop_reason`` of ``max_tokens`` /
    ``tool_use`` (Claude) or ``finish_reason`` ``length`` / ``tool_calls``
    (OpenAI) is a *legitimate* completion, not a silent failure. This matters
    for the multi-agent path where sub-agents make tool calls.
    """
    if not isinstance(body, dict):
        return False

    choices = body.get("choices")
    if isinstance(choices, list):
        if not choices:
            return True
        first = choices[0]
        if not isinstance(first, dict):
            return True
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}

        finish_reason = first.get("finish_reason")
        if isinstance(finish_reason, str) and finish_reason in _LEGIT_EMPTY_OPENAI_FINISH:
            return False

        content = message.get("content", delta.get("content"))
        reasoning = message.get("reasoning_content", delta.get("reasoning_content"))
        tool_calls = message.get("tool_calls") or delta.get("tool_calls")

        has_content = content not in (None, "")
        has_reasoning = reasoning not in (None, "")
        has_tools = isinstance(tool_calls, list) and len(tool_calls) > 0
        return not (has_content or has_reasoning or has_tools)

    content = body.get("content")
    if isinstance(content, list):
        if content:
            return False
        stop_reason = body.get("stop_reason")
        stop = stop_reason if isinstance(stop_reason, str) else ""
        return stop not in _LEGIT_EMPTY_CLAUDE_STOP

    text = body.get("text")
    if isinstance(text, str):
        return text.strip() == ""

    # VOLY's normalized provider result: {"content": <str>, "stop_reason": <str>}.
    # A non-empty string is a real answer; an empty one is only a fake success
    # when the stop reason is NOT a legitimate terminal (max_tokens / tool_use /
    # length / tool_calls) — those carry the propagated stop_reason and must not
    # trigger fallback.
    if "content" in body:
        content = body.get("content")
        if content not in (None, ""):
            return False
        stop_reason = body.get("stop_reason")
        stop = stop_reason if isinstance(stop_reason, str) else ""
        return stop not in (_LEGIT_EMPTY_CLAUDE_STOP | _LEGIT_EMPTY_OPENAI_FINISH)

    return False


def classify_provider_error(
    status_code: int | None,
    body: object,
    provider: str | None = None,
) -> str | None:
    """Classify a provider failure into an :class:`ErrorType`, or ``None``.

    ``status_code`` may be ``None`` for subprocess CLI executors that only
    surface an error string; classification then relies on the signal tables.
    """
    text = _to_text(body)
    credits = is_credits_exhausted(text)
    deactivated = is_account_deactivated(text)
    oauth_invalid = is_oauth_invalid_token(text)

    # Status-code-driven semantics (when available).
    if status_code is not None:
        if credits and status_code in (400, 402, 403):
            return ErrorType.QUOTA_EXHAUSTED
        if status_code == 429:
            if credits or looks_like_quota_exhausted(text) or is_daily_quota_exhausted(text):
                return ErrorType.QUOTA_EXHAUSTED
            return ErrorType.RATE_LIMITED
        if status_code == 401:
            if oauth_invalid:
                return ErrorType.OAUTH_INVALID_TOKEN
            return (
                ErrorType.ACCOUNT_DEACTIVATED if deactivated else ErrorType.UNAUTHORIZED
            )
        if status_code == 402:
            return ErrorType.QUOTA_EXHAUSTED
        if status_code == 403:
            if deactivated:
                return ErrorType.ACCOUNT_DEACTIVATED
            return ErrorType.FORBIDDEN
        if status_code >= 500:
            return ErrorType.SERVER_ERROR
        if status_code == 400 and is_context_overflow(text):
            return ErrorType.CONTEXT_OVERFLOW

    # Text-only fallback (subprocess CLIs, or unrecognized status).
    if deactivated:
        return ErrorType.ACCOUNT_DEACTIVATED
    if credits:
        return ErrorType.QUOTA_EXHAUSTED
    if looks_like_quota_exhausted(text) or is_daily_quota_exhausted(text):
        return ErrorType.QUOTA_EXHAUSTED
    if oauth_invalid:
        return ErrorType.OAUTH_INVALID_TOKEN
    if is_context_overflow(text):
        return ErrorType.CONTEXT_OVERFLOW
    return None


def is_terminal_billing_error(text: str, status_code: int | None = None) -> bool:
    """True when the error means "these credentials are out of budget".

    This is the successor to VOLY's flat ``_is_billing_error``: it fires only for
    terminal quota/account states, NOT for transient rate-limits (a 429 that is
    merely "too many requests/min" must not skip the executor to the next in the
    billing chain).
    """
    # A bare HTTP 402 is always terminal even without a recognizable body.
    if status_code == 402:
        return True
    if _HTTP_402_REGEX.search(text) or "payment required" in text.lower():
        return True
    return classify_provider_error(status_code, text) in TERMINAL_BILLING_TYPES
