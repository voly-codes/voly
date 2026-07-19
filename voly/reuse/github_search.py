"""GitHub REST search client for repositories (and optional code search)."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("voly.reuse.github")

_API = "https://api.github.com"
_STOP = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "using",
    "create", "add", "make", "implement", "build", "write", "fix", "update",
    "please", "need", "want", "should", "could", "would", "have", "been",
})


@dataclass
class RepoHit:
    full_name: str
    html_url: str
    clone_url: str
    description: str
    stars: int
    language: str
    license_spdx: str
    default_branch: str
    topics: list[str]


class GitHubSearchError(RuntimeError):
    pass


def github_token() -> str:
    return (
        os.environ.get("GITHUB_TOKEN", "").strip()
        or os.environ.get("GH_TOKEN", "").strip()
    )


def task_to_query(task: str, *, language: str = "") -> str:
    """Deterministic keyword query from task text (no LLM)."""
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", task.lower())
    keywords: list[str] = []
    for t in tokens:
        if t in _STOP or t in keywords:
            continue
        keywords.append(t)
        if len(keywords) >= 6:
            break
    if not keywords:
        keywords = ["library", "utility"]
    parts = [" ".join(keywords), "in:name,description,readme"]
    if language:
        parts.append(f"language:{language}")
    return " ".join(parts)


def _request_json(
    url: str,
    *,
    token: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "voly-reuse",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    tok = token or github_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise GitHubSearchError(f"GitHub API {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise GitHubSearchError(f"GitHub network error: {e}") from e


def search_repositories(
    query: str,
    *,
    limit: int = 5,
    min_stars: int = 0,
    token: str = "",
    sort: str = "stars",
) -> list[RepoHit]:
    """Search GitHub repositories. Requires network; token recommended for rate limits."""
    q = query.strip()
    if min_stars > 0 and "stars:" not in q:
        q = f"{q} stars:>={min_stars}"
    params = urllib.parse.urlencode({
        "q": q,
        "sort": sort,
        "order": "desc",
        "per_page": min(max(limit, 1), 30),
    })
    url = f"{_API}/search/repositories?{params}"
    data = _request_json(url, token=token)
    items = data.get("items") or []
    hits: list[RepoHit] = []
    for item in items:
        lic = item.get("license") or {}
        spdx = ""
        if isinstance(lic, dict):
            spdx = (lic.get("spdx_id") or lic.get("key") or "") or ""
            if spdx in ("NOASSERTION", "OTHER"):
                spdx = ""
        hits.append(
            RepoHit(
                full_name=item.get("full_name") or "",
                html_url=item.get("html_url") or "",
                clone_url=item.get("clone_url") or item.get("html_url") or "",
                description=(item.get("description") or "")[:500],
                stars=int(item.get("stargazers_count") or 0),
                language=item.get("language") or "",
                license_spdx=spdx.lower() if spdx else "",
                default_branch=item.get("default_branch") or "main",
                topics=list(item.get("topics") or []),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def get_repo(full_name: str, *, token: str = "") -> RepoHit:
    """Fetch a single repository by owner/repo."""
    url = f"{_API}/repos/{full_name}"
    item = _request_json(url, token=token)
    lic = item.get("license") or {}
    spdx = ""
    if isinstance(lic, dict):
        spdx = (lic.get("spdx_id") or lic.get("key") or "") or ""
        if spdx in ("NOASSERTION", "OTHER"):
            spdx = ""
    return RepoHit(
        full_name=item.get("full_name") or full_name,
        html_url=item.get("html_url") or "",
        clone_url=item.get("clone_url") or "",
        description=(item.get("description") or "")[:500],
        stars=int(item.get("stargazers_count") or 0),
        language=item.get("language") or "",
        license_spdx=spdx.lower() if spdx else "",
        default_branch=item.get("default_branch") or "main",
        topics=list(item.get("topics") or []),
    )
