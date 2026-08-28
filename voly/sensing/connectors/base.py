"""Connector interface for bounded polling of external observations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from voly.sensing.schema import Signal


class SensingConnector(ABC):
    name: str

    @abstractmethod
    def poll(self) -> list[Signal]:
        """Return the finite set of Signals observed during one poll."""
