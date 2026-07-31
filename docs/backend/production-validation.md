# Production validation and staged activation

Phase 9 is a RAT probe for the assumption that imported capability mechanics
improve real VOLY outcomes rather than merely adding latency and orchestration.
The probe separates routing correctness from value evidence.

## Versioned suite

`voly/capability/benchmark_suite_v1.json` contains exactly 20 representative
tasks:

- six security-reviewer tasks;
- six TDD tasks;
- six Python-review tasks;
- two tasks that must use native VOLY;
- seven held-out tasks across the suite.

`voly capability evaluated benchmark` runs an offline routing probe. It uses
temporary synthetic activation only to exercise matching, never writes that
state to the evaluated store, performs no model calls, and always reports:

```json
{"synthetic_outcomes": true, "activation_allowed": false}
```

Routing success is infrastructure evidence, not value evidence.

## Real paired outcomes

Real baseline and variant runs are imported with
`voly capability evaluated record`. Each record names exactly one changed
capability, executor, experiment ID, quality scores, outcome metrics and
held-out status. A record declaring multiple changed capabilities is rejected.

For each pilot, the production gate currently requires six measured outcomes,
including at least two held-out outcomes:

- `activate`: the complete sample passes every success criterion and has
  positive paired added value;
- `retire`: the complete sample fails value or outcome criteria;
- `keep-pilot`: evidence or held-out coverage is incomplete.

The decision is reproducible from the local append-only evidence records:

```bash
voly capability evaluated activation-plan --executor claude-code
```

## Staged activation and Cloudflare

`activate-ready --yes` recomputes decisions and locally activates only packs
whose decision is `activate`. It never edits `voly.yaml` and never deploys a
Cloudflare Worker.

Cloudflare deployment becomes ready only when:

1. at least one capability passes local measured validation;
2. no capability remains in `keep-pilot`;
3. activation is still explicitly enabled in configuration/deployment review.

Until then `cloudflare_deploy_ready=false`. Deployment remains a separate,
explicit operational phase.
