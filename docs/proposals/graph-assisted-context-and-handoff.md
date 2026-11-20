# Backlog ideas: project knowledge graph for context compression, and agent handoff on stop

Status: idea — not scoped, not prioritized. Captured from a 2026-11-09 discussion
comparing Voly's token/cost-control positioning against graphify.com's
knowledge-graph approach. Neither item below is a commitment; both need a real
problem-sizing pass before becoming a proposal.

## 1. Project knowledge graph as a context-compression source

**Goal:** reduce the tokens an agent burns re-reading a codebase to answer
"where is X" / "what calls Y" / "how does this connect to that", by having it
pull a pre-built structural+semantic graph instead of grepping and re-reading
files from scratch on every task.

**Why this fits Voly and not a bolt-on competitor:** graphify.com's product is
the graph itself (AST + LLM semantic extraction + community detection,
consumed interactively). That is not Voly's business. The only version of
this worth doing is one where the graph is purely an internal cache that
feeds `RTK` / context-compression (`headroom/`) and `voly reuse`, so it shows
up as *lower token spend per task* in FinOps telemetry — not as a second
product with its own UI.

**Possible shape (not decided):** the graph is assembled once (plausibly in
Voly Cloud, since extraction is the expensive part and the result is small),
then an executor reads the parts it needs locally before acting. Delivery
mechanism (file export, API, cache sync, etc.) is explicitly open — not
scoping it to any particular transport here.

**Main risk:** a graph is a cache, and caches go stale. We saw this exact
failure mode first-hand: `voly_web/CHECKLIST.md` listed 9 "open" bugs after a
2026-07-10 review; 8 were already fixed in code by 2026-11-09 and nobody had
re-run the review. A project graph built once and not continuously
re-extracted on change will drift from the real codebase the same way, and a
stale graph steering an agent's actions is worse than no graph (confidently
wrong beats admittedly unknown). Re-extraction/freshness has to be solved
*before* this is worth building, not after.

**Open questions:**
- Is the token saving (graph lookup vs. re-reading files) actually larger
  than the cost of keeping the graph fresh, on a real Voly-sized codebase?
- Does this duplicate something `voly reuse` or strategic-memory
  (`docs/backend/strategic-memory.md`) already half-solves?
- Who/what re-triggers extraction on change, and how is staleness surfaced
  to an agent using the graph (same question as item 2 below, just for a
  cache instead of a running task)?

## 2. Surfacing where a stopped agent left off, for handoff

**Problem:** when an agent run stops — crash, timeout, context limit, human
interrupt, anything — there is currently no standard, inspectable answer to
"what had it actually finished, and what was it about to do next" that a
different agent (or a human) could use to pick the work back up without
re-deriving it from scratch or re-doing finished work. The run's own
in-context state is gone; what's left is whatever got written to disk, which
may or may not reflect the true in-progress state at the moment it stopped.

**Existing foundation this could sit on:** `WorkReport` already records
files touched, `TaskEvent` records cost/timeline, `EvidenceRecord` joins
execution identity to evaluation state, and the Plan FSM
(`docs/backend/plan.md`, `docs/proposals/plan-gate-verification.md`) already
models step status with enforced transitions. None of these currently answer
"show me the handoff state of a run that stopped mid-step" as a single,
reliable artifact — they record outcomes and evidence, not an in-flight
checkpoint meant for a different executor to resume from.

**Shape of a solution (not decided):** something like a standing
`handoff_state` written/updated at defined checkpoints (not just at the end),
naming the current plan step, what in that step is verified-done vs.
attempted-but-unconfirmed, and what the next action was going to be — so a
second agent (or `voly decide` style human review) can resume instead of
re-planning blind or redoing already-finished work.

**Open questions:**
- Checkpoint granularity: per plan step (coarse, cheap) vs. per tool call
  (fine, more overhead) — where plan-gate verification already draws step
  boundaries might be the natural unit.
- Is "stopped" always detectable, or only for the controlled-stop cases
  (timeout, budget_exceeded)? A hard crash may never get to write a final
  handoff state — does the last verified step stand in for it?
- Does this become part of `WorkReport`/`EvidenceRecord`, or a new record
  type — and does it need its own Spend Protocol-style versioning given
  `TaskEvent` already went through a schema bump for task tags (see
  `docs/proposals/task-tags-and-trusted-outcomes.md`)?
