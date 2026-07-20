"""Parse root-level package manifests for dependencies and versions."""

from __future__ import annotations

import json
import re
from pathlib import Path

_REQ_LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<ver>[=<>!~]+[^\s#;]+)?",
    re.I,
)
_PYPROJECT_DEP = re.compile(
    r'^\s*["\']?(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)["\']?\s*=\s*["\'](?P<ver>[^"\']+)["\']',
    re.M,
)
_GO_MOD = re.compile(r"^\s*(?P<mod>\S+)\s+(?P<ver>v[^\s]+)", re.M)
_CARGO_DEP = re.compile(
    r'^\s*(?P<name>[A-Za-z0-9_-]+)\s*=\s*["\'](?P<ver>[^"\']+)["\']',
    re.M,
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse_package_json(path: str) -> dict[str, str]:
    text = _read(Path(path))
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            for name, ver in block.items():
                out[str(name)] = str(ver)
    return out


def _parse_requirements(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _read(Path(path)).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = _REQ_LINE.match(line)
        if m:
            ver = (m.group("ver") or "").strip() or "*"
            out[m.group("name").lower()] = ver
    return out


def _parse_pyproject(path: str) -> dict[str, str]:
    text = _read(Path(path))
    if not text:
        return {}
    out: dict[str, str] = {}
    for m in _PYPROJECT_DEP.finditer(text):
        out[m.group("name").lower()] = m.group("ver")
    return out


def _parse_go_mod(path: str) -> dict[str, str]:
    text = _read(Path(path))
    out: dict[str, str] = {}
    in_require = False
    for line in text.splitlines():
        if line.strip().startswith("require ("):
            in_require = True
            continue
        if in_require and line.strip() == ")":
            in_require = False
            continue
        m = _GO_MOD.match(line)
        if m and (in_require or line.strip().startswith("require ")):
            out[m.group("mod")] = m.group("ver")
    return out


def _parse_cargo_toml(path: str) -> dict[str, str]:
    text = _read(Path(path))
    section = ""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip().startswith("[") and line.strip().endswith("]"):
            section = line.strip().lower()
            continue
        if section not in ("[dependencies]", "[dev-dependencies]"):
            continue
        m = _CARGO_DEP.match(line)
        if m:
            out[m.group("name")] = m.group("ver")
    return out


def analyze_dependencies(repo_path: str) -> dict:
    """Return ecosystem-keyed dependency maps from root manifests only."""
    root = Path(repo_path)
    if not root.is_dir():
        return {}

    result: dict[str, dict[str, str]] = {}

    pkg = root / "package.json"
    if pkg.is_file():
        deps = _parse_package_json(str(pkg))
        if deps:
            result["node"] = deps

    req = root / "requirements.txt"
    if req.is_file():
        deps = _parse_requirements(str(req))
        if deps:
            result["python"] = deps

    for path in sorted(root.glob("requirements*.txt")):
        if path.name == "requirements.txt":
            continue
        deps = _parse_requirements(str(path))
        if deps:
            py = result.setdefault("python", {})
            py.update(deps)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        deps = _parse_pyproject(str(pyproject))
        if deps:
            py = result.setdefault("python", {})
            py.update(deps)

    gomod = root / "go.mod"
    if gomod.is_file():
        deps = _parse_go_mod(str(gomod))
        if deps:
            result["go"] = deps

    cargo = root / "Cargo.toml"
    if cargo.is_file():
        deps = _parse_cargo_toml(str(cargo))
        if deps:
            result["rust"] = deps

    return result
