# Contributing to VOLY

Thank you for your interest in VOLY! The project core is open under [Apache 2.0](LICENSE),
and contributions are welcome.

## How to contribute

1. Fork the repository and create a branch from `main`.
2. Make your changes. Project rules are in [CLAUDE.md](CLAUDE.md):
   - **Docs move with code** — a change in code behavior is accompanied by
     updating the corresponding file under `docs/` in the same commit.
   - **Gateway first** — model calls go through `AIGateway.chat()`
     (except executors).
   - **Project-agnostic core** — no product logic or hardcoded
     paths in `voly/`.
3. Run tests and gates:
   ```bash
   python3 -m pytest tests/ -q
   python3 scripts/check_doc_links.py
   python3 scripts/check_env_doc_sync.py
   ```
   New tests should be mock-based, with no calls to real APIs.
4. Open a pull request describing the motivation for the change.

## Developer Certificate of Origin (DCO)

The project uses [DCO](https://developercertificate.org/). Sign off
every commit:

```bash
git commit -s -m "..."
```

The line `Signed-off-by: Name <email>` confirms that you have the right
to contribute this code to the project under its license.

## Open-core boundaries

VOLY is developed under an open-core model. So expectations are fair on both
sides, the boundary is public:

**Open core (this repository):** orchestration, executor chain, billing
fallback chain, multi-agent decomposition, AI Gateway (cache, limits,
fallback), telemetry, CLI, **single-user web UI**, and **local** auth
(`auth.provider=local` JWT or auth disabled for localhost). PRs that improve the
core are always welcome.

**Commercial shell (outside this repository / future Team package):** team hosted
control plane — organizational spend dashboards, org-level spend limits, **SSO
(e.g. Clerk and other IdPs)**, audit log, managed-hosting federation, multi-seat
roles. PRs that implement such features as **required** core paths will most
likely be politely declined — not because the contribution is bad, but so the
boundary stays predictable.

**Auth note:** self-host locking with local JWT is core. Hosted SSO integrations
may exist in-tree as optional `provider=clerk` for migration only; they are
**not** the open-core default and are candidates for a separate Team package
(`voly-team`). Prefer local JWT for public examples and tests.

Borderline cases should be discussed in an issue before writing code — that saves
time for you and for maintainers. Protocols through which the core talks to any
external services (`TaskEvent` telemetry, spend protocol, A2A) are open
and versioned — self-hosted alternatives are welcome.

## Naming

"VOLY" is the project name. Forking the code is allowed by the license; distributing
forks under the same name is not.
