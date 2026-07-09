"""Default voly.yaml template written by `voly init`."""

from pathlib import Path

_DEFAULT_YAML = """\
# VOLY Configuration
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
  db_path: ".voly/memory.db"

a2a:
  enabled: true
  port: 9100
  federation_url: "${CF_WORKER_A2A_URL}"
  agent_discovery: true
  remote_agents: []
  local_agents: []
  auto_dispatch: true
  min_flags_for_dispatch: 2
  execution_mode: local          # local | federation
  lead_model: ""                 # empty → premium from healthy pool
  # Hybrid multi-agent: implement roles use executors when cwd is set
  # (see docs/proposals/hybrid-multiagent-executor.md). PR1 = mode map +
  # structure; real AgentRunner wiring is PR2.
  hybrid_code_gen: true
  hybrid_require_cwd: true
  executor_default: claude-code
  executor_roles:
    - developer
    - bugfixer
    - tester

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

registry:
  enabled: true
  agents_path: ".voly/agents"
  skills_path: ".voly/skills"

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
  # Layer-A delegation: "" = off, "omniroute" = route non-CF calls through
  # a local OmniRoute instance first (direct adapters remain the fallback).
  upstream: ""
  upstream_model: ""          # "auto" = OmniRoute auto-combo; "" = passthrough
  upstream_fallback_direct: true
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
  events_dir: ".voly/events"
  pipeline_url: "${CF_PIPELINE_TELEMETRY_ENDPOINT}"
  pipeline_enabled: true
  pipeline_timeout_seconds: 5
  r2_enabled: true

# Web UI JWT auth (optional, requires: pip install 'voly[ui]')
# Default: disabled — API open on localhost only. Enable before any network exposure.
# Secrets: prefer VOLY_JWT_SECRET / VOLY_AUTH_USERS env vars over yaml.
auth:
  enabled: false
  jwt_secret: "${VOLY_JWT_SECRET}"
  jwt_algorithm: HS256
  access_token_expire_minutes: 60
  # username: password (MVP plaintext; override via VOLY_AUTH_USERS=user:pass,…)
  users: {}
  # When auth is on, avoid ["*"] — middleware will fall back to localhost origins.
  cors_origins:
    - "http://localhost:7788"
    - "http://127.0.0.1:7788"
    - "http://localhost:5173"
    - "http://127.0.0.1:5173"

# DSPy optimizer layer (optional, requires: pip install voly[dspy])
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


def create_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_YAML)
