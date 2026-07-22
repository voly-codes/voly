# Review workflow guarded rollout

`review-until-clean` is opt-in: normal CLI/API/UI runs do not enter the loop.
The operator must explicitly select the workflow, a working directory, a lap
limit, and a deadline. Existing spend policy remains the monetary guardrail.

## Riskiest assumption

The extra independent review and repair laps prevent enough manual rework to
justify their additional latency and model cost. A successful technical run is
not sufficient evidence; the workflow must reach verified completion within
the configured bounds and be useful to the operator.

## Ten-task validation protocol

1. Select ten real, bounded coding tasks that normally require file edits.
2. Record the normal expected acceptance check before starting each task.
3. Run each task with `max_rounds=3`, a 15-minute deadline, and the normal
   project spend limit. Do not increase a bound during a run.
4. After each run, execute the task's acceptance check and record whether the
   reviewer's `clean` verdict agreed with it.
5. Record any manual intervention outside the workflow. A cooperative cancel is
   counted automatically; other interventions belong in the experiment notes.
6. After ten completed records, run:

   ```bash
   voly workflow stats --limit 10
   voly workflow stats --limit 10 --json
   ```

## Provisional continuation thresholds

- At least 8/10 runs stop with `clean` and pass the predeclared acceptance check.
- Zero false-clean results: a `clean` verdict must not hide a failing check.
- All non-clean runs expose a specific stop reason and retain their timeline.
- No run exceeds its lap, deadline, or spend guardrail.
- No more than 2/10 runs require manual intervention.
- Operators judge the visible total cost and duration worthwhile versus the
  manual review/rework avoided. This last criterion requires a short operator
  note; runtime telemetry cannot infer perceived value.

If a false-clean result occurs, pause rollout and strengthen review evidence or
acceptance checks before collecting more runs. If verified completion is below
8/10, inspect stop-reason distribution before changing limits: raising limits
without learning would only buy more cost.

## Persisted metrics

Completed parent `RunRecord` files keep `workflow_metrics` outside the frozen
`TaskEvent` v3 schema: lap count, repair laps, verified completion, cooperative
manual interventions, total cost, duration, unique files touched, and stop
reason. `voly workflow stats` aggregates the newest completed workflow records;
it does not include active runs or ordinary executor records.
