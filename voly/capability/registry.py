"""Load/save executor capability profiles from local YAML cache."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from voly.capability.schema import ExecutorCapabilityProfile

logger = logging.getLogger(__name__)

_PACKAGE_SEEDS_DIR = Path(__file__).resolve().parent / "seeds"


class CapabilityRegistry:
    def __init__(self, profiles_dir: str, seeds_dir: str | None = None) -> None:
        self.profiles_dir = Path(profiles_dir)
        self.seeds_dir = Path(seeds_dir) if seeds_dir else _PACKAGE_SEEDS_DIR
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def load(self, executor_id: str) -> ExecutorCapabilityProfile:
        profile_path = self._profile_path(executor_id)
        if profile_path.is_file():
            return self._read_profile(profile_path)

        seed_path = self._seed_path(executor_id)
        if seed_path.is_file():
            profile = self._read_profile(seed_path)
            self.save(profile)
            return profile

        return ExecutorCapabilityProfile.unknown(executor_id)

    def save(self, profile: ExecutorCapabilityProfile) -> None:
        path = self._profile_path(profile.id)
        self._write_profile(path, profile.to_dict())

    def list_ids(self) -> list[str]:
        ids: set[str] = set()
        for directory in (self.profiles_dir, self.seeds_dir):
            if not directory.is_dir():
                continue
            for path in directory.glob("*.yaml"):
                ids.add(path.stem)
            for path in directory.glob("*.yml"):
                ids.add(path.stem)
        return sorted(ids)

    def reset(self, executor_id: str) -> None:
        path = self._profile_path(executor_id)
        if path.is_file():
            path.unlink()

    def reset_all(self) -> None:
        for path in self.profiles_dir.glob("*.yaml"):
            path.unlink()
        for path in self.profiles_dir.glob("*.yml"):
            path.unlink()

    def _profile_path(self, executor_id: str) -> Path:
        return self.profiles_dir / f"{executor_id}.yaml"

    def _seed_path(self, executor_id: str) -> Path:
        yaml_path = self.seeds_dir / f"{executor_id}.yaml"
        if yaml_path.is_file():
            return yaml_path
        return self.seeds_dir / f"{executor_id}.yml"

    def _read_profile(self, path: Path) -> ExecutorCapabilityProfile:
        text = path.read_text(encoding="utf-8")
        data = _load_serialized(text, path.suffix)
        return ExecutorCapabilityProfile.from_dict(data)

    def _write_profile(self, path: Path, data: dict) -> None:
        text = _dump_serialized(data, prefer_yaml=True)
        path.write_text(text, encoding="utf-8")


def _load_serialized(text: str, suffix: str) -> dict:
    if suffix == ".json":
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else {}
    try:
        import yaml
    except ImportError:
        logger.warning("pyyaml not installed; falling back to JSON for this read")
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else {}
    loaded = yaml.safe_load(text) or {}
    return loaded if isinstance(loaded, dict) else {}


def _dump_serialized(data: dict, *, prefer_yaml: bool) -> str:
    if not prefer_yaml:
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        import yaml
    except ImportError:
        logger.warning("pyyaml not installed; falling back to JSON for this write")
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
