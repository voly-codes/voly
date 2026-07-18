# Post-run checklist — multi-agent / pipeline

Use after every metric run on `TEST_VOLY_JOB_MA/` (or any `--cwd`).
Pipeline logs each setup step as `[PIPELINE:SETUP] …` — grep the CLI output first.

```bash
# From voly repo — SETUP/A2A lines print on every `voly run` (INFO)
.venv/bin/voly status
.venv/bin/voly -v run "…" --cwd …   # optional DEBUG
rg '\[PIPELINE:SETUP\]|\[PIPELINE:A2A\]|\[CHAIN:|multiagent\[' /path/to/run.log
```

Known greenfield pitfall: safety used to treat `.env.example` as protected
(`.env.*`). Templates are now allowlisted; real `.env` / `.env.local` stay blocked.

---

## 1. Cloudflare services

| Check | How | Pass |
|---|---|---|
| Account + gateway env | `[PIPELINE:SETUP] cf_env CLOUDFLARE_ACCOUNT_ID=set` and `CLOUDFLARE_AI_GATEWAY_ID=set` | both `set` |
| AI Gateway route | Role using `cloudflare-dynamic` / Workers AI succeeds or fails over within `request_total_timeout_seconds` (60s) | no 120s hang |
| A2A worker URL | `CF_WORKER_A2A_URL` set; `voly a2a status` (or federation health) if using remote mode | OK / local-only intentional |
| Spend worker URL | `CF_WORKER_SPEND_URL` set; `voly spend status` | OK or intentionally local |
| AGUI / Memory workers | `CF_WORKER_AGUI_URL`, `CF_WORKER_MEMORY_URL` | set if those features used |
| Secrets | `CF_AIG_TOKEN` / `CLOUDFLARE_API_TOKEN` present for CF paths | set |

---

## 2. A2A / multi-agent

| Check | How | Pass |
|---|---|---|
| Setup log | `[PIPELINE:SETUP] a2a ok` | present |
| Roles | Event `a2a_agents_used` matches expected (e.g. 5 for architecture+deploy+tests) | expected list |
| Decomposition | Complex greenfield → architect + developer + tester + reviewer + devops | 5 roles when flags warrant |
| Hybrid cwd | Developer `mode=executor` with `files_touched` non-empty on code-gen | yes |
| Plan gates | `plan_status` / `plan_verify_ok` on tester; shadow may force-verify | logged, not silent |
| Fail-over | Dead Anthropic / stall → next provider within ~15s | no 120s stall |

Event file: `.voly/events/<task_id>.json` (under voly cwd or target project).

---

## 3. Headroom

| Check | How | Pass |
|---|---|---|
| Enabled | `voly.yaml` `headroom.enabled: true` | yes |
| Setup | `[PIPELINE:SETUP] headroom ok running=True` | yes |
| Compress | Multi-agent log / debug: headroom compress called for chat roles | optional savings |
| Tokens saved | `voly status` → `[Headroom] Tokens saved` or event `tokens.saved_headroom` | ≥ 0; growth on repeat preferred |

---

## 4. RTK

| Check | How | Pass |
|---|---|---|
| Enabled | `rtk.enabled: true` | yes |
| Setup | `[PIPELINE:SETUP] rtk ok installed=True` | yes |
| Hooks | Claude executor runs with RTK hooks when using claude-code | if that executor used |
| Savings | Event `tokens.saved_rtk` or `voly status` RTK stats | ≥ 0 |

---

## 5. Spend

| Check | How | Pass |
|---|---|---|
| Config | `[PIPELINE:SETUP] spend enabled=True url=…` | expected |
| Live health | `voly spend status` | healthy / known skip |
| Budget | Run did not trip `spend_limited` unless intentional | check event / logs |
| Cost telemetry | Event `cost_usd` + per-role `a2a_assignments[].cost_usd` | present, sums sensible |

---

## 6. Target project (`--cwd`)

| Check | How | Pass |
|---|---|---|
| Files changed | `git status` / list new files under `--cwd` | non-empty for code-gen |
| Tests | Prefer `.venv/bin/pytest -q` in project | green or known fail |
| `.voly/` ignored | `.gitignore` contains `.voly/` after first hybrid run | yes |
| No pollution | Parallel runs do not share unrelated `files_touched` | if parallel used |

---

## 7. Timing / complexity smell test

| Signal | Suspect |
|---|---|
| Wall clock >> sum of role `duration_ms` | Hidden waits (plan verify, setup, serial waves) |
| Tester/reviewer >> 60s with empty `files_touched` | Chat provider stall or oversized prior context |
| `plan_verify_ok=false` every run | Wrong `tester_command` or `command_timeout` too low |
| Always 2 roles on “architecture + deploy” task | Decomposer flags / keyword miss — check `analyze_task` |
| Cache always false on continuation | Prompts unique; expect time savings from smaller developer delta, not gateway cache |

---

## Quick copy-paste after a run

```bash
# Latest event summary
python3 - <<'PY'
import json, glob, os
p = max(glob.glob("/home/lanies/git/codeops/voly/.voly/events/*.json"), key=os.path.getmtime)
d = json.load(open(p))
print(os.path.basename(p), d.get("status"), round(d.get("duration_ms",0)/1000,1), "s", f"${d.get('cost_usd',0):.4f}")
print("agents:", d.get("a2a_agents_used"))
print("gateway:", d.get("gateway"))
print("tokens:", d.get("tokens"), "saved_rtk/headroom:",
      d.get("tokens",{}).get("saved_rtk"), d.get("tokens",{}).get("saved_headroom"))
for a in d.get("a2a_assignments") or []:
    print(f"  {a.get('role')}: {a.get('provider')}/{a.get('model')} "
          f"{round((a.get('duration_ms') or 0)/1000,1)}s ok={a.get('ok')} "
          f"verify={a.get('plan_verify_ok')} files={len(a.get('files_touched') or [])}")
PY

.venv/bin/voly status
.venv/bin/voly spend status 2>/dev/null || true
```
