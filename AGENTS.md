# VOLY — Agent entrypoint

Full agent guide: **[CLAUDE.md](CLAUDE.md)** (architecture, skills, docs mandate, CLI, testing).

OpenWiki quickstart: [openwiki/quickstart.md](openwiki/quickstart.md).

## Must-rules

| Rule | Meaning |
|---|---|
| Gateway first | Model calls go through `AIGateway.chat()` — except file-capable executors |
| Target via `--cwd` | No product-specific paths in `voly/`; work on external repos with `--cwd` |
| E2E only in PulseBoard | Integration / multi-agent runs → `/home/lanies/git/codeops/TEST_VOLY_JOB_MA/`, never this repo |
| Docs with code | Behavior change → update the matching `docs/backend/` or `docs/frontend/` file |
| Local checklist | Never stage/commit/push `docs/problems-checklist.md` |

## Skills

`/voly-plan` · `/voly-backend` · `/voly-frontend` · `/voly-report` — see CLAUDE.md.

<!-- OPENWIKI:START -->

## OpenWiki

This repository has a generated `openwiki/` evidence index. It is optional just-in-time context, not required startup reading.

- Treat source code and tests as authoritative. A brief's unknowns and review items are verification gaps, not automatic requirements.
- Prefer the narrowest quiet validation that proves the changed behavior. Preserve complete failure output.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->
