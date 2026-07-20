"""Pre-clone admission checks via GitHub API."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from voly.intelligence.schema import AdmissionResult

_log = logging.getLogger("voly.intelligence.admission")

_API = "https://api.github.com"
_GITHUB_URL = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+)",
    re.I,
)
_GITHUB_SSH = re.compile(r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/#?]+)", re.I)


@dataclass
class AdmissionConfig:
    max_repo_size_mb: float = 500
    allow_private: bool = False


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) for a GitHub URL, or None if not GitHub."""
    text = (url or "").strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    for pat in (_GITHUB_URL, _GITHUB_SSH):
        m = pat.search(text)
        if m:
            owner = m.group("owner").strip()
            repo = m.group("repo").strip().removesuffix(".git")
            if owner and repo:
                return owner, repo
    return None


def _github_token() -> str:
    return (
        os.environ.get("GITHUB_TOKEN", "").strip()
        or os.environ.get("GH_TOKEN", "").strip()
    )


def _request_repo(owner: str, repo: str) -> dict[str, Any]:
    token = _github_token()
    if not token:
        _log.warning(
            "No GITHUB_TOKEN/GH_TOKEN — using unauthenticated GitHub API (60 req/h)"
        )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "voly-intelligence",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{_API}/repos/{owner}/{repo}",
        headers=headers,
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body) if body else {}


def _days_since(iso_ts: str | None) -> int | None:
    if not iso_ts:
        return None
    try:
        pushed = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if pushed.tzinfo is None:
            pushed = pushed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - pushed.astimezone(timezone.utc)
        return max(int(delta.total_seconds() // 86400), 0)
    except (TypeError, ValueError):
        return None


def _default_result(*, allowed: bool, api_enriched: bool, reason: str | None = None) -> AdmissionResult:
    return AdmissionResult(
        allowed=allowed,
        private=False,
        archived=False,
        size_mb=0.0,
        last_commit_days_ago=None,
        stars=0,
        license_file_present=False,
        api_enriched=api_enriched,
        reason=reason,
    )


def check(url: str, config: AdmissionConfig) -> AdmissionResult:
    """Pre-clone admission gate. Non-GitHub URLs pass without API enrichment."""
    parsed = parse_github_url(url)
    if parsed is None:
        return _default_result(allowed=True, api_enriched=False)

    owner, repo = parsed
    try:
        data = _request_repo(owner, repo)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        return _default_result(
            allowed=False,
            api_enriched=False,
            reason=f"GitHub API error {e.code}: {detail}",
        )
    except urllib.error.URLError as e:
        return _default_result(
            allowed=False,
            api_enriched=False,
            reason=f"GitHub network error: {e.reason}",
        )

    private = bool(data.get("private"))
    archived = bool(data.get("archived"))
    size_mb = float(data.get("size") or 0) / 1024.0
    last_commit_days_ago = _days_since(data.get("pushed_at"))
    stars = int(data.get("stargazers_count") or 0)
    lic = data.get("license") or {}
    license_file_present = isinstance(lic, dict) and lic.get("name") is not None

    if private and not config.allow_private:
        return AdmissionResult(
            allowed=False,
            private=private,
            archived=archived,
            size_mb=size_mb,
            last_commit_days_ago=last_commit_days_ago,
            stars=stars,
            license_file_present=license_file_present,
            api_enriched=True,
            reason="private repo requires --allow-private",
        )
    if archived:
        return AdmissionResult(
            allowed=False,
            private=private,
            archived=archived,
            size_mb=size_mb,
            last_commit_days_ago=last_commit_days_ago,
            stars=stars,
            license_file_present=license_file_present,
            api_enriched=True,
            reason="repository is archived",
        )
    if size_mb > config.max_repo_size_mb:
        return AdmissionResult(
            allowed=False,
            private=private,
            archived=archived,
            size_mb=size_mb,
            last_commit_days_ago=last_commit_days_ago,
            stars=stars,
            license_file_present=license_file_present,
            api_enriched=True,
            reason="repository too large",
        )

    return AdmissionResult(
        allowed=True,
        private=private,
        archived=archived,
        size_mb=size_mb,
        last_commit_days_ago=last_commit_days_ago,
        stars=stars,
        license_file_present=license_file_present,
        api_enriched=True,
        reason=None,
    )
