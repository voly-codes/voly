# Bounded agent workflows

VOLY workflows are narrow product scenarios composed from existing execution
primitives. They are not a general-purpose workflow engine.

## Review until clean

`voly.workflow.review_until_clean.ReviewUntilClean` runs a bounded repair loop:

```text
AgentRunner (developer / file-capable executor)
  -> AIGateway.chat() (independent reviewer)
       -> clean: stop successfully
       -> blocking findings: reactivate the developer
```

The controller records one `ReviewLap` per developer/reviewer pair. Each lap
contains the executor and reviewer route, files touched, raw outputs, structured
verdict, blocking findings, duration, and visible cost. The final
`ReviewLoopResult` always carries an explicit `ReviewStopReason`.

### Guardrails

- `max_rounds` is required to be between 1 and 20 (default 3).
- `deadline_seconds` bounds whether another transition may start (default 900s).
- Each executor attempt receives only the remaining deadline, capped by
  `executor_timeout`.
- Existing AgentRunner safety, billing fallback, and cost policy apply.
- Reviewer calls use `AIGateway.chat()` and therefore inherit DLP, cache, rate,
  spend, provider fallback, and telemetry controls.
- Reviewer output is fail-closed strict JSON. Invalid or contradictory verdicts
  stop with `review_failed`; a blocking verdict must include actionable findings.
- Sub-runs set `emit_event=False`; a future public entrypoint owns the parent
  workflow event instead of emitting misleading duplicate task events.

### Stop reasons

| Reason | Meaning |
|---|---|
| `clean` | Independent reviewer found no blocking issue. |
| `max_rounds` | The configured lap limit was reached with blocking findings. |
| `deadline` | There was not enough workflow time to begin the next transition. |
| `executor_failed` | The developer executor failed before review. |
| `review_failed` | The reviewer call failed or returned an invalid verdict. |
| `spend_limit` | AgentRunner or AIGateway rejected further spend. |

## Architecture boundary

This module must remain a concrete orchestration use case. Reusable graph
operators, arbitrary user-authored topology, persistent subscriptions,
checkpoint/resume, schedules, and webhooks are deliberately out of scope until
real workflow telemetry justifies a separate engine.
