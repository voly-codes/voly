"""Atomic staged storage for admitted external capability packs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from voly.capability.pack_admission import admit_external_pack
from voly.capability.pack_manifest import (
    PackManifest,
    build_pack_manifest,
    validate_pack_id,
)
from voly.capability.packs import discover_ecc_pack

MANIFEST_NAME = "manifest.json"
MANIFEST_HASH_NAME = "manifest.sha256"


class PackStoreError(RuntimeError):
    """Raised for safe, user-actionable staged-pack storage failures."""


@dataclass(frozen=True)
class PackVerification:
    pack_id: str
    valid: bool
    errors: tuple[str, ...]
    checked_components: int


class PackStore:
    """Install immutable staged packs below one explicit runtime root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def install_ecc(self, source: str | Path) -> PackManifest:
        discovery = discover_ecc_pack(source)
        admission = admit_external_pack(discovery)
        manifest = build_pack_manifest(discovery, admission)
        destination = self._pack_path(manifest.pack_id)
        if destination.exists():
            raise PackStoreError(
                f"capability pack already exists: {manifest.pack_id}; "
                "remove it explicitly before reinstalling"
            )

        self.root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".install-", dir=self.root))
        try:
            self._copy_staged_components(manifest, temporary)
            payload = _manifest_bytes(manifest)
            (temporary / MANIFEST_NAME).write_bytes(payload)
            (temporary / MANIFEST_HASH_NAME).write_text(
                hashlib.sha256(payload).hexdigest() + "\n",
                encoding="ascii",
            )
            os.replace(temporary, destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return manifest

    def list(self) -> list[PackManifest]:
        if not self.root.is_dir():
            return []
        manifests: list[PackManifest] = []
        for path in sorted(self.root.iterdir(), key=lambda item: item.name):
            if path.is_dir() and not path.name.startswith("."):
                manifests.append(self.load(path.name))
        return manifests

    def load(self, pack_id: str) -> PackManifest:
        path = self._pack_path(pack_id) / MANIFEST_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PackStoreError(f"capability pack not found: {pack_id}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise PackStoreError(f"invalid capability-pack manifest: {exc}") from exc
        if not isinstance(data, dict):
            raise PackStoreError("capability-pack manifest must contain an object")
        try:
            return PackManifest.from_dict(data)
        except (TypeError, ValueError) as exc:
            raise PackStoreError(f"invalid capability-pack manifest: {exc}") from exc

    def verify(self, pack_id: str) -> PackVerification:
        normalized = validate_pack_id(pack_id)
        pack_path = self._pack_path(normalized)
        manifest = self.load(normalized)
        errors = self._verify_manifest_checksum(pack_path)
        checked = 0
        expected = {MANIFEST_NAME, MANIFEST_HASH_NAME}

        for component in manifest.components:
            if component.staged_path is None:
                continue
            checked += 1
            expected.add(component.staged_path)
            path = self._safe_staged_path(pack_path, component.staged_path)
            if not path.is_file():
                errors.append(f"missing component: {component.staged_path}")
            elif _file_sha256(path) != component.sha256:
                errors.append(f"hash mismatch: {component.staged_path}")

        actual = {
            path.relative_to(pack_path).as_posix()
            for path in pack_path.rglob("*")
            if path.is_file()
        }
        for unexpected in sorted(actual - expected):
            errors.append(f"unexpected file: {unexpected}")
        return PackVerification(normalized, not errors, tuple(errors), checked)

    def remove(self, pack_id: str) -> None:
        destination = self._pack_path(pack_id)
        if not destination.is_dir():
            raise PackStoreError(f"capability pack not found: {pack_id}")
        shutil.rmtree(destination)

    def _pack_path(self, pack_id: str) -> Path:
        normalized = validate_pack_id(pack_id)
        destination = (self.root / normalized).resolve()
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise PackStoreError("capability-pack path escapes store root") from exc
        return destination

    def _copy_staged_components(
        self,
        manifest: PackManifest,
        temporary: Path,
    ) -> None:
        source_root = Path(str(manifest.provenance["source_path"])).resolve(strict=True)
        for component in manifest.components:
            if component.staged_path is None:
                continue
            source = (source_root / component.source_path).resolve(strict=True)
            source.relative_to(source_root)
            destination = self._safe_staged_path(temporary, component.staged_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def _safe_staged_path(self, root: Path, relative: str) -> Path:
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise PackStoreError(f"staged path escapes pack root: {relative}") from exc
        return path

    def _verify_manifest_checksum(self, pack_path: Path) -> list[str]:
        try:
            payload = (pack_path / MANIFEST_NAME).read_bytes()
            expected = (pack_path / MANIFEST_HASH_NAME).read_text(
                encoding="ascii"
            ).strip()
        except OSError as exc:
            return [f"manifest checksum unavailable: {exc}"]
        actual = hashlib.sha256(payload).hexdigest()
        return [] if actual == expected else ["manifest checksum mismatch"]


def _manifest_bytes(manifest: PackManifest) -> bytes:
    text = json.dumps(
        manifest.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (text + "\n").encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
