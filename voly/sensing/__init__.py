"""Versioned contracts for the opt-in business-signal loop.

Runtime ingestion is intentionally absent until the sensing connector phase.
"""

from voly.sensing.schema import ActionReport, Option, Signal, SensingValidationError

__all__ = ["ActionReport", "Option", "Signal", "SensingValidationError"]
