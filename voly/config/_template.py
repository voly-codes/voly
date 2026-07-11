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
  # BYOK (Store Keys): provider API keys live in CF Secrets Store and are
  # resolved by the gateway per request — no provider keys in .env needed.
  # Requires an authenticated gateway + CF_AIG_TOKEN. VOLY_BYOK env overrides.
  # See docs/backend/ai-gateway.md § BYOK (Store Keys).
  byok_enabled: false
  byok_providers: []          # empty = all supported (anthropic, openai, google-ai-studio, deepseek)
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

# Guardrails for file-writing executors (rollback is git-based; requires a
# git repo in cwd). dry_run reverts all changes after the run, keeping a diff
# preview in the result. protected_paths: fnmatch, empty = built-in defaults
# (.env*, *.pem, *.key, id_rsa*, .git/**).
executor_safety:
  enabled: true
  dry_run: false
  protected_paths: []
  max_files_touched: 0     # 0 = unlimited; exceeding rolls back the whole run

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

# Plan gates (Rung B): multi-step plans with acceptance checks.
# CLI: voly plan run <file.yaml>  — see docs/proposals/plan-gate-verification.md
plan:
  enabled: false
  mode: shadow                 # off | shadow | active
  store_dir: ".voly/plans"
  max_step_retries: 1
  default_on_verify_fail: stop # stop | retry | continue
  command_timeout_seconds: 120
  allow_skip: false
  executor_default: claude-code
  step_timeout_seconds: 300
  max_turns: 30
  # PR4: attach plan gates to multi-agent A2A when enabled+mode
  a2a_attach: true
  chat_require_output: true
  executor_require_git_diff: false   # opt-in
  tester_command: ""                 # e.g. "pytest -q"

# Web UI is open on localhost only. Authentication (JWT / SSO), team dashboards,
# and org spend governance are commercial Team-tier features — they live in the
# closed voly-cloud distribution, not in this open-core repo.

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
