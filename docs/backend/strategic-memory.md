# Strategic memory compaction

Strategic memory is an opt-in layer above the existing SQLite/remote transcript
store. Raw history remains available for audit, but when
`memory.strategic_compaction` is enabled the pipeline injects only compact,
typed records. It never silently deletes source history.

## Handoff contract

`SessionHandoff` schema version 1 identifies a session, project, optional
organization, and typed items. Each item declares:

- kind: `decision`, `verified_fact`, `failed_attempt`, `open_question`, or
  `next_action`;
- class: `episodic`, `semantic`, `procedural`, or `preference`;
- scope: `project`, `organization`, or `global`, with a scope identifier;
- title, compact content, provenance, optional expiry, and `private`.

Example:

```json
{
  "schema_version": 1,
  "session_id": "run-123",
  "project_id": "project-a",
  "organization_id": "voly",
  "items": [{
    "kind": "decision",
    "memory_class": "semantic",
    "scope": "project",
    "title": "Runtime",
    "content": "Use Python 3.13",
    "provenance": ["commit:985e908"],
    "private": false
  }]
}
```

Import it with `voly memory compact handoff.json --cwd .`. Preview retrieval
with `voly memory context "<query>" --cwd .`. `voly memory export` emits only
non-private, non-expired records, so private observations cannot enter
exportable capability packs.

## Retrieval and isolation

Project records require an exact project ID match. Organization records require
an exact organization ID; global records are visible everywhere. If callers do
not provide `project_id`, VOLY derives a stable identifier from the resolved
project path.

Retrieval applies a total approximate-token budget and a limit per memory
class. Expired records are ignored. Exact duplicates are skipped. A new record
with the same kind, scope, scope ID, and title but different content is retained
and linked bidirectionally through `contradicts`; VOLY does not guess which
claim is true.

```yaml
memory:
  strategic_compaction: false
  strategic_path: ".voly/strategic-memory.jsonl"
  retrieval_token_budget: 600
  retrieval_per_class_limit: 3
```

The JSONL file is local runtime state and ignored by Git.
