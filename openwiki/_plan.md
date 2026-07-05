# OpenWiki plan

## Intended pages
- /openwiki/quickstart.md — entrypoint with repo overview, major domains, and links to the rest of the wiki.
- /openwiki/config-and-operations.md — configuration, generated artifacts, testing guidance, operational cautions.

## Evidence
- README.md — product overview, CLI/UI/API surface, project-agnostic positioning.
- CLAUDE.md — workflow rules, config expectations, important source map references.
- voly.yaml, codeops.yaml, .env.example, pyproject.toml — runtime config and test conventions.
- voly/cli/main.py, voly/web/server.py, voly/pipeline/core.py, voly/runner/agent_runner.py, voly/ai_gateway/gateway.py — major entrypoints and execution paths.

## Remaining questions
- Whether the existing docs/ tree should also be documented in OpenWiki or referenced only from quickstart.
- Whether there are any recent code changes beyond the openwiki docs and instruction files that affect commit scope.