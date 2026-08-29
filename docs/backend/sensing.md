# Business signal sensing

Business sensing is an opt-in, local-first input path for the governed OODA
loop. It captures domain-neutral `Signal` records, interprets them into
`Option` records through the existing DSPy/AIGateway path, and creates a
business Decision Plan only in active mode above the configured urgency gate.

## Safety boundaries

- `sensing.enabled: false` leaves existing code-task paths unchanged.
- RSS is the only v1 connector; polling never executes an action.
- Signals and interpreted options are stored under `.voly/signals/`.
- A Signal's free-form `raw` payload remains local and is not copied into
  TaskEvent or the Cloud Analytics allowlist.
- Interpretation calls models only through `AIGateway.chat()` via DSPyRunner.
- Active interpretation may create a Plan, but execution still requires an
  explicit human approval in the Decision subsystem.

## Lifecycle

```text
RSS → SignalStore → analyst interpretation → Option
                                      │ active + urgency gate
                                      ▼
                              business Decision Plan
```

Commands:

```bash
voly sensing poll
voly sensing list
```

Configuration and connector allowlists are documented in
[`config.md`](config.md). Decision execution is documented in
[`decisions.md`](decisions.md).

## TaskEvent v4 context

When a resulting business Decision reaches a terminal rejection or action
execution outcome, its local TaskEvent includes a bounded `signal` object:

```json
{
  "signal_id": "rss-…",
  "source": "rss",
  "captured_at": "2026-08-29T10:00:00Z",
  "confidence": 0.8
}
```

The connector URL and `raw` payload are deliberately absent. The entire
`signal` object is excluded from remote Cloud Analytics v1.

## Tests

```bash
python -m pytest tests/test_sensing_schema.py tests/test_sensing_interpret.py -q
```
