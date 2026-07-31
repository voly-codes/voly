# Research-first shadow pilot

Phase 4 adds an offline evidence pass before implementation decisions. It is a
pilot, not an active router: the output is a typed `reuse | adapt | build`
recommendation and never changes the task, model, agent, or tools.

Evidence is consulted in this order:

1. selected modules from `.voly/reuse/reports/latest.json`;
2. matching source and documentation in the current project;
3. no network fallback.

Tasks are admitted only when deterministic size or risk signals justify the
latency. Small edits are recorded as ineligible. Reports include candidates,
the selected candidate, rejected alternatives, provenance, duration, and
`network_used: false`. Runtime artifacts live in
`.voly/research/reports/` and are ignored by Git.

```yaml
research:
  enabled: false
  mode: shadow
  reports_dir: .voly/research/reports
  max_candidates: 8
  max_duration_ms: 1000
```

Use `voly research shadow "<task>" --cwd .` for one decision. Use
`voly research benchmark "<task 1>" "<task 2>" --cwd .` for the paired
build-only baseline. `builds_avoided` means the pilot found evidence strong
enough to recommend reuse or adaptation; it is an experiment metric, not a
claim that production outcomes improved.

When `research.enabled` is true, `Pipeline.run()` emits
`RESEARCH_SHADOW` after `INIT` and stores the report on
`PipelineResult.research_report`. Passing
`context["research_first_shadow"] = true` enables it for one run.
