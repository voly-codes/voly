"""Tech version registry.

Single source of truth for framework/library versions injected into agent prompts
so agents don't guess or search the web for current version numbers.

Versions are pinned at release time and updated manually on major releases.
Last updated: 2025-07.
"""

from __future__ import annotations

import re
from typing import Any

# ── Registry data ─────────────────────────────────────────────────────────────

# Each entry:
#   name        canonical ID
#   label       display name
#   versions    [latest, N-1, N-2] — first is the default
#   category    frontend | backend | language | infra | database | testing
#   keywords    task-description tokens that trigger detection (lowercase)
#   companions  other registry IDs to suggest alongside this one
#   notes       short "what changed in latest" for agent context

_REGISTRY: list[dict[str, Any]] = [
    # ── Frontend frameworks ────────────────────────────────────────────────
    {
        "name": "svelte",
        "label": "Svelte",
        "versions": ["5.33.0", "5.20.0", "4.2.19"],
        "category": "frontend",
        "keywords": ["svelte", "sveltekit", "runes"],
        "companions": ["sveltekit", "typescript", "vite", "vitest"],
        "notes": "v5: runes API ($state, $derived, $props, $effect) replaces reactive stores and Options API entirely.",
    },
    {
        "name": "sveltekit",
        "label": "SvelteKit",
        "versions": ["2.21.0", "2.15.0", "1.30.4"],
        "category": "frontend",
        "keywords": ["sveltekit", "svelte kit"],
        "companions": ["svelte", "typescript", "vite"],
        "notes": "v2: file-based routing, server load functions, +page.server.ts pattern.",
    },
    {
        "name": "react",
        "label": "React",
        "versions": ["19.1.0", "18.3.1"],
        "category": "frontend",
        "keywords": ["react", "jsx", "tsx"],
        "companions": ["typescript", "vite"],
        "notes": "v19: Server Components stable, use() hook, form actions, React Compiler (opt-in).",
    },
    {
        "name": "nextjs",
        "label": "Next.js",
        "versions": ["15.3.1", "14.2.29"],
        "category": "frontend",
        "keywords": ["next.js", "nextjs", "next js"],
        "companions": ["react", "typescript"],
        "notes": "v15: Turbopack stable, React 19 first-class, partial prerendering.",
    },
    {
        "name": "vue",
        "label": "Vue",
        "versions": ["3.5.13", "3.4.21"],
        "category": "frontend",
        "keywords": ["vue", "vuejs", "vue.js"],
        "companions": ["typescript", "vite"],
        "notes": "v3.5: useTemplateRef(), improved reactivity, deferred hydration.",
    },
    {
        "name": "nuxt",
        "label": "Nuxt",
        "versions": ["3.16.2", "3.15.4"],
        "category": "frontend",
        "keywords": ["nuxt", "nuxtjs", "nuxt.js"],
        "companions": ["vue", "typescript"],
        "notes": "v3.16: Nitro 2.10, improved dev server, Vite 6 support.",
    },
    # ── Languages ─────────────────────────────────────────────────────────
    {
        "name": "typescript",
        "label": "TypeScript",
        "versions": ["5.8.3", "5.7.3", "5.4.5"],
        "category": "language",
        "keywords": ["typescript", "ts", ".ts", ".tsx"],
        "companions": [],
        "notes": "v5.8: strict optional chaining, improved narrowing, --erasableSyntaxOnly flag.",
    },
    {
        "name": "python",
        "label": "Python",
        "versions": ["3.12.8", "3.13.2", "3.11.12"],
        "category": "language",
        "keywords": ["python", "py", "fastapi", "django", "flask", "pytest", "pydantic"],
        "companions": [],
        "notes": "3.12 is LTS production default. 3.13 adds JIT (opt-in) and free-threaded mode.",
    },
    {
        "name": "node",
        "label": "Node.js",
        "versions": ["22.15.0", "20.19.0"],
        "category": "language",
        "keywords": ["node", "nodejs", "node.js", "npm", "npx"],
        "companions": [],
        "notes": "v22 is LTS (Active). v20 is LTS (Maintenance).",
    },
    # ── Backend frameworks ─────────────────────────────────────────────────
    {
        "name": "fastapi",
        "label": "FastAPI",
        "versions": ["0.115.12", "0.110.3"],
        "category": "backend",
        "keywords": ["fastapi", "fast api", "fastapi backend"],
        "companions": ["python", "pydantic", "uvicorn", "pytest", "httpx"],
        "notes": "0.115: Pydantic v2 native, lifespan context managers, annotated dependencies.",
    },
    {
        "name": "django",
        "label": "Django",
        "versions": ["5.2.1", "4.2.20"],
        "category": "backend",
        "keywords": ["django", "django rest", "drf"],
        "companions": ["python", "pytest"],
        "notes": "v5.2: async ORM, LoginRequiredMiddleware, composite PKs.",
    },
    {
        "name": "flask",
        "label": "Flask",
        "versions": ["3.1.0", "3.0.3"],
        "category": "backend",
        "keywords": ["flask"],
        "companions": ["python", "pytest"],
        "notes": "v3.1: sync/async unified, improved type hints.",
    },
    {
        "name": "pydantic",
        "label": "Pydantic",
        "versions": ["2.11.5", "2.10.6", "1.10.21"],
        "category": "backend",
        "keywords": ["pydantic"],
        "companions": ["python"],
        "notes": "v2: 5–50× faster validation, model_validator, field_validator decorators.",
    },
    {
        "name": "uvicorn",
        "label": "Uvicorn",
        "versions": ["0.34.2", "0.32.1"],
        "category": "backend",
        "keywords": ["uvicorn"],
        "companions": ["fastapi", "python"],
        "notes": "v0.34: HTTP/2 via h2, improved worker lifecycle.",
    },
    {
        "name": "sqlalchemy",
        "label": "SQLAlchemy",
        "versions": ["2.0.40", "1.4.54"],
        "category": "backend",
        "keywords": ["sqlalchemy", "sqla", "orm"],
        "companions": ["python"],
        "notes": "v2: fully typed ORM, async-first, select() style replaces Query.",
    },
    {
        "name": "httpx",
        "label": "httpx",
        "versions": ["0.28.1", "0.27.2"],
        "category": "testing",
        "keywords": ["httpx"],
        "companions": ["python", "pytest"],
        "notes": "Async HTTP client; used with FastAPI TestClient for integration tests.",
    },
    # ── Build / Testing ───────────────────────────────────────────────────
    {
        "name": "vite",
        "label": "Vite",
        "versions": ["6.3.5", "5.4.19"],
        "category": "build",
        "keywords": ["vite"],
        "companions": [],
        "notes": "v6: Rolldown bundler (Rust), environment API, improved HMR.",
    },
    {
        "name": "vitest",
        "label": "Vitest",
        "versions": ["3.2.4", "2.1.9"],
        "category": "testing",
        "keywords": ["vitest"],
        "companions": [],
        "notes": "v3: browser mode stable, workspace projects, improved coverage.",
    },
    {
        "name": "pytest",
        "label": "pytest",
        "versions": ["8.4.0", "7.4.4"],
        "category": "testing",
        "keywords": ["pytest"],
        "companions": ["python"],
        "notes": "v8.4: improved fixture resolution, assert rewriting, asyncio-mode=auto default.",
    },
    # ── Database ──────────────────────────────────────────────────────────
    {
        "name": "postgresql",
        "label": "PostgreSQL",
        "versions": ["17.4", "16.8"],
        "category": "database",
        "keywords": ["postgresql", "postgres", "psql", "pg"],
        "companions": [],
        "notes": "v17: incremental sort, logical replication improvements.",
    },
    {
        "name": "redis",
        "label": "Redis",
        "versions": ["7.4.2", "7.2.7"],
        "category": "database",
        "keywords": ["redis", "cache", "queue"],
        "companions": [],
        "notes": "v7.4: LPOS improvements, TLS 1.3, modules API v7.",
    },
    # ── Infra ─────────────────────────────────────────────────────────────
    {
        "name": "docker",
        "label": "Docker",
        "versions": ["28.0.1", "27.5.1"],
        "category": "infra",
        "keywords": ["docker", "dockerfile", "docker-compose", "compose"],
        "companions": [],
        "notes": "v28: BuildKit default, compose v2 (docker compose), improved networking.",
    },
    # ── Game engines / frameworks ─────────────────────────────────────────
    {
        "name": "pygame",
        "label": "Pygame",
        "versions": ["2.6.1", "2.5.2"],
        "category": "frontend",
        "keywords": ["pygame", "python game", "2d game python", "arcade"],
        "companions": ["python", "pytest"],
        "notes": "2.6: SDL2-based 2D sprites, event loop, sound. Best for Python 2D/retro games.",
    },
    {
        "name": "godot",
        "label": "Godot",
        "versions": ["4.4.1", "3.6.0"],
        "category": "frontend",
        "keywords": ["godot", "gdscript", "godot engine", "godot4"],
        "companions": [],
        "notes": "v4: GDScript 2.0, Vulkan renderer, C# support. v3: stable, large community.",
    },
    {
        "name": "phaser",
        "label": "Phaser",
        "versions": ["3.88.2", "3.80.1"],
        "category": "frontend",
        "keywords": ["phaser", "phaser3", "html5 game", "browser game", "canvas game"],
        "companions": ["typescript", "vite"],
        "notes": "v3: WebGL/Canvas, arcade physics, tilemaps, asset loader. Best for browser 2D games.",
    },
    {
        "name": "love2d",
        "label": "LÖVE 2D",
        "versions": ["11.5", "11.4"],
        "category": "frontend",
        "keywords": ["love2d", "lua game", "löve", "love framework"],
        "companions": [],
        "notes": "Lua-based 2D framework. Lightweight, cross-platform, good for indie/retro games.",
    },
    {
        "name": "unity",
        "label": "Unity",
        "versions": ["6000.0.47", "2022.3.62", "2021.3.47", "2020.3.48"],
        "category": "frontend",
        "keywords": ["unity", "monobehaviour", "gameobject", "hdrp", "urp", "unityengine", "unity3d", "prefab"],
        "companions": ["csharp"],
        "notes": (
            "Unity 6 (6000.x): ECS/DOTS stable, new Physics, Render Graph. "
            "2022.3 LTS: recommended for production. "
            "IMPORTANT: every new .cs file needs a sibling .meta file with a unique GUID — "
            "missing .meta breaks script references in the Editor. "
            "Tests run via Unity Test Runner (NUnit) inside the Editor, NOT pytest."
        ),
    },
    {
        "name": "csharp",
        "label": "C#",
        "versions": ["12.0", "11.0", "9.0"],
        "category": "language",
        "keywords": ["csharp", "c#", ".cs", "dotnet", "monobehaviour", "scriptableobject"],
        "companions": [],
        "notes": "C# 12 (Unity 2022+): record structs, default interface members, pattern matching.",
    },
]

# Build lookup index by name
_BY_NAME: dict[str, dict[str, Any]] = {e["name"]: e for e in _REGISTRY}


# ── Detection logic ───────────────────────────────────────────────────────────

def detect_unity_version(cwd: str) -> str | None:
    """Read Unity version from ProjectSettings/ProjectVersion.txt if present."""
    import os
    version_file = os.path.join(os.path.expanduser(cwd), "ProjectSettings", "ProjectVersion.txt")
    try:
        with open(version_file, encoding="utf-8") as f:
            for line in f:
                if line.startswith("m_EditorVersion:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def detect_tech_from_task(task: str, cwd: str = "") -> list[dict[str, Any]]:
    """Deterministic keyword-based detection of tech stack from task description.

    When cwd points to a Unity project (ProjectSettings/ProjectVersion.txt exists),
    the exact Editor version is read and used instead of the registry default.

    Returns a list of registry entries (with defaults set) for the detected stack,
    companions included and deduplicated, ordered by relevance.
    """
    task_lower = task.lower()
    # Tokenise: split on non-word chars, keep tokens ≥ 2 chars
    tokens = set(re.split(r"[^\w.]+", task_lower))

    matched: dict[str, int] = {}  # name → hit count

    for entry in _REGISTRY:
        hits = 0
        for kw in entry["keywords"]:
            kw_tok = kw.replace(".", "").replace(" ", "")
            # Short tokens (≤ 3 chars) must be whole words to avoid substring false-positives
            # (e.g. "ts" in "tests", "py" in "copy").
            if len(kw_tok) <= 3:
                if kw_tok in tokens:
                    hits += 1
            else:
                if kw in task_lower:
                    hits += 1
        if hits:
            matched[entry["name"]] = hits

    if not matched:
        return []

    # Determine which language ecosystems are present in direct matches.
    _PYTHON_ECOSYSTEM = frozenset({"python", "fastapi", "django", "flask", "sqlalchemy",
                                   "pydantic", "uvicorn", "pytest", "httpx", "alembic"})
    _JS_ECOSYSTEM = frozenset({"node", "typescript", "react", "nextjs", "vue", "nuxt",
                                "svelte", "sveltekit", "vite", "vitest"})
    has_python = bool(set(matched) & _PYTHON_ECOSYSTEM)
    has_js = bool(set(matched) & _JS_ECOSYSTEM)

    def _companion_allowed(companion: str) -> bool:
        """Reject companions that belong to a different ecosystem than what's detected."""
        if companion in _PYTHON_ECOSYSTEM and not has_python:
            return False
        if companion in _JS_ECOSYSTEM and not has_js:
            return False
        return True

    # Expand companions one level
    expanded: dict[str, int] = dict(matched)
    for name, score in list(matched.items()):
        for companion in (_BY_NAME.get(name) or {}).get("companions", []):
            if companion not in expanded and _companion_allowed(companion):
                expanded[companion] = max(score - 1, 1)

    # Sort: direct matches first, companions second; within each by hit count desc
    def _sort_key(name: str) -> tuple[int, int]:
        is_companion = name not in matched
        return (int(is_companion), -expanded[name])

    ordered = sorted(expanded.keys(), key=_sort_key)
    results = [_entry_with_defaults(_BY_NAME[n]) for n in ordered if n in _BY_NAME]

    # For Unity projects: override version with the actual Editor version from disk.
    if cwd and any(r["name"] == "unity" for r in results):
        actual = detect_unity_version(cwd)
        if actual:
            entry = _BY_NAME["unity"]
            known = list(entry["versions"])
            if actual not in known:
                known.insert(0, actual)
            results = [
                {**r, "version": actual, "versions": known} if r["name"] == "unity" else r
                for r in results
            ]

    return results


def _entry_with_defaults(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": entry["name"],
        "label": entry["label"],
        "version": entry["versions"][0],
        "versions": list(entry["versions"]),
        "category": entry["category"],
        "notes": entry.get("notes", ""),
    }


def get_registry() -> list[dict[str, Any]]:
    """Return the full tech registry for CF/API exposure."""
    return [_entry_with_defaults(e) for e in _REGISTRY]


# ── Category definitions ──────────────────────────────────────────────────────

_CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "web",
        "label": "Web Frontend",
        "description": "Browser apps and dashboards — React, Svelte, Vue, Next.js",
        "techs": ["svelte", "sveltekit", "react", "nextjs", "vue", "nuxt", "typescript", "vite", "vitest"],
    },
    {
        "id": "backend",
        "label": "Python Backend",
        "description": "APIs and services — FastAPI, Django, Flask",
        "techs": ["fastapi", "django", "flask", "python", "pydantic", "uvicorn", "pytest", "httpx", "postgresql"],
    },
    {
        "id": "game",
        "label": "Game",
        "description": "2D/3D games — Pygame, Phaser, Godot, Unity",
        "techs": ["pygame", "phaser", "godot", "unity", "love2d", "python", "typescript", "csharp"],
    },
    {
        "id": "cli",
        "label": "CLI / Script",
        "description": "Command-line tools and automation scripts",
        "techs": ["python", "node", "typescript", "pytest"],
    },
    {
        "id": "data",
        "label": "Data / ML",
        "description": "Data pipelines, analysis, machine learning",
        "techs": ["python", "pytest", "postgresql", "redis", "httpx"],
    },
]


def get_categories() -> list[dict[str, Any]]:
    """Return project categories with their resolved tech entries for the fallback picker."""
    return [
        {
            "id": cat["id"],
            "label": cat["label"],
            "description": cat["description"],
            "entries": [_entry_with_defaults(_BY_NAME[n]) for n in cat["techs"] if n in _BY_NAME],
        }
        for cat in _CATEGORIES
    ]


def tech_stack_context(selected: list[dict[str, Any]]) -> str:
    """Format a confirmed tech stack as a constraint block for agent prompts."""
    if not selected:
        return ""
    lines = ["**Approved tech stack — use these exact versions:**"]
    for item in selected:
        note = f" ({item['notes']})" if item.get("notes") else ""
        lines.append(f"- {item['label']}: {item['version']}{note}")
    lines.append(
        "Do not install or suggest newer versions. "
        "Do not upgrade pinned versions during implementation."
    )

    names = {item["name"] for item in selected}
    if "unity" in names:
        lines += [
            "",
            "**Unity project rules (MANDATORY):**",
            "- Every new .cs file MUST have a sibling .meta file containing a unique GUID"
            " (format: `guid: <32 hex chars>`). Without it the Editor loses the script reference.",
            "- Do NOT use pytest, npm test, or any non-Unity test runner.",
            "- Tests run via Unity Test Runner (NUnit) inside the Editor — not from CLI.",
            "- When writing a plan, set tester_command to:"
            " `echo 'Run Unity Test Runner manually in Editor'`",
        ]

    return "\n".join(lines)
