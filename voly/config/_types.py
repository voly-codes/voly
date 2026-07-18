"""
Dataclass definitions for all VOLY configuration sections.

_DEFAULT_MODELS is defined at the bottom because VOLYConfig.get_model_config()
references it at call time (not at class-definition time), which avoids a
circular import with any module that imports ModelConfig first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_CONFIG_FILENAME = "voly.yaml"
DEFAULT_PROXY_PORT = 8787
DEFAULT_PXPIPE_PORT = 47821


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
class PxpipeConfig:
    enabled: bool = False
    port: int = DEFAULT_PXPIPE_PORT
    models: str = "claude-fable-5,gpt-5.6"
    auto_start: bool = False
    override_anthropic_base_url: bool = False


@dataclass
class MemoryConfig:
    enabled: bool = False
    # local = SQLite only
    # hybrid = SQLite + CF memory Worker (remote_url)
    # agent_memory = SQLite + Cloudflare Agent Memory HTTP API
    backend: str = "hybrid"
    remote_url: str = ""
    db_path: str = ".voly/memory.db"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_memories: int = 10000
    # Cloudflare Agent Memory (backend=agent_memory)
    agent_memory_account_id: str = ""
    agent_memory_namespace: str = "voly"
    agent_memory_profile: str = "default"


@dataclass
class A2AConfig:
    enabled: bool = True
    port: int = 9100
    federation_url: str = ""
    agent_discovery: bool = True
    remote_agents: list[str] = field(default_factory=list)
    local_agents: list[dict[str, Any]] = field(default_factory=list)
    token: str = ""
    auto_dispatch: bool = True
    min_flags_for_dispatch: int = 2
    task_timeout_seconds: float = 600.0
    # "local"  → sub-agents run in-process via AIGateway.chat() with per-role
    #            model tier + skills assigned by the lead orchestrator.
    # "federation" → dispatch sub-tasks to remote A2A agents (federation_url).
    execution_mode: str = "local"
    # Model used by the lead orchestrator to assign tiers/skills. Empty → resolve
    # a strong (premium) provider from the healthy pool automatically.
    lead_model: str = ""
    # When to spend an LLM call on the lead orchestrator:
    #   auto          — only for non-standard decompositions (unknown roles or
    #                   >5 sub-tasks); standard role sets use the deterministic
    #                   role→tier map, saving a premium chat before any code.
    #   llm           — always call the lead model (legacy behavior).
    #   deterministic — never call; role map + top skill candidates.
    lead_mode: str = "auto"
    # Hybrid multi-agent (docs/proposals/hybrid-multiagent-executor.md):
    # implement roles may use AgentRunner+cwd; plan/review stay on chat().
    hybrid_code_gen: bool = True
    hybrid_require_cwd: bool = True
    executor_default: str = "claude-code"
    # Empty → use built-in default set (developer, bugfixer, tester).
    executor_roles: list[str] = field(default_factory=list)
    # Wave parallelism (P4): roles whose dependencies are all satisfied run in
    # the same wave. Chat roles of a wave execute concurrently (bounded by
    # max_parallel_roles); executor roles always run serially (shared cwd/git).
    parallel_waves: bool = True
    max_parallel_roles: int = 3
    # Per-role tier overrides (P4): reduce premium calls for roles where quality
    # difference is acceptable. E.g. {architect: standard} saves one premium
    # call per run. Empty → use built-in defaults from assignment._ROLE_TIER.
    role_tiers: dict[str, str] = field(default_factory=dict)


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
class RegistryConfig:
    enabled: bool = True
    agents_path: str = ".voly/agents"
    skills_path: str = ".voly/skills"
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
    # Layer-A delegation: route non-CF calls through one external gateway
    # (e.g. "omniroute") first; direct adapters are the fallback. Empty = off.
    upstream: str = ""
    upstream_model: str = ""            # override model sent upstream ("auto" = OmniRoute auto-combo)
    upstream_fallback_direct: bool = True
    # BYOK (Store Keys): provider API keys live in CF Secrets Store, the
    # gateway resolves them per request (docs/backend/ai-gateway.md § BYOK).
    byok_enabled: bool = False
    byok_providers: list[str] = field(default_factory=list)  # empty = all supported
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    cache_max_entries: int = 1000
    # Persist the response cache to disk so repeat tasks hit across requests /
    # restarts (each web /api/run builds a fresh gateway). Empty → in-memory only.
    cache_persist_dir: str = ".voly/gateway_cache"
    rate_limits_enabled: bool = True
    rate_requests_per_minute: int = 60
    spend_limits_enabled: bool = True
    spend_daily_budget_usd: float = 20.0
    spend_per_agent_budget: dict[str, float] = field(default_factory=dict)
    fallback_enabled: bool = True
    fallback_chain: list[dict[str, str]] = field(default_factory=list)
    fallback_retries: int = 3
    # Whole-response HTTP timeout for provider urlopen calls. Stall → error → fallback.
    request_timeout_seconds: float = 15.0
    dlp_enabled: bool = False
    dlp_block_secrets: bool = True
    dlp_block_pii: bool = True


@dataclass
class ExecutorSafetyConfig:
    """Guardrails for file-writing executors (docs/backend/executors.md § Safety)."""

    enabled: bool = True
    # Run executors normally but roll back all file changes afterwards,
    # keeping the diff preview in result metadata. Per-call override:
    # `voly run --dry-run` / RunRequest.dry_run.
    dry_run: bool = False
    # fnmatch patterns (repo-relative path or basename); empty → built-in
    # defaults (.env*, *.pem, *.key, id_rsa*, .git/** …).
    protected_paths: list[str] = field(default_factory=list)
    # 0 = unlimited; exceeding rolls back the whole run.
    max_files_touched: int = 0


@dataclass
class MCPConfig:
    servers: list[dict[str, Any]] = field(default_factory=list)
    tools_allowlist: list[str] = field(default_factory=list)


@dataclass
class CloudConfig:
    """Link to a VOLY Cloud control plane — local runs report into the shared
    org history (voly-cloud ``POST /cloud/v1/tenants/{id}/runs/report``).

    ``token`` is the tenant edge JWT from the org manifest, not a user session
    token. Reporting is best-effort telemetry: metadata only (task text capped,
    cost, files touched), never file contents.
    """

    enabled: bool = False
    base_url: str = ""      # control plane, e.g. http://127.0.0.1:7790
    tenant_id: str = ""
    token: str = ""         # prefer env VOLY_CLOUD_TOKEN over yaml
    user_id: str = ""       # optional attribution shown in the org timeline
    device_id: str = ""     # AgentDevice id — required for heartbeat / runs/report
    timeout_seconds: float = 5.0


@dataclass
class TelemetryConfig:
    enabled: bool = True
    events_dir: str = ".voly/events"
    pipeline_url: str = ""
    pipeline_enabled: bool = True
    pipeline_timeout_seconds: float = 5.0
    r2_enabled: bool = True
    # Resilience (Этап 2, Rung A): in-flight run tracking + watchdog.
    runs_dir: str = ".voly/runs"
    # A run is "stale" when its heartbeat is older than stale_factor × task_timeout.
    watchdog_stale_factor: float = 2.0


@dataclass
class PlanConfig:
    """Plan state machine + verification gates (Rung B). See plan-gate-verification proposal."""

    enabled: bool = False
    # off: plan subsystem not used by multi-agent (CLI still works when invoked)
    # shadow: run verifiers and log; do not hard-block next step on verify fail
    # active: hard gate — next step only after deps verified
    mode: str = "shadow"
    store_dir: str = ".voly/plans"
    max_step_retries: int = 1
    # stop | retry | continue — active mode; shadow treats verify fail as soft
    default_on_verify_fail: str = "stop"
    command_timeout_seconds: float = 60.0
    allow_skip: bool = False
    # Default executor for mode=executor steps without step.executor
    executor_default: str = "claude-code"
    step_timeout_seconds: int = 300
    max_turns: int = 30
    # When enabled and mode != off, multi-agent run_local uses plan gates (PR4).
    a2a_attach: bool = True
    # Default acceptance for chat roles: non-empty model output.
    chat_require_output: bool = True
    # Opt-in: executor roles must leave a git dirty/diff (files_touched or porcelain).
    executor_require_git_diff: bool = False
    # Mandatory executor policy: changed text files may not exceed this many lines.
    executor_file_line_limit: int = 300
    # Architect may raise the limit up to this cap with strict plan markers.
    architect_approved_file_line_limit: int = 500
    # Opt-in: tester role runs this command as acceptance (e.g. "pytest -q").
    tester_command: str = ""

    VALID_MODES = frozenset({"off", "shadow", "active"})
    VALID_ON_FAIL = frozenset({"stop", "retry", "continue"})


@dataclass
class DSPyConfig:
    """DSPy optimizer layer — sits between Headroom and AIGateway.chat()."""

    enabled: bool = False
    # off: DSPy not used at all
    # shadow: runs in parallel, result logged but not returned to caller
    # active: DSPy result replaces AIGateway.chat() for opted-in agents
    mode: str = "shadow"
    programs_dir: str = ".voly/dspy/programs"
    datasets_dir: str = ".voly/dspy/datasets"
    optimizer: str = "bootstrap_fewshot"
    min_examples: int = 20
    # small | medium | large — controls compile budget (num trials / epochs)
    compile_budget: str = "small"
    # agents to apply DSPy to; empty list = all agents when mode=active
    agents: list[str] = field(default_factory=list)
    # routing_mode: shadow | active — controls whether DSPy also drives routing
    routing_mode: str = "shadow"
    # model to use for DSPy inference; empty = use route model (may fail if no balance)
    # Recommended: set to a cheap/free model, e.g. "llama-scout" (workers-ai)
    model: str = ""
    # provider for DSPy model; empty = auto-resolved from model config
    provider: str = ""
    # program registry / version manager
    active_tag: str = "production"
    shadow_tag: str = "candidate"
    program_overrides: dict[str, str] = field(default_factory=dict)

    VALID_MODES = {"off", "shadow", "active"}

    @classmethod
    def validate(cls, **kwargs: Any) -> bool:
        model = kwargs.get("model", "")
        provider = kwargs.get("provider", "")
        mode = kwargs.get("mode", "")

        if model and not provider:
            raise ValueError("DSPyConfig: model is set but provider is empty")
        if provider and not model:
            raise ValueError("DSPyConfig: provider is set but model is empty")
        if mode not in cls.VALID_MODES:
            raise ValueError(
                f"DSPyConfig: mode must be one of {cls.VALID_MODES}, got {mode!r}"
            )
        return True


@dataclass
class VOLYConfig:
    models: dict[str, ModelConfig] = field(default_factory=dict)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    rtk: RTKConfig = field(default_factory=RTKConfig)
    headroom: HeadroomConfig = field(default_factory=HeadroomConfig)
    pxpipe: PxpipeConfig = field(default_factory=PxpipeConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    a2a: A2AConfig = field(default_factory=A2AConfig)
    agui: AGUIConfig = field(default_factory=AGUIConfig)
    spend: SpendConfig = field(default_factory=SpendConfig)
    registry: RegistryConfig = field(default_factory=RegistryConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    ai_gateway: AIGatewayConfig = field(default_factory=AIGatewayConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    cost_policy: CostPolicyConfig = field(default_factory=CostPolicyConfig)
    executor_safety: ExecutorSafetyConfig = field(default_factory=ExecutorSafetyConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    cloud: CloudConfig = field(default_factory=CloudConfig)
    dspy: DSPyConfig = field(default_factory=DSPyConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)
    default_model: str = "claude-sonnet"
    default_agent: str = "claude"
    default_cwd: str = ""   # VOLY_PROJECT_CWD or voly.yaml: default_cwd

    def get_model_config(self, name: str | None = None) -> ModelConfig:
        from voly.config._defaults import _DEFAULT_MODELS
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
