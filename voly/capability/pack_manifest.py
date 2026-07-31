"""Versioned manifest contract for staged external capability packs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voly.capability.pack_admission import PackAdmissionReport
from voly.capability.packs import PackDiscoveryReport

PACK_MANIFEST_SCHEMA_VERSION = 1
_PACK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SKILL_REFERENCE = re.compile(r"skills/([a-zA-Z0-9._-]+)/SKILL\.md")
_DEPRECATED_SKILL = re.compile(
    r"(?i)\[DEPRECATED\s*-\s*use\s+([a-zA-Z0-9._-]+)\]"
)


@dataclass(frozen=True)
class StagedPackComponent:
    kind: str
    component_id: str
    source_path: str
    staged_path: str | None
    sha256: str
    status: str


@dataclass(frozen=True)
class CompatibilityAlias:
    alias: str
    target: str
    kind: str


@dataclass(frozen=True)
class PackManifest:
    schema_version: int
    pack_id: str
    adapter: str
    version: str
    installed_at: str
    state: str
    provenance: dict[str, Any]
    admission: dict[str, Any]
    components: tuple[StagedPackComponent, ...]
    compatibility_aliases: tuple[CompatibilityAlias, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackManifest:
        if int(data.get("schema_version", 0)) != PACK_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported capability-pack manifest schema")
        pack_id = validate_pack_id(str(data.get("pack_id") or ""))
        components = tuple(
            StagedPackComponent(**item) for item in data.get("components", [])
        )
        aliases = tuple(
            CompatibilityAlias(**item)
            for item in data.get("compatibility_aliases", [])
        )
        return cls(
            schema_version=PACK_MANIFEST_SCHEMA_VERSION,
            pack_id=pack_id,
            adapter=str(data.get("adapter") or ""),
            version=str(data.get("version") or ""),
            installed_at=str(data.get("installed_at") or ""),
            state=str(data.get("state") or ""),
            provenance=dict(data.get("provenance") or {}),
            admission=dict(data.get("admission") or {}),
            components=components,
            compatibility_aliases=aliases,
        )


def build_pack_manifest(
    discovery: PackDiscoveryReport,
    admission: PackAdmissionReport,
) -> PackManifest:
    root = Path(discovery.provenance.source_path).resolve(strict=True)
    quarantined = set(admission.quarantined_components)
    components: list[StagedPackComponent] = []

    for component in discovery.components:
        source = _safe_source_path(root, component.path)
        is_quarantined = component.path in quarantined
        components.append(
            StagedPackComponent(
                kind=component.kind,
                component_id=component.component_id,
                source_path=component.path,
                staged_path=None if is_quarantined else f"content/{component.path}",
                sha256=_sha256(source),
                status="quarantined" if is_quarantined else "staged",
            )
        )
    aliases = _compatibility_aliases(root, components)

    return PackManifest(
        schema_version=PACK_MANIFEST_SCHEMA_VERSION,
        pack_id=validate_pack_id(discovery.pack_id),
        adapter=discovery.adapter,
        version=discovery.provenance.package_version,
        installed_at=datetime.now(timezone.utc).isoformat(),
        state="staged",
        provenance=asdict(discovery.provenance),
        admission={
            "schema_version": admission.schema_version,
            "decision": admission.decision,
            "risk_level": admission.risk_level,
            "finding_count": len(admission.findings),
            "quarantined_components": list(admission.quarantined_components),
        },
        components=tuple(components),
        compatibility_aliases=aliases,
    )


def validate_pack_id(pack_id: str) -> str:
    normalized = pack_id.strip().lower()
    if not _PACK_ID.fullmatch(normalized):
        raise ValueError(f"invalid capability-pack id: {pack_id!r}")
    return normalized


def _safe_source_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"component escapes capability pack source: {relative}") from exc
    if not path.is_file():
        raise ValueError(f"capability-pack component is not a file: {relative}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compatibility_aliases(
    root: Path,
    components: list[StagedPackComponent],
) -> tuple[CompatibilityAlias, ...]:
    staged_skills = {
        item.component_id
        for item in components
        if item.kind == "skill" and item.status == "staged"
    }
    aliases: list[CompatibilityAlias] = []
    for component in components:
        if component.status != "staged":
            continue
        if component.kind == "legacy_command":
            target = _referenced_skill(root / component.source_path, staged_skills)
            aliases.append(
                CompatibilityAlias(
                    alias=component.component_id,
                    target=f"skill:{target}" if target else (
                        f"legacy-command:{component.component_id}"
                    ),
                    kind="command",
                )
            )
        elif component.kind == "skill":
            target = _deprecated_skill_target(
                root / component.source_path,
                staged_skills,
            )
            if target:
                aliases.append(
                    CompatibilityAlias(
                        alias=component.component_id,
                        target=f"skill:{target}",
                        kind="skill",
                    )
                )
    return tuple(sorted(aliases, key=lambda item: (item.kind, item.alias)))


def _referenced_skill(path: Path, staged_skills: set[str]) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _SKILL_REFERENCE.search(text)
    if match and match.group(1) in staged_skills:
        return match.group(1)
    return None


def _deprecated_skill_target(path: Path, staged_skills: set[str]) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")[:8_000]
    match = _DEPRECATED_SKILL.search(text)
    if match and match.group(1) in staged_skills:
        return match.group(1)
    return None
