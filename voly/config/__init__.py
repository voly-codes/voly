"""
VOLY configuration package.

Public API — all names importable as `from voly.config import <name>`:

  Dataclasses:
    ModelConfig, AgentConfig, VOLYConfig,
    RTKConfig, HeadroomConfig, PxpipeConfig, MemoryConfig, A2AConfig, AGUIConfig,
    SpendConfig, RegistryConfig, ScannerConfig,
    AIGatewayConfig, MCPConfig, TelemetryConfig, CloudConfig, DSPyConfig, PlanConfig,
    CostPolicyConfig, ExecutorSafetyConfig

  Functions:
    load_config, create_default_config

  Constants:
    DEFAULT_CONFIG_FILENAME, DEFAULT_PROXY_PORT, DEFAULT_PXPIPE_PORT

Internal modules (underscore-prefixed) are not part of the public API.
"""

from voly.config._types import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_PXPIPE_PORT,
    DEFAULT_PROXY_PORT,
    A2AConfig,
    AGUIConfig,
    AIGatewayConfig,
    AgentConfig,
    CloudConfig,
    VOLYConfig,
    CostPolicyConfig,
    DSPyConfig,
    ExecutorSafetyConfig,
    HeadroomConfig,
    MCPConfig,
    MemoryConfig,
    ModelConfig,
    PlanConfig,
    PxpipeConfig,
    RTKConfig,
    RegistryConfig,
    ScannerConfig,
    SpendConfig,
    TelemetryConfig,
)
from voly.config._defaults import _DEFAULT_MODELS
from voly.config._loader import load_config
from voly.config._template import create_default_config

__all__ = [
    # dataclasses
    "ModelConfig",
    "AgentConfig",
    "VOLYConfig",
    "RTKConfig",
    "HeadroomConfig",
    "PxpipeConfig",
    "MemoryConfig",
    "A2AConfig",
    "AGUIConfig",
    "SpendConfig",
    "RegistryConfig",
    "ScannerConfig",
    "AIGatewayConfig",
    "MCPConfig",
    "TelemetryConfig",
    "CloudConfig",
    "DSPyConfig",
    "PlanConfig",
    "CostPolicyConfig",
    "ExecutorSafetyConfig",
    # functions
    "load_config",
    "create_default_config",
    # constants
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_PXPIPE_PORT",
    "DEFAULT_PROXY_PORT",
    # internal (kept for compat)
    "_DEFAULT_MODELS",
]
