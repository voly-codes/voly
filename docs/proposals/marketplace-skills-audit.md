# Proposal: Marketplace Skills Audit and Cleanup

**Status:** planning — not started
**Complexity:** simple/moderate — mostly data review and a handful of safe,
reversible archive operations; no new architecture
**Recommended agent:** claude-code for the audit CLI tooling (Phase 1);
zen acceptable for mechanical dedup/archive work once Phase 1's report
exists and a human has picked which duplicate survives each group
**Related:** `docs/skills.md` (skill/marketplace reference — read first),
`cf-workers/marketplace/schema.sql`, `voly/registry/marketplace.py`,
`voly/registry/external_catalog.py`, `voly/pipeline/stages_context.py`
(`_stage_skill_suggest`/`_stage_skill_inject`, the consumers of this data)

## Goal

Audit and clean up the skills/plugins actually stored in VOLY's own
Cloudflare-hosted marketplace (D1 database `voly`, bound to
`cf-workers/marketplace/`) — not a third-party catalog. This is content and
data hygiene on infrastructure VOLY already runs, prompted by the same
review pass that led to the Context7 MCP addition and the workflow
graph/business-templates planning doc.

## Why this work — findings from a live audit

Queried directly against the production D1 database (`voly`,
`52103c13-d1fe-4a1e-b025-9ca687e67dbd`) rather than assumed. Numbers below
are a snapshot as of this writing — re-run the queries in Phase 1 before
acting on them, since `voly skill publish`/`archive` change these figures
over time.

| Finding | Number | Detail |
|---|---|---|
| Total skills | 372 | 351 `source=organization` (bulk-imported), 11 `builtin`, 10 `marketplace` (actually published by a user) |
| Total plugins | 81 | all `status=active` |
| **Never-used** | **372 / 372** | `usage_count = 0` for *every* skill — see "usage_count is dead code" below, this is a code gap, not proof nothing is used |
| Zero downloads | 342 / 372 | 30 skills *do* have nonzero `downloads` — that counter does work |
| **Duplicate names** | **18 groups** | e.g. `status`×3, `run`/`init`/`review`/`handoff`×2 each (generic, collision-prone ids), plus near-duplicate specialist skills: `chief-data-officer-advisor`, `chief-customer-officer-advisor`, `chief-ai-officer-advisor`, `general-counsel-advisor`, `iso42001-specialist`, `eu-ai-act-specialist`, `slo-architect`, `feature-flags-architect`, `kubernetes-operator`, `chaos-engineering`, `vpe-advisor`, `arquiteto-de-empresa` (Portuguese "enterprise architect") each ×2 |
| Everything imported in one window | — | `MIN(updated_at)`/`MAX(updated_at)` span ~14 days — every row was bulk-imported once (`voly registry import-external`) and never individually revised since |
| Missing compatibility metadata | 325 / 372 (87%) | `compatible_agents = '[]'` — `voly skill list --agent X` / any compatibility-based filtering is effectively non-functional for the large majority of the catalog |
| Near-stub content | 10 / 11 `builtin` skills | 70–103 chars each (`skill-nextjs`, `skill-docker`, `skill-kubernetes`, `skill-postgres`, `skill-testing`, `skill-dotnet`, `skill-architecture`, `skill-cloudflare`, `skill-security`, `skill-temporal`) — essentially unfleshed placeholders, not real injectable content. `organization`-sourced content is not stub-length (70–20,980 chars, avg ~8,100) |

### `usage_count` is dead code, not evidence of an unused catalog

`cf-workers/marketplace/src/index.ts` increments `downloads` on install/
download (`UPDATE skills SET downloads = downloads + 1 ...`, two call
sites) but **no code path anywhere increments `usage_count` after insert**
— it is only ever set once, at creation, from whatever value the source
catalog provided (usually `0`). This fully explains the 372/372 finding
above without needing to assume the marketplace is actually unused — 30
skills have real download activity, `usage_count` is simply a column
nothing writes to. Confirm before treating "372 never used" as a content
problem to solve; it's a telemetry gap to fix or a field to remove, not
missing adoption.

## Scope

### In scope

- reproducible audit tooling (a script/CLI, not one-off manual queries)
  producing the report above on demand;
- resolving the 18 duplicate-name groups: pick a canonical entry per group,
  archive the rest via the existing `MarketplaceClient.archive_skill()`
  (soft delete — `status='archived'`, already implemented, already excluded
  from default `active`-status listings — no new API needed);
- a decision on the 10 near-stub `builtin` skills: flesh out with real
  content, or archive as placeholders that never got built out;
- deciding whether `usage_count` gets wired up (a small worker change:
  increment on whatever "used in a real run" actually means — e.g. from
  `_stage_skill_inject`'s injection event, not just install) or is dropped
  from the schema/API surface as dead weight — either is a legitimate
  outcome, "leave it silently broken" is not.

### Non-goals

- rewriting the marketplace worker's schema or API beyond what's needed to
  either wire up or remove `usage_count`;
- backfilling `compatible_agents` for all 325 affected skills by hand — at
  this volume that needs either an automated heuristic (infer from
  `tags`/source repo — a real idea, but its own scoped follow-up, not
  bundled into an audit) or acceptance as a known, documented limitation;
  picking between those two is this proposal's job, doing the backfill
  itself is not;
- a UI for browsing/moderating the marketplace — `voly skill list`/`show`/
  the raw D1 queries are sufficient for an audit of this size;
- auditing *content quality* of all 351 organization-sourced skills
  individually — infeasible at this volume; sample-based spot checks are
  the realistic bar (see Phase 2).

## Delivery plan

### Phase 1 — Reproducible audit tooling

**Deliverables**

- a script or `voly registry audit` CLI subcommand that runs the queries
  behind the findings table above (total/by-source/by-status counts,
  duplicate-name groups, content-length outliers, empty-metadata counts,
  update-time clustering) against the configured marketplace, and prints a
  report — so this audit is a repeatable command, not manual D1 queries;
- output format: human-readable by default, `--json` for scripting the
  later phases against.

**Tests:** the query logic itself is straightforward SQL — a unit test
against a small fixture D1/SQLite instance (or the worker's local
`wrangler d1` dev mode) covering the duplicate-detection and outlier logic
is enough; no need to test against production data.

**Docs:** `docs/skills.md` — add the audit command under "Marketplace CLI."

**Done when:** running the tool reproduces (up to data drift since this
writing) the findings table above without hand-written SQL.

### Phase 2 — Duplicate resolution

**Process per duplicate group** (18 groups from the findings above):

1. Read both/all versions' `content` — for generically-named ones
   (`status`, `run`, `init`, `review`, `handoff`) these likely came from
   different source repos and mean genuinely different things; for the
   specialist-advisor duplicates, compare whether they're near-identical
   (safe to archive one) or meaningfully different personas that happen to
   share a name (rename one instead of archiving).
2. Pick a canonical id/name per group; `archive_skill()` the rest.
3. If a generic name is renamed rather than archived (e.g.
   `run` → `run-devops-checklist`), update anything that referenced the old
   id by name (spot-check `voly skill show <old-id>` still 404s cleanly
   post-archive, per the worker's existing `status='active'`-only default
   filtering).

**Tests:** none beyond re-running Phase 1's tool afterward and confirming
zero duplicate groups remain among `active` skills.

**Done when:** Phase 1's report shows 0 duplicate-name groups among active
skills.

### Phase 3 — Builtin stub cleanup

Two legitimate outcomes for each of the 10 near-stub `builtin` skills
(`skill-nextjs`, `skill-docker`, `skill-kubernetes`, `skill-postgres`,
`skill-testing`, `skill-dotnet`, `skill-architecture`, `skill-cloudflare`,
`skill-security`, `skill-temporal`):

- **flesh out** with real injectable content (a real Next.js/Docker/k8s/etc.
  skill body, matching the depth of the 351 organization-sourced skills);
- **archive** if a stub was never meant to ship as-is and nothing depends
  on the id existing.

Check `voly/registry/builtin_data.py` (the local Python-side builtin
definitions) for whether these 10 originate there or were separately
seeded directly into D1 — the fix differs (edit the Python source + re-seed,
vs. a direct marketplace edit) depending on which.

**Done when:** every `builtin`-source skill is either real content (>500
chars, matching the catalog's normal range) or explicitly archived — none
left in the 70–103 char stub state.

### Phase 4 — `usage_count` decision

Pick one:

- **wire it up**: increment in `cf-workers/marketplace/src/index.ts` from a
  real "used" signal — the natural point is
  `voly/pipeline/stages_context.py::_stage_skill_inject()` actually
  injecting a skill's content into a run, reported back to the worker
  (needs a new authenticated write path from the Python side, since
  `_stage_skill_inject` runs client-side, not inside the worker);
- **remove it**: drop the column/field from schema, API responses, and
  `voly/registry/skills.py`'s `Skill` dataclass if it's judged not worth
  the wiring effort right now.

Either is acceptable; leaving it as a silently-dead field that looks like
real telemetry is not — `voly skill show`'s output currently implies
`usage_count` means something.

**Done when:** `usage_count` either increments from a real signal, or has
been removed everywhere it's currently exposed as if it were live data.

## Dependency order

```text
Phase 1 (audit tooling)  ← do this first, everything else reads its report
    ↓
Phase 2 (dedup) ─────┐
Phase 3 (stub cleanup) ┼─ independent of each other, both need Phase 1's report
Phase 4 (usage_count)  ┘
```

## Testing strategy

```bash
# Phase 1
voly registry audit --json   # or wherever the command lands
# Phases 2-3, after each change:
voly registry audit          # confirm the specific finding it targeted is resolved
```

## Documentation requirements

| Change | Update |
|---|---|
| Audit CLI | `docs/skills.md` |
| Duplicate resolution / builtin content changes | `voly/registry/builtin_data.py` changes need no separate doc — content, not behavior |
| `usage_count` wired up or removed | `docs/skills.md`, `cf-workers/marketplace/schema.sql` comment if removed, `docs/backend/pipeline.md` if `_stage_skill_inject` gains a reporting call |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Archiving the wrong duplicate loses a meaningfully-different skill | Read `content` before archiving, not just names (Phase 2's explicit process) |
| A skill id is referenced somewhere outside the marketplace (a hardcoded `voly skill install skill-x` in a script, doc, or test) | Archiving is a soft delete (`status='archived'`), not a hard delete — recoverable if something breaks; grep the repo for the id before archiving anything genuinely load-bearing-looking |
| `usage_count` wiring adds a new authenticated write path with its own abuse surface | Scope it minimally (increment-only, rate-limited like the existing `downloads` counter) or choose removal instead — both are fine outcomes per Phase 4 |

## Success metrics

- Phase 1's audit tool exists and is used as the source of truth for the
  rest of this plan, replacing the one-off manual D1 queries this proposal
  was written from;
- 0 duplicate-name groups remain among active skills;
- every `builtin`-source skill is either real content or archived, none
  left in a stub state;
- `usage_count` is either live or gone — no field left implying telemetry
  that doesn't exist.

## Implementation checklist

```text
[ ] Phase 1  reproducible audit CLI/script
[ ] Phase 2  resolve 18 duplicate-name groups
[ ] Phase 3  flesh out or archive the 10 builtin stub skills
[ ] Phase 4  wire up or remove usage_count
```

## Changelog

- v0.1 — initial planning draft, written from a live audit of the
  production `voly` D1 database (372 skills, 81 plugins) queried directly
  via the Cloudflare D1 API rather than assumed from schema alone.
