"""
Конфигурация CodeOps — загружается из codeops.yaml в корне проекта.

Поддерживает:
    - Конфигурацию моделей (Claude, GPT, Gemini, Ollama)
    - Настройки агентов и маршрутизации
    - Параметры RTK и Headroom
    - Управление памятью
    - Интеграции MCP
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_FILENAME = "codeops.yaml"
DEFAULT_PROXY_PORT = 8787


@dataclass
class ModelConfig:
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    api_key: str = ""
    base_url: str | None = None
    max_tokens: int = 8192
    temperature: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    name: str = "claude"
    description: str = ""
    model: str | None = None
    executor: str | None = None
    tools: list[str] = field(default_factory=list)
    system_prompt: str | None = None
    max_turns: int = 100
    sandbox: bool = False


@dataclass
class CostPolicyConfig:
    enabled: bool = True
    max_task_cost_usd: float = 1.0
    stop_on_budget_exceeded: bool = True
    prefer_cheaper_model_for: list[str] = field(
        default_factory=lambda: ["docs", "tests", "summarization"]
    )
    cheaper_model: str = "deepseek-v4-flash"
    cheaper_model_map: dict[str, str] = field(default_factory=dict)

@dataclass
class RTKConfig:
    enabled: bool = True
    binary_path: str | None = None
    auto_install: bool = True


@dataclass
class HeadroomConfig:
    enabled: bool = True
    port: int = DEFAULT_PROXY_PORT
    savings_profile: str = "agent-90"
    memory_enabled: bool = False
    code_graph: bool = False
    lean_ctx: bool = False


@dataclass
class MemoryConfig:
    enabled: bool = False
    backend: str = "hybrid"
    remote_url: str = ""
    db_path: str = ".codeops/memory.db"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_memories: int = 10000


@dataclass
class A2AConfig:
    enabled: bool = True
    port: int = 9100
    federation_url: str = ""
    agent_discovery: bool = True
    remote_agents: list[str] = field(default_factory=list)
    local_agents: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AGUIConfig:
    enabled: bool = True
    port: int = 9101
    remote_url: str = ""
    streaming: bool = True
    session_timeout_seconds: int = 3600
    cors_origins: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class SpendConfig:
    enabled: bool = True
    remote_url: str = ""
    daily_budget_usd: float = 20.0


@dataclass
class WorkflowConfig:
    enabled: bool = True
    remote_url: str = ""
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    timeout_seconds: float = 300.0
    checkpoint_dir: str = ".codeops/checkpoints"


@dataclass
class RegistryConfig:
    enabled: bool = True
    agents_path: str = ".codeops/agents"
    skills_path: str = ".codeops/skills"
    marketplace_url: str = ""


@dataclass
class ScannerConfig:
    enabled: bool = True
    auto_scan: bool = True
    scan_depth: int = 3


@dataclass
class AIGatewayConfig:
    enabled: bool = True
    provider: str = "cloudflare"
    account_id: str = ""
    gateway_id: str = "default"
    api_token: str = ""
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    cache_max_entries: int = 1000
    rate_limits_enabled: bool = True
    rate_requests_per_minute: int = 60
    spend_limits_enabled: bool = True
    spend_daily_budget_usd: float = 20.0
    spend_per_agent_budget: dict[str, float] = field(default_factory=dict)
    fallback_enabled: bool = True
    fallback_chain: list[dict[str, str]] = field(default_factory=list)
    fallback_retries: int = 3
    dlp_enabled: bool = False
    dlp_block_secrets: bool = True
    dlp_block_pii: bool = True


@dataclass
class MCPConfig:
    servers: list[dict[str, Any]] = field(default_factory=list)
    tools_allowlist: list[str] = field(default_factory=list)


@dataclass
class TelemetryConfig:
    enabled: bool = True
    events_dir: str = ".codeops/events"
    pipeline_url: str = ""
    pipeline_enabled: bool = True
    pipeline_timeout_seconds: float = 5.0
    r2_enabled: bool = True


@dataclass
class DSPyConfig:
    """DSPy optimizer layer — sits between Headroom and AIGateway.chat()."""

    enabled: bool = False
    # off: DSPy not used at all
    # shadow: runs in parallel, result logged but not returned to caller
    # active: DSPy result replaces AIGateway.chat() for opted-in agents
    mode: str = "shadow"
    programs_dir: str = ".codeops/dspy/programs"
    datasets_dir: str = ".codeops/dspy/datasets"
    optimizer: str = "bootstrap_fewshot"
    min_examples: int = 20
    # small | medium | large — controls compile budget (num trials / epochs)
    compile_budget: str = "small"
    # agents to apply DSPy to; empty list = all agents when mode=active
    agents: list[str] = field(default_factory=list)
    # routing_mode: shadow | active — controls whether DSPy also drives routing
    routing_mode: str = "shadow"
    # program registry / version manager
    active_tag: str = "production"
    shadow_tag: str = "candidate"
    program_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class CodeOpsConfig:
    models: dict[str, ModelConfig] = field(default_factory=dict)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    rtk: RTKConfig = field(default_factory=RTKConfig)
    headroom: HeadroomConfig = field(default_factory=HeadroomConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    a2a: A2AConfig = field(default_factory=A2AConfig)
    agui: AGUIConfig = field(default_factory=AGUIConfig)
    spend: SpendConfig = field(default_factory=SpendConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    registry: RegistryConfig = field(default_factory=RegistryConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    ai_gateway: AIGatewayConfig = field(default_factory=AIGatewayConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    cost_policy: CostPolicyConfig = field(default_factory=CostPolicyConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    dspy: DSPyConfig = field(default_factory=DSPyConfig)
    default_model: str = "claude-sonnet"
    default_agent: str = "claude"

    def get_model_config(self, name: str | None = None) -> ModelConfig:
        name = name or self.default_model
        if name in self.models:
            return self.models[name]
        if name in _DEFAULT_MODELS:
            return _DEFAULT_MODELS[name]
        return ModelConfig(provider="anthropic", model=name)

    def get_agent_config(self, name: str | None = None) -> AgentConfig:
        name = name or self.default_agent
        if name in self.agents:
            return self.agents[name]
        return AgentConfig(name=name)


_DEFAULT_MODELS: dict[str, ModelConfig] = {
    "claude-sonnet": ModelConfig(provider="anthropic", model="claude-sonnet-4-5-20250929"),
    "claude-opus": ModelConfig(provider="anthropic", model="claude-opus-4-5-20250929"),
    "gpt-4o": ModelConfig(provider="openai", model="gpt-4o"),
    "gpt-4o-mini": ModelConfig(provider="openai", model="gpt-4o-mini"),
    "gemini-pro": ModelConfig(provider="google", model="gemini-2.5-pro"),
    "gemini-flash": ModelConfig(provider="google", model="gemini-2.5-flash"),
    "deepseek-chat": ModelConfig(provider="deepseek", model="deepseek-chat"),
    "deepseek-reasoner": ModelConfig(provider="deepseek", model="deepseek-reasoner"),
    "mimo-pro": ModelConfig(provider="mimo", model="mimo-v2.5-pro"),
    "mimo-fast": ModelConfig(provider="mimo", model="mimo-v2.5"),
    "mimo-omni": ModelConfig(provider="mimo", model="mimo-v2-omni"),
    # OpenCode Go — Chinese/alternative models (opencode.ai/zen/go/v1)
    "deepseek-v4-flash": ModelConfig(provider="opencode", model="deepseek-v4-flash"),
    "deepseek-v4-pro": ModelConfig(provider="opencode", model="deepseek-v4-pro"),
    "kimi-k2": ModelConfig(provider="opencode", model="kimi-k2.6"),
    "kimi-k2-code": ModelConfig(provider="opencode", model="kimi-k2.7-code"),
    "qwen3-plus": ModelConfig(provider="opencode", model="qwen3.7-plus"),
    "qwen3-max": ModelConfig(provider="opencode", model="qwen3.7-max"),
    "minimax-m3": ModelConfig(provider="opencode", model="minimax-m3"),
    "glm-5": ModelConfig(provider="opencode", model="glm-5.2"),
    # OpenCode Zen — mainstream models via proxy (opencode.ai/zen/v1)
    "zen-claude-sonnet": ModelConfig(provider="opencode-zen", model="claude-sonnet-4-6"),
    "zen-claude-opus": ModelConfig(provider="opencode-zen", model="claude-opus-4-8"),
    "zen-claude-haiku": ModelConfig(provider="opencode-zen", model="claude-haiku-4-5"),
    "zen-deepseek-free": ModelConfig(provider="opencode-zen", model="deepseek-v4-flash-free"),
    "zen-mimo-free": ModelConfig(provider="opencode-zen", model="mimo-v2.5-free"),
}


def _find_config_path(start_dir: Path | None = None) -> Path | None:
    current = start_dir or Path.cwd()
    while True:
        candidate = current / DEFAULT_CONFIG_FILENAME
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _load_dotenv(start_dir: Path | None = None) -> None:
    """Load .env file(s) into os.environ (only sets vars that aren't already set).

    Loads in order: CodeOps package root .env first (always), then walks up from
    start_dir/cwd to merge project-level .env. First loaded value wins.
    """
    def _apply(env_file: Path) -> None:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value

    # Always load CodeOps package root .env first (contains API credentials)
    package_root = Path(__file__).parent.parent
    pkg_env = package_root / ".env"
    if pkg_env.exists():
        _apply(pkg_env)

    # Also walk up from start_dir/cwd to merge any project-level .env
    current = start_dir or Path.cwd()
    # Don't re-apply the same file
    visited = {pkg_env.resolve()} if pkg_env.exists() else set()
    while True:
        env_file = current / ".env"
        if env_file.exists() and env_file.resolve() not in visited:
            _apply(env_file)
        parent = current.parent
        if parent == current:
            break
        current = parent


def load_config(config_path: str | Path | None = None) -> CodeOpsConfig:
    if config_path:
        path = Path(config_path)
    else:
        path = _find_config_path()

    # Load .env before expanding ${VAR} placeholders in YAML
    _load_dotenv(path.parent if path else None)

    if path and path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return _parse_config(raw)

    return CodeOpsConfig()


def _parse_config(raw: dict) -> CodeOpsConfig:
    config = CodeOpsConfig()

    if "models" in raw:
        config.models = {
            name: ModelConfig(
                provider=m.get("provider", "anthropic"),
                model=m.get("model", name),
                api_key=os.path.expandvars(m.get("api_key", "")),
                base_url=m.get("base_url"),
                max_tokens=m.get("max_tokens", 8192),
                temperature=m.get("temperature", 0.0),
                extra=m.get("extra", {}),
            )
            for name, m in raw["models"].items()
        }

    if "agents" in raw:
        config.agents = {
            name: AgentConfig(
                name=name,
                description=a.get("description", ""),
                model=a.get("model"),
                executor=a.get("executor"),
                tools=a.get("tools", []),
                system_prompt=a.get("system_prompt"),
                max_turns=a.get("max_turns", 100),
                sandbox=a.get("sandbox", False),
            )
            for name, a in raw["agents"].items()
        }

    if "rtk" in raw:
        r = raw["rtk"]
        config.rtk = RTKConfig(
            enabled=r.get("enabled", True),
            binary_path=r.get("binary_path"),
            auto_install=r.get("auto_install", True),
        )

    if "headroom" in raw:
        h = raw["headroom"]
        config.headroom = HeadroomConfig(
            enabled=h.get("enabled", True),
            port=h.get("port", DEFAULT_PROXY_PORT),
            savings_profile=h.get("savings_profile", "agent-90"),
            memory_enabled=h.get("memory_enabled", False),
            code_graph=h.get("code_graph", False),
            lean_ctx=h.get("lean_ctx", False),
        )

    if "memory" in raw:
        m = raw["memory"]
        config.memory = MemoryConfig(
            enabled=m.get("enabled", False),
            backend=m.get("backend", "hybrid"),
            remote_url=os.path.expandvars(m.get("remote_url", "")),
            db_path=m.get("db_path", ".codeops/memory.db"),
            embedding_model=m.get("embedding_model", "all-MiniLM-L6-v2"),
            max_memories=m.get("max_memories", 10000),
        )

    if not config.memory.remote_url:
        for key in ("CF_WORKER_MEMORY_URL", "MEMORY_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.memory.remote_url = env_url.rstrip("/")
                break

    if "mcp" in raw:
        c = raw["mcp"]
        config.mcp = MCPConfig(
            servers=c.get("servers", []),
            tools_allowlist=c.get("tools_allowlist", []),
        )

    if "a2a" in raw:
        a = raw["a2a"]
        config.a2a = A2AConfig(
            enabled=a.get("enabled", True),
            port=a.get("port", 9100),
            federation_url=os.path.expandvars(a.get("federation_url", "")),
            agent_discovery=a.get("agent_discovery", True),
            remote_agents=a.get("remote_agents", []),
            local_agents=a.get("local_agents", []),
        )

    if not config.a2a.federation_url:
        for key in ("CF_WORKER_A2A_URL", "A2A_FEDERATION_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.a2a.federation_url = env_url.rstrip("/")
                break

    if "agui" in raw:
        g = raw["agui"]
        config.agui = AGUIConfig(
            enabled=g.get("enabled", True),
            port=g.get("port", 9101),
            remote_url=os.path.expandvars(g.get("remote_url", "")),
            streaming=g.get("streaming", True),
            session_timeout_seconds=g.get("session_timeout_seconds", 3600),
            cors_origins=g.get("cors_origins", ["*"]),
        )

    if "spend" in raw:
        s = raw["spend"]
        config.spend = SpendConfig(
            enabled=s.get("enabled", True),
            remote_url=os.path.expandvars(s.get("remote_url", "")),
            daily_budget_usd=float(s.get("daily_budget_usd", 20.0)),
        )

    if not config.spend.remote_url:
        for key in ("CF_WORKER_SPEND_URL", "SPEND_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.spend.remote_url = env_url.rstrip("/")
                break

    if not config.agui.remote_url:
        for key in ("CF_WORKER_AGUI_URL", "AGUI_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.agui.remote_url = env_url.rstrip("/")
                break

    config.default_model = raw.get("default_model", "claude-sonnet")
    config.default_agent = raw.get("default_agent", "claude")

    if "workflow" in raw:
        w = raw["workflow"]
        config.workflow = WorkflowConfig(
            enabled=w.get("enabled", True),
            remote_url=os.path.expandvars(w.get("remote_url", "")),
            max_retries=w.get("max_retries", 3),
            retry_delay_seconds=w.get("retry_delay_seconds", 5.0),
            timeout_seconds=w.get("timeout_seconds", 300.0),
            checkpoint_dir=w.get("checkpoint_dir", ".codeops/checkpoints"),
        )

    if not config.workflow.remote_url:
        for key in ("CF_WORKER_WORKFLOW_URL", "WORKFLOW_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.workflow.remote_url = env_url.rstrip("/")
                break

    if "registry" in raw:
        r = raw["registry"]
        marketplace_url = os.path.expandvars(r.get("marketplace_url", ""))
        config.registry = RegistryConfig(
            enabled=r.get("enabled", True),
            agents_path=r.get("agents_path", ".codeops/agents"),
            skills_path=r.get("skills_path", ".codeops/skills"),
            marketplace_url=marketplace_url,
        )

    # Env fallback for marketplace URL
    if not config.registry.marketplace_url:
        for key in ("CF_WORKER_MARKETPLACE_URL", "MARKETPLACE_URL"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.registry.marketplace_url = env_url
                break

    if "scanner" in raw:
        s = raw["scanner"]
        config.scanner = ScannerConfig(
            enabled=s.get("enabled", True),
            auto_scan=s.get("auto_scan", True),
            scan_depth=s.get("scan_depth", 3),
        )

    if "ai_gateway" in raw:
        g = raw["ai_gateway"]
        config.ai_gateway = AIGatewayConfig(
            enabled=g.get("enabled", True),
            provider=g.get("provider", "cloudflare"),
            account_id=os.path.expandvars(g.get("account_id", "")),
            gateway_id=os.path.expandvars(g.get("gateway_id", "default")),
            api_token=os.path.expandvars(g.get("api_token", "")),
            cache_enabled=g.get("caching", {}).get("enabled", True),
            cache_ttl_seconds=g.get("caching", {}).get("ttl_seconds", 3600),
            cache_max_entries=g.get("caching", {}).get("max_entries", 1000),
            rate_limits_enabled=g.get("rate_limits", {}).get("enabled", True),
            rate_requests_per_minute=g.get("rate_limits", {}).get("requests_per_minute", 60),
            spend_limits_enabled=g.get("spend_limits", {}).get("enabled", True),
            spend_daily_budget_usd=g.get("spend_limits", {}).get("daily_budget_usd", 20.0),
            spend_per_agent_budget=g.get("spend_limits", {}).get("per_agent_budget", {}),
            fallback_enabled=g.get("fallback", {}).get("enabled", True),
            fallback_chain=g.get("fallback", {}).get("chain", []),
            fallback_retries=g.get("fallback", {}).get("retries", 3),
            dlp_enabled=g.get("dlp", {}).get("enabled", False),
            dlp_block_secrets=g.get("dlp", {}).get("block_secrets", True),
            dlp_block_pii=g.get("dlp", {}).get("block_pii", True),
        )

    if "cost_policy" in raw:
        cp = raw["cost_policy"]
        config.cost_policy = CostPolicyConfig(
            enabled=cp.get("enabled", True),
            max_task_cost_usd=float(cp.get("max_task_cost_usd", 1.0)),
            stop_on_budget_exceeded=cp.get("stop_on_budget_exceeded", True),
            prefer_cheaper_model_for=cp.get(
                "prefer_cheaper_model_for", ["docs", "tests", "summarization"]
            ),
            cheaper_model=cp.get("cheaper_model", "deepseek-v4-flash"),
            cheaper_model_map=cp.get("cheaper_model_map", {}),
        )

    if "telemetry" in raw:
        t = raw["telemetry"]
        pipeline_url = os.path.expandvars(t.get("pipeline_url", ""))
        config.telemetry = TelemetryConfig(
            enabled=t.get("enabled", True),
            events_dir=t.get("events_dir", ".codeops/events"),
            pipeline_url=pipeline_url,
            pipeline_enabled=t.get("pipeline_enabled", True),
            pipeline_timeout_seconds=float(t.get("pipeline_timeout_seconds", 5.0)),
            r2_enabled=t.get("r2_enabled", True),
        )

    if not config.telemetry.pipeline_url:
        for key in ("CF_PIPELINE_TELEMETRY_ENDPOINT", "PIPELINE_TELEMETRY_ENDPOINT"):
            env_url = os.environ.get(key, "").strip()
            if env_url:
                config.telemetry.pipeline_url = env_url.rstrip("/")
                break

    if "dspy" in raw:
        d = raw["dspy"]
        config.dspy = DSPyConfig(
            enabled=d.get("enabled", False),
            mode=d.get("mode", "shadow"),
            programs_dir=d.get("programs_dir", ".codeops/dspy/programs"),
            datasets_dir=d.get("datasets_dir", ".codeops/dspy/datasets"),
            optimizer=d.get("optimizer", "bootstrap_fewshot"),
            min_examples=int(d.get("min_examples", 20)),
            compile_budget=d.get("compile_budget", "small"),
            agents=d.get("agents", []),
            routing_mode=d.get("routing_mode", "shadow"),
            active_tag=d.get("active_tag", "production"),
            shadow_tag=d.get("shadow_tag", "candidate"),
            program_overrides=d.get("program_overrides", {}),
        )

    # Env overrides for DSPy
    if os.environ.get("DSPY_ENABLED", "").lower() in ("1", "true", "yes"):
        config.dspy.enabled = True
    if os.environ.get("DSPY_MODE", ""):
        config.dspy.mode = os.environ["DSPY_MODE"]

    return config


def create_default_config(path: Path) -> None:
    content = """\
# CodeOps Configuration
# =====================

default_model: claude-sonnet
default_agent: claude

models:
  claude-sonnet:
    provider: anthropic
    model: claude-sonnet-4-5-20250929
    api_key: "${ANTHROPIC_API_KEY}"
  claude-opus:
    provider: anthropic
    model: claude-opus-4-5-20250929
    api_key: "${ANTHROPIC_API_KEY}"
  gpt-4o:
    provider: openai
    model: gpt-4o
    api_key: "${OPENAI_API_KEY}"
  gemini-pro:
    provider: google
    model: gemini-2.5-pro
    api_key: "${GOOGLE_API_KEY}"

agents:
  claude:
    description: "Claude Code — основной агент разработки"
    model: claude-sonnet
  architect:
    description: "Агент архитектурного планирования"
    model: claude-opus
    tools: [github, gitlab, wiki]
  reviewer:
    description: "Агент код-ревью"
    model: gpt-4o
    tools: [github]
  bugfixer:
    description: "Агент исправления багов"
    model: claude-sonnet
    tools: [github, temporal]

rtk:
  enabled: true
  auto_install: true

headroom:
  enabled: true
  port: 8787
  savings_profile: agent-90
  memory_enabled: false

memory:
  enabled: false
  backend: hybrid
  remote_url: "${CF_WORKER_MEMORY_URL}"
  db_path: ".codeops/memory.db"

a2a:
  enabled: true
  port: 9100
  federation_url: "${CF_WORKER_A2A_URL}"
  agent_discovery: true
  remote_agents: []
  local_agents: []

agui:
  enabled: true
  port: 9101
  remote_url: "${CF_WORKER_AGUI_URL}"
  streaming: true
  session_timeout_seconds: 3600

spend:
  enabled: true
  remote_url: "${CF_WORKER_SPEND_URL}"
  daily_budget_usd: 20.0

mcp:
  servers: []
  tools_allowlist: []

workflow:
  enabled: true
  remote_url: "${CF_WORKER_WORKFLOW_URL}"
  max_retries: 3
  retry_delay_seconds: 5.0
  timeout_seconds: 300.0

registry:
  enabled: true
  agents_path: ".codeops/agents"
  skills_path: ".codeops/skills"

scanner:
  enabled: true
  auto_scan: true
  scan_depth: 3

ai_gateway:
  enabled: true
  provider: cloudflare
  account_id: "${CLOUDFLARE_ACCOUNT_ID}"
  gateway_id: "${CLOUDFLARE_AI_GATEWAY_ID}"
  api_token: "${CLOUDFLARE_API_TOKEN}"
  caching:
    enabled: true
    ttl_seconds: 3600
  rate_limits:
    enabled: true
    requests_per_minute: 60
  spend_limits:
    enabled: true
    daily_budget_usd: 20
    per_agent_budget: {}
  fallback:
    enabled: true
    chain: []
    retries: 3
  dlp:
    enabled: false
    block_secrets: true
    block_pii: true

cost_policy:
  enabled: true
  max_task_cost_usd: 1.00
  stop_on_budget_exceeded: true
  prefer_cheaper_model_for:
    - docs
    - tests
    - summarization
  cheaper_model: deepseek-v4-flash

telemetry:
  enabled: true
  events_dir: ".codeops/events"
  pipeline_url: "${CF_PIPELINE_TELEMETRY_ENDPOINT}"
  pipeline_enabled: true
  pipeline_timeout_seconds: 5
  r2_enabled: true

# DSPy optimizer layer (optional, requires: pip install codeops[dspy])
# mode: off | shadow | active
# shadow — runs in parallel, logs diff to telemetry, does NOT affect responses
# active — replaces AIGateway.chat() for agents listed in `agents`
dspy:
  enabled: false
  mode: shadow
  optimizer: bootstrap_fewshot
  min_examples: 20
  compile_budget: small
  routing_mode: shadow
  agents:
    - reviewer
    - documenter
    - architect
  active_tag: production
  shadow_tag: candidate
  program_overrides: {}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
