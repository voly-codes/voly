# Code reuse pipeline — Backend Reference

Deterministic Layer B cycle: **task → GitHub search → shallow clone → structure pack → module pick → copy with license gate**.

Package: `voly/reuse/`. CLI: `voly reuse`. Model calls go through `AIGateway.chat()` only.

---

## Flow

```text
task text
  → QueryPlanner (optional AIGateway) or keyword query
  → GitHub Search API (search/repositories)
  → filter stars + license allow/deny
  → shallow clone → .voly/reuse/cache/<owner>__<repo>@<sha>/
  → pack: file tree + ProjectScanner + keyword-relevant files
  → ModulePicker (AIGateway → JSON modules) or heuristic fallback
  → apply into --cwd under apply_dest (default dry-run)
  → ReuseReport JSON under .voly/reuse/reports/
```

---

## CLI

```bash
# Search (+ clone/pack by default)
voly reuse search "JWT auth middleware for FastAPI" --limit 5 --lang python

# Clone + pack one repo
voly reuse pack owner/repo --task "JWT auth"

# Pick modules from latest / given report (AIGateway or heuristic)
voly reuse pick [.voly/reuse/reports/latest.json]

# Apply picks (dry-run default; --write to copy)
voly reuse apply report.json --cwd /path/to/project [--write]

# Full MVP pipeline (apply dry-run unless --write)
voly reuse run "add rate limiter" --cwd /path/to/project --lang python
```

Env: `GITHUB_TOKEN` or `GH_TOKEN` (recommended for search rate limits).

---

## Config (`voly.yaml`)

```yaml
reuse:
  enabled: true
  cache_dir: ".voly/reuse/cache"
  reports_dir: ".voly/reuse/reports"
  max_repos: 5
  min_stars: 20
  allowed_licenses: [mit, apache-2.0, bsd-2-clause, bsd-3-clause, isc, 0bsd, unlicense]
  deny_licenses: [gpl-2.0, gpl-3.0, agpl-3.0]
  pack_max_chars: 80000
  apply_dest: "vendor/reuse"
  auto: false                  # auto-run search+pick before each executor call
  auto_max_age_seconds: 604800 # skip if fresh report exists (7 days)
  auto_max_repos: 3            # smaller limit to keep latency low
```

| Field | Meaning |
|---|---|
| `enabled` | Master switch; also gates optional context inject |
| `cache_dir` | Shallow clone cache (relative paths resolve from process cwd / project) |
| `reports_dir` | JSON reports + `latest.json` |
| `max_repos` | Cap for search results |
| `min_stars` | Appended as `stars:>=N` to the GitHub query |
| `allowed_licenses` / `deny_licenses` | SPDX keys (lowercase); deny wins; unknown → not allowed for apply |
| `pack_max_chars` | Budget for packed tree + snippets |
| `apply_dest` | Destination under `--cwd` |
| `auto` | Auto-run GitHub search+pick before each run (adds ~10–30s, opt-in) |
| `auto_max_age_seconds` | Skip auto-search if existing report is younger than this |
| `auto_max_repos` | Repo limit in auto mode (smaller than `max_repos` to stay fast) |

---

## License policy

- **Allow (default):** MIT, Apache-2.0, BSD-2/3-Clause, ISC, 0BSD, Unlicense.
- **Deny (default):** GPL-2.0, GPL-3.0, AGPL-3.0 (and LGPL variants in deny set).
- Apply **blocks** denied/unknown licenses; dry-run still records `status=blocked`.
- On `--write`, copies `LICENSE*` + writes `NOTICE` under `vendor/reuse/<owner>__<repo>/`.

---

## Modules

| File | Role |
|---|---|
| `github_search.py` | REST search + token from env |
| `clone.py` | `git clone --depth 1` into cache |
| `pack.py` | Tree + `ProjectScanner` + keyword files |
| `license.py` | SPDX normalize / allow / LICENSE heuristics |
| `picker.py` | `AIGateway.chat()` → modules JSON |
| `apply.py` | Copy with path escape + protected-path checks |
| `report.py` | `ReuseReport` save/load |
| `pipeline.py` | `run_reuse` / `search_and_pack` / `pack_one` |
| `context.py` | Short report snippet for local context inject |

---

## Pipeline integration

### Passive inject (always on when `enabled: true`)

If `.voly/reuse/reports/latest.json` exists under the target cwd and is recent,
`_gather_local_context` prepends a short **Code reuse report** block before
executor/pipeline local files.

### Auto-search (`auto: true`, opt-in)

When `reuse.auto: true`, the pipeline runs `auto_reuse()` before each executor call:

1. Checks if a report younger than `auto_max_age_seconds` exists **and has at least
   one license-allowed candidate** — skips only then. Empty / all-denied reports
   do not block a re-search (avoids a 7-day poison cache after a bad query).
2. Calls `search_and_pack` (up to `auto_max_repos` repos) + `pick_modules`.
3. Saves the report to `.voly/reuse/reports/` — immediately picked up by the passive inject.
4. Never raises: network errors, rate limits, missing GitHub token → silent skip.

**Query planner:** with AIGateway available, `plan_search_query` refines the task into
an English GitHub query. Deterministic fallback (`task_to_query`) extracts Latin
keywords, normalizes `three.js`→`threejs`, maps common Cyrillic tech stems
(танк→tank, браузер→browser, …), and uses a short `in:name,description` AND.
If the API returns zero hits, `search_repositories` retries without `in:` and
then with the first two keywords only.

Enable per-project in `voly.yaml`:
```yaml
reuse:
  auto: true
  auto_max_repos: 3
```

Skill playbook: `.voly/skills/code-reuse.yaml` — directs agents to the CLI;
skills remain prompt-text, not executable workflows.

---

## Safety

- `apply` defaults to **dry-run**; `--write` required for filesystem copy.
- Path escape (`..`) blocked; executor `DEFAULT_PROTECTED_PATHS` respected.
- No automatic PR creation; no GPL “copy with warning” in the default path.

---

## E2E

Manual / integration runs only under `/home/lanies/git/codeops/TEST_VOLY_JOB_MA/`
(never against this repository as the target `--cwd` for write tests).

```bash
export GITHUB_TOKEN=...
voly reuse run "small Python retry helper" \
  --cwd /home/lanies/git/codeops/TEST_VOLY_JOB_MA --lang python
# review report, then optionally --write
```
