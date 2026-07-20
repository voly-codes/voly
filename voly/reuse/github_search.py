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
    # common RU stop-ish stems (matched after lowercasing)
    "для", "при", "или", "как", "что", "это", "все", "без", "над", "под",
    "создай", "сделай", "нужно", "надо", "полный", "полноценн",
})

# Normalize dotted tech tokens before keyword extraction (three.js → threejs).
_TECH_NORMALIZE = (
    (re.compile(r"\bthree\.js\b", re.I), "threejs"),
    (re.compile(r"\breact\.js\b", re.I), "react"),
    (re.compile(r"\bnode\.js\b", re.I), "nodejs"),
    (re.compile(r"\bnext\.js\b", re.I), "nextjs"),
    (re.compile(r"\bvue\.js\b", re.I), "vue"),
    (re.compile(r"\bpixi\.js\b", re.I), "pixijs"),
    (re.compile(r"\bbabylon\.js\b", re.I), "babylonjs"),
)

# Small RU→EN glossary so Cyrillic-only tasks still produce GitHub-usable queries.
# Project-agnostic tech/domain stems only (substring match on token).
_RU_EN = (
    ("танчик", "tank"),
    ("танки", "tank"),
    ("танк", "tank"),
    ("браузер", "browser"),
    ("игра", "game"),
    ("игр", "game"),
    ("физик", "physics"),
    ("изометр", "isometric"),
    ("трёхмер", "3d"),
    ("трехмер", "3d"),
    ("производств", "manufacturing"),
    ("завод", "factory"),
    ("датчик", "sensor"),
    ("симулятор", "simulation"),
    ("симуляц", "simulation"),
    ("аркад", "arcade"),
    ("левел", "level"),
    ("уровен", "level"),
    ("мультиплеер", "multiplayer"),
    ("авторизац", "auth"),
    ("аутентификац", "auth"),
    ("мидлвар", "middleware"),
    ("middleware", "middleware"),
)


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
    """Deterministic keyword query from task text (no LLM).

    Handles Latin + common Cyrillic tech terms. Prefers a short AND query
    (name/description only) — full readme AND of 6 tokens often returns zero hits.
    """
    text = task or ""
    for pat, repl in _TECH_NORMALIZE:
        text = pat.sub(repl, text)
    lower = text.lower()

    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", lower)
    cyr = re.findall(r"[а-яё]{3,}", lower)

    # Domain terms from Cyrillic first — otherwise Latin noise (hud, threejs)
    # crowds out tank/game and GitHub returns unrelated high-star hits.
    mapped: list[str] = []
    for token in cyr:
        if token in _STOP:
            continue
        for stem, en in _RU_EN:
            if stem in token and en not in mapped:
                mapped.append(en)
                break

    stack: list[str] = []
    for t in latin:
        if t in _STOP or t in mapped or t in stack:
            continue
        stack.append(t)

    # Keep room for 1–2 stack tokens (threejs, fastapi) after domain terms.
    keywords = (mapped[:3] + stack)[:5]
    if not keywords:
        # Last resort: avoid the old "library utility" mega-list query.
        keywords = ["example", "template"] if not cyr else ["game", "javascript"]

    lang = language or infer_language(task)
    # Shorter AND = more recall. Qualifier without readme (readme AND is too strict).
    parts = [" ".join(keywords[:4]), "in:name,description"]
    if lang:
        parts.append(f"language:{lang}")
    return " ".join(parts)


def infer_language(task: str) -> str:
    """Best-effort GitHub language: filter from task text (empty if unknown)."""
    t = (task or "").lower()
    for pat, repl in _TECH_NORMALIZE:
        t = pat.sub(repl, t)
    rules: list[tuple[tuple[str, ...], str]] = [
        (("typescript", "threejs", "pixijs", "babylonjs", "react", "nextjs", "svelte", "vue"), "TypeScript"),
        (("javascript", "nodejs", "webgl", "canvas", "html5"), "JavaScript"),
        (("fastapi", "django", "flask", "pytest", "python"), "Python"),
        (("golang", " go "), "Go"),
        (("rust", "cargo"), "Rust"),
        (("kotlin",), "Kotlin"),
        (("swift",), "Swift"),
        (("csharp", "c#", ".net", "unity"), "C#"),
    ]
    for keys, lang in rules:
        if any(k in t for k in keys):
            return lang
    return ""


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


def _parse_repo_hits(items: list[dict[str, Any]], *, limit: int) -> list[RepoHit]:
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


def _search_once(
    q: str,
    *,
    limit: int,
    token: str,
    sort: str,
) -> list[RepoHit]:
    params = urllib.parse.urlencode({
        "q": q,
        "sort": sort,
        "order": "desc",
        "per_page": min(max(limit, 1), 30),
    })
    url = f"{_API}/search/repositories?{params}"
    data = _request_json(url, token=token)
    return _parse_repo_hits(list(data.get("items") or []), limit=limit)


def search_repositories(
    query: str,
    *,
    limit: int = 5,
    min_stars: int = 0,
    token: str = "",
    sort: str = "stars",
) -> list[RepoHit]:
    """Search GitHub repositories. Requires network; token recommended for rate limits.

    If the strict query returns nothing, retries with relaxed variants (drop
    in:-qualifiers, then fewer keywords) so auto-reuse does not die on AND-miss.
    """
    q = query.strip()
    if min_stars > 0 and "stars:" not in q:
        q = f"{q} stars:>={min_stars}"

    hits = _search_once(q, limit=limit, token=token, sort=sort)
    if hits:
        return hits

    # Retry 1: drop in:name,description(,readme) qualifiers.
    relaxed = re.sub(r"\bin:\S+", "", q)
    relaxed = re.sub(r"\s+", " ", relaxed).strip()
    if relaxed != q:
        _log.debug("search retry without in: qualifier: %s", relaxed)
        hits = _search_once(relaxed, limit=limit, token=token, sort=sort)
        if hits:
            return hits

    # Retry 2: keep stars + first 2 keyword tokens only.
    stars_m = re.search(r"stars:>=?\d+", relaxed)
    stars_part = stars_m.group(0) if stars_m else ""
    lang_m = re.search(r"language:\S+", relaxed)
    lang_part = lang_m.group(0) if lang_m else ""
    bare = re.sub(r"stars:>=?\d+", "", relaxed)
    bare = re.sub(r"language:\S+", "", bare)
    bare = re.sub(r"\s+", " ", bare).strip()
    words = bare.split()
    if len(words) > 2:
        short = " ".join(words[:2])
        parts = [p for p in (short, stars_part, lang_part) if p]
        short_q = " ".join(parts)
        _log.debug("search retry with short query: %s", short_q)
        hits = _search_once(short_q, limit=limit, token=token, sort=sort)
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
