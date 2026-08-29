# Governed business Decisions

A business Decision reuses the existing Plan FSM instead of introducing a
parallel workflow engine. Every option has two steps:

```text
approve-option (human_review) → execute-action (action_succeeded)
```

`execute-action` cannot start until explicit approval moves the first step to
`verified`. Rejection moves it to `failed` and permanently keeps execution
blocked. Approval and execution are separate API/CLI actions.

## Supported actions

- `http_call`: allowlisted host and method, public-address SSRF check, bounded
  timeout/body, redirects disabled and mandatory idempotency key;
- `notify`: one explicitly allowlisted webhook transport.

Both actions use the existing Executor result contract. Successful or failed
execution writes an EvidenceRecord with a redacted `action_report`.

Commands:

```bash
voly decide list
voly decide approve <plan-id>
voly decide reject <plan-id>
voly decide execute <plan-id>
```

The UI exposes the same lifecycle at `#/decisions` and displays the exact
method/target before approval.

## TaskEvent v4

A terminal rejection and every attempted approved execution emit one local
TaskEvent with `task_type: business_decision`. The new `business_plan` object
contains only bounded lifecycle fields:

```json
{
  "plan_id": "option-1",
  "option_id": "option-1",
  "urgency": "high",
  "decision": "approved",
  "decided_at": 1787990000.0,
  "execution": "completed",
  "executed_at": 1787990010.0,
  "action_kind": "notify"
}
```

An approval alone does not emit a terminal TaskEvent. A later execution emits
the complete approved outcome. Rejection emits a completed decision event with
`execution: pending`; it is a valid governed outcome, not an executor failure.
The nested `signal` and `business_plan` objects remain local and are excluded
from Cloud Analytics v1.

## Learning and calibration

When learning is enabled, approval, rejection and successful execution feed
candidate instinct evidence. They never approve or activate an instinct.
`voly eval calibrate --plans-dir .voly/plans` reports observational decision
and execution aggregates without modifying thresholds or Plans.

## Tests

```bash
python -m pytest tests/test_decisions.py tests/test_http_action_executor.py \
  tests/test_notify_executor.py tests/test_judge_calibration.py -q
```
