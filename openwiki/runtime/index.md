# Files

- [File-capable executor run lifecycle](executor-runs.md) - How AgentRunner resolves a file-capable executor for a target cwd, records its pre- and post-run state, enforces rollback policy, and publishes evidence, evaluation, live state, and telemetry.
- [Model gateway, provider routing, and FinOps](gateway-and-finops.md) - AIGateway is the governed model-call boundary for VOLY pipeline, A2A, SDK, and plan chat work. It documents request controls, cache and credential boundaries, provider fallback, and the separate accounting semantics of file-capable executor fallback.
