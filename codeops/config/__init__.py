"""
CodeOps configuration package.

Public API — all names importable as `from codeops.config import <name>`:

  Dataclasses:
    ModelConfig, AgentConfig, CodeOpsConfig,
    RTKConfig, HeadroomConfig, MemoryConfig, A2AConfig, AGUIConfig,
    SpendConfig, WorkflowConfig, RegistryConfig, ScannerConfig,
    AIGatewayConfig, MCPConfig, TelemetryConfig, DSPyConfig, CostPolicyConfig

  Functions:
    load_config, create_default_config

  Constants:
    DEFAULT_CONFIG_FILENAME, DEFAULT_PROXY_PORT

Internal modules (underscore-prefixed) are not part of the public API.
"""

from codeops.config._types import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_PROXY_PORT,
    A2AConfig,
    AGUIConfig,
    AIGatewayConfig,
    AgentConfig,
    CodeOpsConfig,
    CostPolicyConfig,
    DSPyConfig,
    HeadroomConfig,
    MCPConfig,
    MemoryConfig,
    ModelConfig,
    RTKConfig,
    RegistryConfig,
    ScannerConfig,
    SpendConfig,
    TelemetryConfig,
    WorkflowConfig,
)
from codeops.config._defaults import _DEFAULT_MODELS
from codeops.config._loader import load_config
from codeops.config._template import create_default_config

__all__ = [
    # dataclasses
    "ModelConfig",
    "AgentConfig",
    "CodeOpsConfig",
    "RTKConfig",
    "HeadroomConfig",
    "MemoryConfig",
    "A2AConfig",
    "AGUIConfig",
    "SpendConfig",
    "WorkflowConfig",
    "RegistryConfig",
    "ScannerConfig",
    "AIGatewayConfig",
    "MCPConfig",
    "TelemetryConfig",
    "DSPyConfig",
    "CostPolicyConfig",
    # functions
    "load_config",
    "create_default_config",
    # constants
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_PROXY_PORT",
    # internal (kept for compat)
    "_DEFAULT_MODELS",
]
