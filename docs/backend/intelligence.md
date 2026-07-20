# Repository Intelligence

> Added: Phase 1. Source: voly/intelligence/

## Purpose

Pre-run analysis of external repositories before agent planning. Provides
license gate, architecture map, reuse candidates, and security risk summary.

## CLI

```bash
voly repo inspect <url>    # pre-clone admission only
voly repo analyze <url>    # full analysis (Phase 2)
voly repo map <url>        # architecture map only (Phase 2)
voly repo license <url>    # license analysis only (Phase 2)
```

## Modules

| Module | Role |
|---|---|
| `schema.py` | `RepositoryIntelligence` and sub-dataclasses |
| `admission.py` | Pre-clone GitHub API checks |
| `license_analyzer.py` | SPDX risk matrix and policy gate |

## AdmissionResult fields

| Field | Type | Description |
|---|---|---|
| `allowed` | `bool` | Whether the repo passes pre-clone admission |
| `private` | `bool` | GitHub visibility (API-enriched repos only) |
| `archived` | `bool` | Whether the repository is archived |
| `size_mb` | `float` | Approximate size in megabytes (GitHub `size` KB → MB) |
| `last_commit_days_ago` | `int \| None` | Days since last push (`pushed_at`) |
| `stars` | `int` | Stargazer count |
| `license_file_present` | `bool` | GitHub API reports a `license.name` |
| `api_enriched` | `bool` | Whether GitHub API data was fetched |
| `reason` | `str \| None` | Set when `allowed=False` |

## LicenseInfo fields

| Field | Type | Description |
|---|---|---|
| `spdx` | `str \| None` | Normalized SPDX identifier |
| `commercial_use` | `bool` | Commercial use permitted |
| `modification` | `bool` | Modification permitted |
| `distribution` | `bool` | Distribution permitted |
| `notice_required` | `bool` | Attribution/notice required |
| `copyleft` | `bool` | Copyleft obligations apply |
| `risk` | `str` | `low`, `medium`, `high`, or `unknown` |

## Storage

Reports cached under `.voly/intelligence/reports/<owner>__<repo>@<sha>.json`

Clone cache under `.voly/intelligence/cache/` (separate from `voly/reuse/cache/`)
