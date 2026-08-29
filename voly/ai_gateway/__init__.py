"""AI Gateway Layer — centralised LLM routing with CF AI Gateway support.

Split into:
  models.py  — enums and dataclasses (RateLimit, SpendLimit, CacheConfig, …)
  gateway.py — AIGateway class
"""
from .factory import gateway_from_config
from .gateway import AIGateway
from .models import (
    CacheConfig,
    DLPConfig,
    FallbackChain,
    FallbackStrategy,
    GatewayMetrics,
    GatewayProvider,
    RateLimit,
    SpendLimit,
)
from .project_state import project_fingerprint

__all__ = [
    "GatewayProvider",
    "FallbackStrategy",
    "RateLimit",
    "SpendLimit",
    "CacheConfig",
    "FallbackChain",
    "DLPConfig",
    "GatewayMetrics",
    "AIGateway",
    "gateway_from_config",
    "project_fingerprint",
]
