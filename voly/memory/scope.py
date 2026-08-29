"""Deterministic Cloudflare Agent Memory profile isolation."""

from __future__ import annotations

import re
from pathlib import Path

from voly.memory.strategic import project_scope_id

_SAFE = re.compile(r"[^a-z0-9_-]+")


def truncate_utf8(value: str, max_bytes: int) -> str:
    """Bound text by UTF-8 bytes without returning a partial code point."""
    return value.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def project_memory_profile(cwd: str | Path) -> str:
    """Return a stable, readable profile name within Cloudflare's 100-char limit."""
    root = Path(cwd).expanduser().resolve()
    slug = _SAFE.sub("-", root.name.lower()).strip("-") or "project"
    slug = slug[:60].rstrip("-") or "project"
    return f"project-{slug}-{project_scope_id(root)[:12]}"


def resolve_memory_profile(
    configured_profile: str,
    *,
    mode: str = "project",
    cwd: str | Path | None = None,
) -> str:
    """Resolve explicit or project-scoped profile; project mode fails closed without cwd."""
    selected_mode = (mode or "project").strip().lower()
    if selected_mode == "explicit":
        profile = (configured_profile or "default").strip()
    elif selected_mode == "project":
        profile = project_memory_profile(cwd) if cwd and str(cwd).strip() else ""
    else:
        raise ValueError("agent_memory_profile_mode must be project or explicit")
    if len(profile) > 100:
        raise ValueError("Agent Memory profile exceeds 100 characters")
    return profile
