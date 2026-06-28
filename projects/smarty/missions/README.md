# Smarty combat missions (file-based)

Each mission lives in its own YAML file — **do not edit `cli_commands.py`** for new missions.

## Layout

```
projects/smarty/
  cli_commands.py      # CLI only (~150 lines)
  context.py           # {{SMARTY_PROJECT}}, {{LEGACY_GAP_REF}}, …
  combat/
    registry.py        # load + validate mission names
    runner.py          # execute sequential/parallel steps
  missions/
    smarty-foo.yaml    # one file per mission
  tasks/
    design-review.yaml # analytical multi-agent tasks
```

## Quick start

```bash
cd codeops && source .env

# List all missions (inline + files)
python3 -m codeops.cli smarty combat list

# Run by name
python3 -m codeops.cli smarty combat run smarty-group-settings --sequential

# Scaffold a new mission file
python3 -m codeops.cli smarty combat init smarty-my-feature

# Preview steps + source file
python3 -m codeops.cli smarty combat show smarty-bills-crud
```

## File format (`*.yaml`)

Filename = default mission id (or set explicit `name:` field).

```yaml
name: smarty-my-feature

description: >
  One-line summary for `combat list`.

# supervised: true   # optional — Zen catalog routing

tasks:
  - agent: cursor
    label: "cursor: implement feature"
    task: |
      STEP 1/2 — Instructions for the agent.

      {{LEGACY_GAP_REF}}
      Project root: {{SMARTY_PROJECT}}

  - agent: cursor
    label: "cursor: review"
    task: |
      STEP 2/2 — Review + npm run build.
```

### Template variables

Use `{{VAR_NAME}}` in `description` and task bodies. Available names are in `_constants.py` (`mission_context()`).

Common: `SMARTY_PROJECT`, `LEGACY_GAP_REF`, `LEGACY_FRONTEND`, `LEGACY_FRONTEND_ROUTES`.

TypeScript types like `{ collectionName? }` stay as single braces — only `{{UPPER_SNAKE}}` is expanded.

## Merge rules

All missions are file-based (`missions/*.yaml`). `cli_commands.py` is CLI-only (~180 lines).

## Python missions (optional)

For dynamic task generation, add `missions/my-mission.py`:

```python
from projects.smarty.missions._constants import LEGACY_GAP_REF

MISSION_NAME = "my-mission"
MISSION = {
    "description": "…",
    "tasks": [{"agent": "cursor", "label": "…", "task": f"… {LEGACY_GAP_REF}"}],
}
```

YAML is preferred for most missions.
