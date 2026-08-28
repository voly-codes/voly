"""Atomic local Signal persistence with connector-defined deduplication."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from voly.sensing.schema import Signal, SensingValidationError


class SignalStore:
    """Store Signals as ``<store>/<YYYY-MM-DD>/<signal_id>.json``."""

    _INDEX_NAME = ".dedup.json"

    def __init__(self, store_dir: str = ".voly/signals") -> None:
        self.store_dir = Path(store_dir)

    @staticmethod
    def _date_for(signal: Signal) -> str:
        raw = signal.captured_at.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise SensingValidationError(
                f"invalid captured_at: {signal.captured_at!r}"
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()

    def path(self, signal: Signal) -> Path:
        return self.store_dir / self._date_for(signal) / f"{signal.signal_id}.json"

    def options_path(self, signal: Signal) -> Path:
        return self.store_dir / self._date_for(signal) / f"{signal.signal_id}.options.json"

    @staticmethod
    def _atomic_json(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _load_index(self) -> dict[str, str]:
        path = self.store_dir / self._INDEX_NAME
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise SensingValidationError("signal dedup index is not an object")
        return {str(key): str(value) for key, value in data.items()}

    def save(self, signal: Signal) -> bool:
        """Persist a new Signal; return False when its dedup key already exists."""
        index = self._load_index()
        if signal.dedup_key in index:
            return False
        target = self.path(signal)
        if target.exists():
            raise SensingValidationError(f"duplicate signal_id: {signal.signal_id!r}")
        self._atomic_json(target, signal.to_dict())
        relative = target.relative_to(self.store_dir).as_posix()
        index[signal.dedup_key] = relative
        self._atomic_json(self.store_dir / self._INDEX_NAME, index)
        return True

    def save_many(self, signals: Iterable[Signal]) -> list[Signal]:
        stored: list[Signal] = []
        for signal in signals:
            if self.save(signal):
                stored.append(signal)
        return stored

    def save_options(self, signal: Signal, options: Iterable[object]) -> Path:
        """Atomically store the interpretation artifact beside its Signal."""
        serialized = []
        for option in options:
            to_dict = getattr(option, "to_dict", None)
            if not callable(to_dict):
                raise TypeError("options must provide to_dict()")
            serialized.append(to_dict())
        target = self.options_path(signal)
        self._atomic_json(target, {
            "schema_version": 1,
            "signal_id": signal.signal_id,
            "options": serialized,
        })
        return target

    def list(self) -> list[Signal]:
        signals: list[Signal] = []
        if not self.store_dir.exists():
            return signals
        for path in self.store_dir.glob("????-??-??/*.json"):
            try:
                with path.open(encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    signals.append(Signal.from_dict(data))
            except (OSError, ValueError, TypeError, KeyError):
                continue
        return sorted(signals, key=lambda item: item.captured_at, reverse=True)
