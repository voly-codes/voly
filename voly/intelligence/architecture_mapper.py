"""Map repository structure to architecture data via heuristics + optional AI."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

_log = logging.getLogger("voly.intelligence.architecture_mapper")

HEURISTIC_PATTERNS: dict[str, list[str]] = {
    "python": [".py"],
    "typescript": [".ts", ".tsx"],
    "javascript": [".js", ".jsx", ".mjs"],
    "go": [".go"],
    "rust": [".rs"],
    "java": [".java"],
    "kotlin": [".kt"],
    "ruby": [".rb"],
}

FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "react": ["package.json"],
    "vue": ["package.json"],
    "next.js": ["next.config.*", "next.config.js", "next.config.ts"],
    "svelte": ["svelte.config.*"],
    "fastapi": ["requirements*.txt", "pyproject.toml"],
    "django": ["manage.py", "settings.py"],
    "flask": ["requirements*.txt", "pyproject.toml"],
    "express": ["package.json"],
    "nestjs": ["nest-cli.json"],
    "vite": ["vite.config.*"],
    "docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
}

_SKIP_DIRS = frozenset(
    {"node_modules", ".git", "__pycache__", ".venv", "dist", "build", ".tox"}
)
_ENTRY_NAMES = frozenset(
    {"main.py", "app.py", "server.py", "index.ts", "index.js", "main.ts", "main.go"}
)


def _iter_files(repo_path: Path):
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(repo_path).parts)
        if parts & _SKIP_DIRS:
            continue
        yield path


def detect_languages(repo_path: str) -> list[str]:
    """Count files per extension, return top languages by file count."""
    root = Path(repo_path)
    if not root.is_dir():
        return []
    counts: dict[str, int] = {}
    for path in _iter_files(root):
        ext = path.suffix.lower()
        for lang, exts in HEURISTIC_PATTERNS.items():
            if ext in exts:
                counts[lang] = counts.get(lang, 0) + 1
                break
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [lang for lang, _ in ranked]


def _glob_exists(root: Path, pattern: str) -> bool:
    if "*" in pattern:
        return any(root.glob(pattern))
    return (root / pattern).exists()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _npm_deps(root: Path) -> dict[str, str]:
    pkg = root / "package.json"
    if not pkg.is_file():
        return {}
    try:
        data = json.loads(_read_text(pkg))
    except json.JSONDecodeError:
        return {}
    deps: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            deps.update({str(k).lower(): str(v) for k, v in block.items()})
    return deps


def _python_manifest_text(root: Path) -> str:
    chunks: list[str] = []
    for path in sorted(root.glob("requirements*.txt")):
        chunks.append(_read_text(path))
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        chunks.append(_read_text(pyproject))
    return "\n".join(chunks).lower()


def detect_frameworks(repo_path: str) -> list[str]:
    """Check FRAMEWORK_SIGNALS file presence + content where needed."""
    root = Path(repo_path)
    if not root.is_dir():
        return []
    found: set[str] = set()
    npm = _npm_deps(root)
    py_text = _python_manifest_text(root)
    django = (root / "manage.py").is_file() or (root / "settings.py").is_file()

    if "react" in npm:
        found.add("react")
    if "vue" in npm:
        found.add("vue")
    if "express" in npm:
        found.add("express")
    if any(root.glob("next.config.*")) or (root / "next.config.js").is_file():
        found.add("next.js")
    if any(root.glob("svelte.config.*")):
        found.add("svelte")
    if any(root.glob("vite.config.*")):
        found.add("vite")
    if (root / "nest-cli.json").is_file():
        found.add("nestjs")
    if django:
        found.add("django")
    if "fastapi" in py_text:
        found.add("fastapi")
    if "flask" in py_text and not django:
        found.add("flask")
    if any(
        (root / name).is_file()
        for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml")
    ):
        found.add("docker")

    for fw, signals in FRAMEWORK_SIGNALS.items():
        if fw in found:
            continue
        for sig in signals:
            if "*" in sig:
                if _glob_exists(root, sig):
                    found.add(fw)
                    break
            elif (root / sig).is_file():
                found.add(fw)
                break
    return sorted(found)


def detect_entrypoints(repo_path: str) -> list[str]:
    """Look for common entrypoint filenames (relative paths)."""
    root = Path(repo_path)
    if not root.is_dir():
        return []
    hits: list[str] = []
    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        name = path.name
        if name in _ENTRY_NAMES:
            hits.append(rel)
            continue
        if rel.startswith("src/main.") and path.suffix:
            hits.append(rel)
    return sorted(set(hits))


def _top_level_modules(repo_path: Path) -> list[str]:
    mods: list[str] = []
    for child in repo_path.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith(".") or name in _SKIP_DIRS:
            continue
        mods.append(name)
    return sorted(mods)


def _infer_style(repo_path: Path, entrypoints: list[str]) -> str:
    if len(entrypoints) <= 1:
        return "monolith"
    modules = _top_level_modules(repo_path)
    if len(modules) <= 3:
        return "modular"
    ep_names = {Path(ep).name for ep in entrypoints}
    dirs_with_ep = 0
    for mod in modules:
        mod_dir = repo_path / mod
        for ep in ep_names:
            if (mod_dir / ep).is_file() or any(mod_dir.rglob(ep)):
                dirs_with_ep += 1
                break
    if dirs_with_ep > 3:
        return "microservices"
    return "modular"


def _ai_enrich(repo_path: str, base: dict) -> dict | None:
    try:
        from voly.ai_gateway import AIGateway
    except ImportError:
        return None
    try:
        gw = AIGateway()
        prompt = (
            "Given this repository architecture summary, reply with JSON "
            'keys "style" and "notes" only:\n'
            f"{json.dumps(base, ensure_ascii=False)}"
        )
        reply = gw.chat(prompt, model="small")
        text = reply if isinstance(reply, str) else str(reply)
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        if isinstance(data.get("style"), str):
            base["style"] = data["style"]
        if data.get("notes"):
            base["ai_notes"] = data["notes"]
        return base
    except Exception as exc:
        _log.debug("architecture AI enrichment failed: %s", exc)
        return None


def map_architecture(repo_path: str, *, use_ai: bool = False) -> dict:
    """Heuristic architecture map with optional AIGateway enrichment."""
    root = Path(repo_path)
    entrypoints = detect_entrypoints(repo_path)
    modules = _top_level_modules(root) if root.is_dir() else []
    result = {
        "style": _infer_style(root, entrypoints) if root.is_dir() else "unknown",
        "entrypoints": entrypoints,
        "modules": modules,
        "ai_assisted": False,
    }
    if use_ai:
        enriched = _ai_enrich(repo_path, dict(result))
        if enriched is not None:
            result.update(enriched)
            result["ai_assisted"] = True
    return result
