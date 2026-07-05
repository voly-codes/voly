"""
Хранилище скомпилированных DSPy программ.

Новая схема хранения:
    .voly/dspy/programs/<program_id>/v<N>.json

Где `program_id` — стабильный идентификатор программы, независимый
от агента. Для обратной совместимости также читаются legacy-директории,
созданные по имени агента.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DSPY_AVAILABLE = False
try:
    import dspy  # noqa: F401
    _DSPY_AVAILABLE = True
except ImportError:
    pass


class DSPyProgramStore:
    """Управляет сохранением и загрузкой скомпилированных DSPy программ."""

    def __init__(self, programs_dir: str = ".voly/dspy/programs") -> None:
        self.programs_dir = Path(programs_dir)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slug(identifier: str) -> str:
        return identifier.replace("/", "__")

    @staticmethod
    def _unslug(path_name: str) -> str:
        return path_name.replace("__", "/")

    def _dir_for(self, identifier: str) -> Path:
        return self.programs_dir / self._slug(identifier)

    def _candidate_dirs(self, program_id: str, aliases: tuple[str, ...] | None = None) -> list[Path]:
        seen: set[str] = set()
        candidates: list[Path] = []
        for ident in (program_id, *(aliases or ())):
            slug = self._slug(ident)
            if slug in seen:
                continue
            seen.add(slug)
            candidates.append(self.programs_dir / slug)
        return candidates

    def _latest_version(self, program_id: str, aliases: tuple[str, ...] | None = None) -> int:
        versions: list[int] = []
        for directory in self._candidate_dirs(program_id, aliases):
            if not directory.exists():
                continue
            for file in directory.glob("*.json"):
                try:
                    versions.append(int(file.stem.lstrip("v")))
                except ValueError:
                    continue
        return max(versions, default=0)

    def path_for(
        self,
        program_id: str,
        version: int | None = None,
        *,
        alias: str | None = None,
        aliases: tuple[str, ...] | None = None,
    ) -> Path:
        if version is None:
            version = self._latest_version(program_id, aliases)
        target_dir = self._dir_for(alias or program_id)
        candidate_dirs = [target_dir]
        for other in self._candidate_dirs(program_id, aliases):
            if other not in candidate_dirs:
                candidate_dirs.append(other)
        for directory in candidate_dirs:
            candidate = directory / f"v{version}.json"
            if candidate.exists():
                return candidate
        return target_dir / f"v{version}.json"

    def next_version_path(self, program_id: str) -> Path:
        next_version = self._latest_version(program_id) + 1
        directory = self._dir_for(program_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"v{next_version}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, program: Any, program_id: str, version: int | None = None) -> tuple[Path, int]:
        """
        Save a compiled DSPy program.

        Args:
            program: dspy.Module that was compiled via teleprompter.compile()
            program_id: unique program identifier
            version: explicit version; auto-increments if None

        Returns:
             (Path, version) tuple for the saved program.
        """
        if version is None:
            path = self.next_version_path(program_id)
            version = int(path.stem.lstrip("v"))
        else:
            path = self._dir_for(program_id) / f"v{version}.json"
            path.parent.mkdir(parents=True, exist_ok=True)

        try:
            program.save(str(path))
            logger.info("dspy.store: saved %s → %s", program_id, path)
        except Exception as exc:
            logger.warning("dspy.store: program.save() failed (%s), using JSON fallback", exc)
            # Fallback: store repr for debugging
            path.write_text(json.dumps({"program_id": program_id, "error": str(exc)}), encoding="utf-8")
        return path, version

    def load(
        self,
        program_id: str,
        program: Any,
        version: int | None = None,
        *,
        aliases: tuple[str, ...] | None = None,
    ) -> tuple[bool, int]:
        """
        Load a compiled DSPy program in-place into `program`.

        Args:
            program_id: unique program identifier
            program: uninitialised dspy.Module to load into
            version: explicit version; latest if None
            aliases: optional legacy identifiers (e.g. agent name)

        Returns:
            (loaded: bool, version: int)
        """
        identifiers = (program_id, *(aliases or ()))
        target_version = version or self._latest_version(program_id, aliases)

        if not target_version:
            return False, 0

        for ident in identifiers:
            path = self._dir_for(ident) / f"v{target_version}.json"
            if not path.exists():
                continue
            try:
                program.load(str(path))
                logger.info("dspy.store: loaded %s ← %s", program_id, path)
                return True, target_version
            except Exception as exc:
                logger.warning("dspy.store: failed to load %s (%s): %s", program_id, path, exc)
                continue

        logger.debug("dspy.store: no saved program for %s v%s", program_id, target_version)
        return False, 0

    def list_programs(self) -> dict[str, list[int]]:
        """Return {program_id: [versions]} for all saved programs."""
        result: dict[str, list[int]] = {}
        if not self.programs_dir.exists():
            return result
        for directory in sorted(self.programs_dir.iterdir()):
            if not directory.is_dir():
                continue
            versions = []
            for f in sorted(directory.glob("*.json")):
                try:
                    versions.append(int(f.stem.lstrip("v")))
                except ValueError:
                    pass
            if versions:
                program_id = self._unslug(directory.name)
                result[program_id] = sorted(versions)
        return result

    def delete(self, program_id: str, version: int) -> bool:
        """Delete a specific version. Returns True if deleted."""
        path = self._dir_for(program_id) / f"v{version}.json"
        if path.exists():
            path.unlink()
            logger.info("dspy.store: deleted %s v%s", program_id, version)
            return True
        return False

    def latest_version(self, program_id: str, aliases: tuple[str, ...] | None = None) -> int:
        """Public wrapper for the latest version lookup."""
        return self._latest_version(program_id, aliases)
