# Gateway and executors

This page explains how VOLY talks to models and how it executes file-writing work.

## AI Gateway

`voly/ai_gateway/gateway.py` is the central model-routing layer. Its `chat()` method applies the middleware stack in this order:

1. DLP checks
2. Cache lookup
3. Rate limiting
4. Spend limiting
5. Routing
6. Provider execution
7. Empty-content guard

The gateway can either call Cloudflare AI Gateway for CF-native providers or delegate to direct adapters. It also supports an upstream delegation mode, which the architecture docs describe as the layer-A make-vs-delegate split: a single upstream gateway such as OmniRoute can own provider selection, with direct adapters retained as fallback.

Important gateway behaviors:

- cache keys can be scoped to project state
- empty 200 responses are converted into synthetic errors so they can fall back
- spend and cache behavior are tracked in gateway metrics
- the gateway is the canonical place to add provider support and cost logic

## Executors

`voly/runner/agent_runner.py` is the file-capable execution path. It resolves executors, optionally refines the task with DSPy, executes the backend, and applies billing fallback when an executor signals a billing error.

The fallback chain documented in code is:

`claude-code → wrangler → opencode → zen`

Not every backend is in that chain. Only file-writing executors belong there; text-only providers such as `deepseek` and `mimo` are excluded.

### File patching

`voly/executor/patch.py` is used by the Wrangler path to apply FILE blocks or unified diffs to the target project. It is intentionally defensive about file paths and uses path traversal checks.

## Why this split exists

The repository deliberately separates model routing from file writes. That lets the pipeline use centralized caching, DLP, and spend controls, while executors remain responsible for touching the filesystem of the target project.

## What to watch when changing gateway or executors

- Update the gateway docs and config docs whenever provider names, fallback behavior, or cost policy changes.
- Keep billing-error classification aligned with executor tests.
- Preserve the rule that text-only providers are not file-writing executors.
- When adding a provider, update gateway routing, cost accounting, and the configuration defaults together.

## Useful source files

- `voly/ai_gateway/gateway.py`
- `voly/ai_gateway/error_classifier.py`
- `voly/runner/agent_runner.py`
- `voly/executor/base.py`
- `voly/executor/patch.py`
- `docs/backend/ai-gateway.md`
- `docs/backend/executors.md`
