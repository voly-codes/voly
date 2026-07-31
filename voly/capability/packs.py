"""Read-only discovery of external capability packs.

Discovery treats every file in the external repository as untrusted data. It
does not import Python modules, execute hooks, start MCP servers, or copy files.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class ExternalPackError(ValueError):
    """Raised when an external capability pack cannot be safely inspected."""


@dataclass(frozen=True)
class PackComponent:
    """One inert component discovered in an external pack."""

    kind: str
    component_id: str
    path: str


@dataclass(frozen=True)
class PackProvenance:
    """Best-effort source identity without trusting repository code."""

    source_path: str
    repository: str = ""
    revision: str = ""
    package_name: str = ""
    package_version: str = ""
    license: str = ""


@dataclass(frozen=True)
class PackDiscoveryReport:
    """Deterministic inventory returned by a read-only adapter."""

    schema_version: int
    adapter: str
    pack_id: str
    provenance: PackProvenance
    components: tuple[PackComponent, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    dry_run: bool = True

    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for component in self.components:
            counts[component.kind] = counts.get(component.kind, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["counts"] = self.counts
        return data


_ECC_LAYOUT: tuple[tuple[str, str], ...] = (
    ("agent", "agents/*.md"),
    ("skill", "skills/*/SKILL.md"),
    ("rule", "rules/**/*.md"),
    ("hook", "hooks/**/*.json"),
    ("mcp_config", "mcp-configs/*.json"),
    ("legacy_command", "legacy-command-shims/commands/*.md"),
)


def discover_ecc_pack(source: str | Path) -> PackDiscoveryReport:
    """Inventory an ECC checkout without executing or installing its content."""
    root = _resolve_source(source)
    package = _read_package_metadata(root)
    components: list[PackComponent] = []

    for kind, pattern in _ECC_LAYOUT:
        for path in _safe_files(root, pattern):
            rel = path.relative_to(root).as_posix()
            components.append(
                PackComponent(
                    kind=kind,
                    component_id=_component_id(kind, path),
                    path=rel,
                )
            )

    components.sort(key=lambda item: (item.kind, item.component_id, item.path))
    warnings: list[str] = []
    if not components:
        warnings.append("no supported ECC components discovered")

    return PackDiscoveryReport(
        schema_version=1,
        adapter="ecc",
        pack_id=str(package.get("name") or "ecc"),
        provenance=PackProvenance(
            source_path=str(root),
            repository=_git_value(root, "config", "--get", "remote.origin.url"),
            revision=_git_value(root, "rev-parse", "HEAD"),
            package_name=str(package.get("name") or ""),
            package_version=str(package.get("version") or ""),
            license=str(package.get("license") or ""),
        ),
        components=tuple(components),
        warnings=tuple(warnings),
    )


def _resolve_source(source: str | Path) -> Path:
    path = Path(source).expanduser()
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise ExternalPackError(f"capability pack source does not exist: {path}") from exc
    if not root.is_dir():
        raise ExternalPackError(f"capability pack source is not a directory: {root}")
    return root


def _safe_files(root: Path, pattern: str) -> list[Path]:
    files: list[Path] = []
    for candidate in root.glob(pattern):
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ExternalPackError(
                f"component escapes capability pack source: {candidate}"
            ) from exc
        files.append(resolved)
    return sorted(set(files), key=lambda path: path.relative_to(root).as_posix())


def _component_id(kind: str, path: Path) -> str:
    if kind == "skill":
        return path.parent.name
    return path.stem


def _read_package_metadata(root: Path) -> dict[str, Any]:
    package_path = root / "package.json"
    if not package_path.is_file():
        return {}
    try:
        if package_path.stat().st_size > 1_000_000:
            raise ExternalPackError("package.json exceeds the 1 MB discovery limit")
        data = json.loads(package_path.read_text(encoding="utf-8"))
    except ExternalPackError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExternalPackError(f"invalid package.json: {exc}") from exc
    if not isinstance(data, dict):
        raise ExternalPackError("package.json must contain an object")
    return data


def _git_value(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
