# Proposal: Visual Workflow Graph UI and Business-Vertical Templates

**Status:** planning — not started
**Complexity:** Phase A (graph UI) moderate/frontend-only; Phase B (templates) simple-per-template but iterative
**Recommended agent:** claude-code (Phase A — needs UI iteration + visual verification); zen acceptable for individual Phase B templates once the pattern is established
**Related:** `docs/proposals/agent-workflow-sdk.md` (the SDK this builds on — read first),
`docs/backend/sdk.md`, `docs/frontend/components.md`, `docs/frontend/overview.md`,
`examples/workflows/README.md`, `examples/workflows/BENCHMARK.md`

## Goal

Close the two gaps identified while comparing VOLY's Workflow SDK against
Open Executive (a single-vendor "AI executive team" product) and against the
proposal's own deferred scope:

1. **A real visual workflow graph**, not a status list. `ui/src/lib/components/workflows/WorkflowsPage.svelte`
   today renders a top-to-bottom list of node cards — accurate, but not the
   "workflow graph UI" the original proposal's Phase 5 asked for. This is
   pure frontend polish; the backend (`GET /api/workflows/{plan_id}`) already
   returns everything a graph needs (`depends_on`, `status`, `cost_usd`,
   `duration_ms`, `role`, `model`/`provider`).
2. **Business-vertical workflow templates** (board prep, fundraising prep,
   incident postmortems, etc.) — the concrete product gap named in the
   Open Executive comparison: VOLY's `examples/workflows/` has 7 solid
   *developer-tooling* examples and zero *business* ones, while that's
   exactly what made Open Executive's onboarding land fast.

Neither phase touches `voly/sdk/`'s public contracts. Both build entirely on
what already exists and is tested: `Workflow`, the six presets, the
approval gate, and the `/api/workflows/*` REST surface.

## Why this work, and why now

This is the direct continuation of `docs/proposals/agent-workflow-sdk.md`
after its Phase 0–6 (+ the post-Phase-6 `Agent` capability work: tool
calling, structured output, capability routing) all landed. Two items were
identified as remaining and explicitly deferred at the time:

- Phase 5's own text: *"defer drag-and-drop editing until the read-only
  graph contract is stable"* — the read-only contract (`GET /api/workflows`)
  has been stable and tested since PR5. A visual graph is the natural next
  step, still short of an editor.
- The Open Executive comparison's conclusion: VOLY's infrastructure is now
  comparable or ahead (governance, resume, multi-provider fallback), but its
  "go-to-market wedge" — a finished, curated scenario a new user can run in
  minutes — is not. Business templates are that wedge.

## Scope

### In scope

**Phase A:**
- a real node-link graph rendering for one `Plan`'s nodes and `depends_on`
  edges, replacing (or offered alongside) the current list view;
- automatic layout, zoom/pan, live status coloring matching the existing
  list view's semantics (`pending`/`running`/`verifying`/`verified`/`failed`);
- click-through node detail (same fields the list already shows: role,
  model/provider, cost, duration, error, approve/reject for a paused
  `human_review` node) — no new backend fields required.

**Phase B:**
- 4–6 curated business-vertical workflow templates built on the existing
  `Workflow`/preset API, each with the same docstring contract
  (`examples/workflows/`'s "expected output, required credentials,
  cost/safety notes") and an offline contract test;
- an explicit, repeatable process for iterating on template *prompt
  quality* — this is not a one-shot implementation the way a preset is.

### Non-goals

- a drag-and-drop graph **editor** (still explicitly deferred — this
  proposal only covers *viewing* a compiled graph, matching Phase 5's own
  boundary);
- new `voly/sdk/` public contracts, new `PlanStep`/`NodeResult` fields, or
  any backend change to `/api/workflows/*` — Phase A is presentation-layer
  only over data that already exists;
- new topology presets (`voly/sdk/presets.py`) — business templates compose
  existing presets/`Workflow.add()`, they do not need new graph shapes;
- wholesale import of third-party skill-pack content (see "Content sourcing"
  under Phase B) — evaluated case by case, not a bulk pull.

## Phase A — Visual workflow graph

### Design decision: hand-rolled layered layout, not a graph library

A `Plan` is guaranteed acyclic (`PlanEngine.validate()` rejects cycles at
compile time — `tests/test_sdk_workflow.py::test_cycle_rejected`), so a full
force-directed physics layout is unnecessary complexity for what's
mathematically a DAG. Recommended approach:

1. Compute each node's **column** = longest path length from a root (a node
   with no `depends_on`) — a single topological pass, no iteration needed.
2. Position nodes in CSS grid columns by that number; multiple nodes sharing
   a column are stacked vertically in declaration order (matches the
   existing list view's ordering guarantee).
3. Draw `depends_on` edges as SVG lines/paths between column N and column
   N+1 (or further, for a node depending on a non-adjacent ancestor).
4. Zoom/pan via a CSS `transform: scale()`/`translate()` on a wrapping
   `<svg>`/`<div>`, driven by wheel/drag events — no new dependency needed
   for this either.

This matches the existing hand-rolled, no-library style already used by
`WorkflowGraph.svelte`/`LiveAgentGraph.svelte` (`docs/frontend/components.md`)
rather than introducing a graph-layout npm dependency (`dagre`, `elkjs`,
`d3-dag`, ...). The tradeoff: a hand-rolled layered layout looks clean for
the topology shapes VOLY's presets actually produce (chains, fan-out/fan-in,
small councils) but will look progressively worse than a real layout engine
on a large, irregular hand-built graph. Given `MAX_*` bounds on every preset
(10–20 nodes) and that `examples/workflows/`'s largest example has 6 nodes,
this is judged sufficient — revisit only if real usage produces graphs a
layered column layout renders poorly.

**Deliverables**

- extend or add alongside `WorkflowsPage.svelte`: a graph canvas component
  (e.g. `ui/src/lib/components/workflows/WorkflowGraphCanvas.svelte`) taking
  the same `GET /api/workflows/{plan_id}` response shape the list view
  already consumes — no new API client function needed
  (`fetchWorkflow(planId)` already exists);
- a toggle between list/graph view (list view stays — it is more scannable
  for a 2–3 node workflow; the graph view earns its complexity on wider
  fan-out shapes) or, if UI review during implementation shows the graph
  view is strictly better in all observed cases, replace the list view
  outright — this is an implementation-time call, not decided here;
- click-through detail (reuse the existing per-node detail markup from the
  current list view — do not fork a second rendering of the same fields);
- approve/reject on a `verifying` + `human_review` node — reuses
  `decideWorkflowNode()`, already in `ui/src/lib/api/client.js`.

**Tests**

- component-level: a fixture Plan (linear chain, fan-out/fan-in,
  single-node) renders the expected column count and edge count;
- no backend test changes are expected — this is a pure rendering feature
  over an already-tested API contract. If implementation reveals a real gap
  in what the API returns (unlikely, but note it if found — don't
  silently work around it in the frontend).

**Docs:** `docs/frontend/components.md` (extend the existing
`WorkflowsPage.svelte` entry or add a new one), `docs/frontend/overview.md`
if a new file is added, `docs/backend/sdk.md` (update the Phase 5 status
line — "no drag-and-drop editor" stays true, "list view only" would not).

**Done when:** a multi-node workflow (at least one fan-out/fan-in shape,
e.g. `examples/workflows/02_parallel_market_analysis.py`'s output) is
visually inspectable as a graph — verify in an actual browser per this
repo's UI-change convention, not just `npm run build` succeeding.

## Phase B — Business-vertical workflow templates

### Candidate templates (initial set — pick 4–6, do not attempt all at once)

| Template | Shape | Preset/style |
|---|---|---|
| `board_prep` | metrics gather → deck draft → review | `sequential` or `planner_generator_evaluator` |
| `fundraising_prep` | market research → pitch draft → financial-model review | `sequential` |
| `weekly_ops_review` | N read-only investigators → synthesis | `supervisor_workers` (mirrors example 2/5) |
| `incident_postmortem` | timeline reconstruction → root cause → action items | `sequential` |
| `competitor_analysis` | N analyst agents → judge | `council` |
| `contract_review_intake` | draft summary → **human approval** → filed | manual `Workflow` with `approval=True` (mirrors example 4) |

Each is a thin, VOLY-flavored composition of what already exists —
`sequential`/`supervisor_workers`/`council`/manual `Workflow.add()` with
domain-specific `Agent.instructions` and task text. None require new SDK
code. This table is a starting point, not a commitment — cut anything that
doesn't survive the quality-iteration step below.

### Why this is "long, not code" — the actual process

Building the graph shape for a template takes under an hour (it's a
`sequential()`/`council()` call with different strings, per
`BENCHMARK.md`'s own measured line counts). The work that actually takes
time is the same problem any prompt-engineering effort has: does the output
a `board_prep` template produces actually read like a usable board deck
draft, or generic filler? That can't be settled with an offline contract
test the way `sequential_failure_blocks_downstream` was — a contract test
proves the *topology* behaves (dependency handoff reaches the next node,
failure blocks correctly), not that the *content* is good.

**Recommended process per template** (repeat, don't batch):

1. Draft the graph + initial `Agent.instructions` (following existing
   examples' pattern).
2. Run it live (not `--offline`) against 2–3 realistic sample tasks a real
   user would give it.
3. Read the actual output critically. Revise `instructions`/task text —
   this is the iteration loop; expect several passes per template.
4. Once output quality is acceptable, add the same offline contract test
   the rest of the catalog has (topology + dependency handoff + failure
   propagation) using canned fakes — this proves the *graph* stays correct
   over time, it is not a substitute for step 2–3's human judgment and
   was never meant to catch a prompt-quality regression.
5. Ship with the same docstring contract as `examples/workflows/`
   (expected output, required credentials, cost/safety notes).

This is why the estimate is "iterative, not one-shot": steps 2–3 are
judgment calls that take real sample runs, not a fixed engineering
duration. Budget per template accordingly — a template that needs 5 rounds
of revision is not a sign something is broken.

### Content sourcing: third-party skill packs as a starting point, not a shortcut

The Claude Skills audit that motivated this proposal surfaced real,
maintained business skill packs (`coreyhaines31/marketingskills`,
`charlie947/social-media-skills`, and Anthropic's own
`claude.com/plugins/{finance,small-business,legal}`) that cover similar
ground to some candidate templates above. These may be useful as **prompt
inspiration** — reading how a mature marketing-skills repo frames a
copywriting task is legitimate research — but must not be imported
wholesale as VOLY templates:

- quality/trust is unverified for community packs (see the earlier audit:
  the official Anthropic plugin pages' own stated skill counts didn't even
  match the viral post that named them — 15 vs. a claimed 31 for
  Small Business);
- a template that's a thin wrapper around someone else's unreviewed prompt
  content defeats the point of step 2–3 above (critically reading output
  quality against VOLY's own bar, not inheriting someone else's).

If a specific external skill's *content* proves genuinely strong after
reading it, adapting its ideas into a VOLY-authored `Agent.instructions`
is fine — copying it verbatim as a dependency is not, and importing it via
`voly registry import-external` (which exists and works, per the earlier
audit's follow-up options) should be treated as a separate, explicit
decision per pack, not bundled into this proposal.

**Deliverables**

- `examples/workflows/business/` (new subdirectory, mirroring the existing
  catalog's per-file docstring contract) — 4–6 templates from the table
  above, however many survive the quality-iteration process;
- `examples/workflows/business/README.md` — same shape as the top-level
  catalog README, plus a short note pointing at this proposal's "why this
  is long, not code" section so a future contributor doesn't assume a
  template is a 30-minute task.

**Tests:** one offline contract test per shipped template (topology +
dependency handoff + failure propagation), following
`tests/test_examples_workflows.py`'s existing pattern — add to that file or
a new `tests/test_examples_workflows_business.py`, contributor's call at
implementation time.

**Docs:** `examples/workflows/README.md` (link to the new subdirectory),
`docs/backend/sdk.md` (a one-line mention, matching how Phase 6 is
mentioned there today).

**Done when:** at least 3 templates have been run live against realistic
sample tasks, revised at least once based on actual output, and shipped
with an offline contract test — not "the graph compiles," which was true
on the first draft of every template and proves nothing about quality.

## Dependency order

```text
Phase A (graph UI)         — independent, no dependency on Phase B
Phase B (business templates) — independent, no dependency on Phase A
```

Both build on already-landed work (`agent-workflow-sdk.md` Phase 0–6 +
post-Phase-6 `Agent` capabilities). Neither blocks the other — they can run
in parallel or either order.

## Testing strategy

```bash
# Phase A — no backend changes; if a frontend build step is added:
cd ui && npm run build

# Phase B — per template, then the whole set:
python examples/workflows/business/<template>.py --offline
python -m pytest tests/test_examples_workflows_business.py -q   # or wherever tests land
ruff check examples/workflows/business
```

## Documentation requirements

| Change | Update |
|---|---|
| Graph UI component | `docs/frontend/components.md`, `docs/frontend/overview.md` |
| Business template catalog | `examples/workflows/README.md`, `examples/workflows/business/README.md` |
| Either phase's status | `docs/backend/sdk.md` |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Graph layout looks bad on an irregular hand-built `Workflow` | Bounded by existing preset node-count limits (10–20); revisit with a real layout library only if actual usage proves the hand-rolled layout insufficient — don't pre-optimize for graphs that don't exist yet |
| Business templates ship with weak/generic output | The iteration process (§ "why this is long, not code") is not optional — a template skipping steps 2–3 should not ship regardless of schedule pressure |
| Third-party skill content copied in without review | Explicit non-goal; any adoption of external content is its own decision, not bundled into "shipping a template" |
| Graph view and list view diverge in what fields they show | Both read the same `GET /api/workflows/{plan_id}` response; reuse the existing detail markup rather than forking a second implementation of the same fields |

## Success metrics

- Phase A: a fan-out/fan-in workflow (e.g. `02_parallel_market_analysis.py`'s
  output) is visually inspectable as a real graph, verified in a browser;
- Phase B: at least 3 business templates ship with a documented revision
  history (what changed between draft 1 and the shipped version, and why) —
  the absence of a revision history is itself a signal step 2–3 was skipped.

## Implementation checklist

```text
[ ] Phase A  visual workflow graph canvas (layout, zoom/pan, node detail)
[ ] Phase B  4-6 business-vertical templates, each iterated against real output
```

## Changelog

- v0.1 — initial planning draft, written after `agent-workflow-sdk.md`'s
  Phase 0–6 and post-Phase-6 `Agent` capability work (tool calling,
  structured output, capability routing) all landed, and after auditing a
  viral list of third-party Claude Skills for anything worth adopting
  (Context7 landed as a builtin MCP server from that audit; business skill
  packs are noted here as inspiration only, not a content source to import
  wholesale).
