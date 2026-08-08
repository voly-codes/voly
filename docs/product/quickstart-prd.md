*Built with Next Move Theory — [nextmovetheory.com](https://nextmovetheory.com/?utm_source=nmt-product-requirements&utm_medium=skill-artifact)*

<a id="disclaimers"></a>
> **Numerical disclaimer.** All numerical targets in this document are hypotheses with a verification path. Validate them before making a major decision.
> **Hallucination disclaimer.** This document was generated with LLM assistance and may contain mistakes. It is a build hypothesis, not customer evidence.
> ⚠️ This PRD uses the manually described VOLY segment and value direction. No external customer interviews have yet confirmed that installation is the binding constraint.

## How to read this

- **Level 1 — What we're building:** the one-page decision. [jump ▸](#layer-1)
- **Level 2 — The reasoning:** why this path won. [jump ▸](#layer-2)
- **Level 3 — The full work:** requirements, failures, metrics, and risks. [jump ▸](#layer-3)

<a id="layer-1"></a>
# VOLY Quickstart — what we're building

2026-08-09 · developers who already use at least one file-capable coding agent · early product validation

> ⚠️ These are hypotheses, not facts — [full disclaimer ▸](#disclaimers)

> **Validation debt:** this PRD rests on **6** unvalidated assumptions, **2** of which can sink the build. Validate those assumptions before expanding packaging beyond the first slice. [see them ▸](#l2-risk)

## What we're building

One guided command that checks the machine, selects a repository and an available agent, creates the minimum safe configuration, and gets the user ready for a verified VOLY task. [why this approach won ▸](#l2-build)

## Who it's for

Developers who already run Claude Code, Cursor, OpenCode, or another supported CLI agent and want orchestration, budget control, fallback, and evidence without learning VOLY's internal configuration first. [who and why ▸](#l2-users)

## The one moment that proves it works

The user sees a preflight summary saying that their repository and at least one executor are ready, together with the exact safe command for their first task, without editing YAML or `.env`. [where this moment lives ▸](#l2-capabilities)

## The single riskiest thing to validate BEFORE building more

Installation and configuration must actually be the reason qualified users abandon VOLY. Test this by observing five first-time users and recording where each one stops. [full risk picture ▸](#l2-risk)

## What to build first

Implement `voly quickstart --check` as a deterministic, non-destructive preflight. It must work without provider credentials and must never launch a paid agent unless the user explicitly requests it. [full requirements ▸](#l3-requirements)

---

<a id="layer-2"></a>
# Why we're building it this way — the reasoning

<a id="l2-input-risks"></a>
## What we know — and what remains a hypothesis

| Input | Treatment | Risk | Cheapest check |
|---|---|---|---|
| Previous VOLY multi-agent runs failed during executor/SDK setup | Observation | Failures may reflect a development machine, not normal users | Five clean-machine sessions |
| The CLI currently exposes many setup commands and configuration fields | Repository data | Complexity may not be the main adoption barrier | Observe where first-time users stop |
| Prime Intellect uses a short CLI install/login/run path | Documented comparison | Its hosted product and users differ from VOLY | Test the pattern, not the brand analogy |
| A five-minute first result would feel substantially easier | Hunch | The threshold may be wrong | Measure actual first-run time and satisfaction |

**The scope relies primarily on the unvalidated belief that setup friction blocks otherwise-qualified users. Risk R1 below must be tested before native installers are built.**

<a id="l2-build"></a>
## Is building this the right move?

The business goal is not to ship installers. It is to let a qualified developer experience VOLY's control and evidence before setup cost exhausts their attention. A native application, Docker image, and hosted-only runner all introduce more assumptions. A guided command reuses the current open core and removes configuration work with the smallest reversible change.

The decision is **GO (to validation)**: build the deterministic preflight as a probe, observe users, and expand packaging only if the probe confirms the barrier. [challenge details ▸](#l3-challenge)

<a id="l2-users"></a>
## Who it serves, and what success means

The initial segment already has a supported coding agent and a local repository. They want to delegate a real coding task while retaining cost limits and independently checkable results. VOLY should remove the orientation work of discovering executors, configuration, and the next command. [overview ▸](#l3-overview)

<a id="l2-capabilities"></a>
## What it must do

- Detect supported executors without installing or authenticating them.
- Validate the selected repository and explain any blocking condition.
- Create configuration only after explicit confirmation.
- Produce one exact next command, safe by default.
- Clearly distinguish ready, optional, and blocking checks.

[functional requirements ▸](#l3-requirements)

<a id="l2-failures"></a>
## Failures that matter

The path fails if it modifies a repository during diagnosis, asks for secrets too early, claims an executor is usable when it is not, overwrites an existing configuration, or presents a wall of optional integrations before the first task. [edge cases ▸](#l3-edge)

<a id="l2-risk"></a>
## The riskiest assumption and cheapest probe

The fatal assumption is that qualified users want VOLY but are blocked by installation and setup. Give five developers the current landing page and a clean machine, say only “run one safe task on this repository,” and observe without helping. Compare the current path with `uvx voly quickstart --check`. [risk table ▸](#l3-risk)

---

<a id="layer-3"></a>
# The full build spec

<a id="l3-challenge"></a>
## 0. Build decision

| Way considered | What it removes or adds | Cost vs. first slice | Riskiest assumption | Won? |
|---|---|---:|---|---|
| Guided CLI preflight | Removes manual discovery and configuration | Baseline | Setup is the binding constraint | ✅ |
| Docker-first | Adds mounts, credentials, host executors, and filesystem boundaries | Higher | Containerization is easier for local agent work | — |
| Native Windows/macOS/Linux packages | Removes Python/uv but adds signing and release matrices | Much higher | Runtime installation is the main barrier | — |
| Hosted-only runner | Removes local setup but changes trust, privacy, and economics | Highest | Users will upload or remotely expose repositories | — |

The business-goal ladder is: package VOLY → reduce setup abandonment → reach the first verified run → prove repeated task delegation → support a sustainable hosted business. The first slice removes orientation and configuration work without changing the operating model.

> <sub>**▸ methodology trace.** Challenge the business goal; subtract Jobs before adding features; use an MVP as a probe; prefer the option that drops the most unvalidated assumptions.</sub>

<a id="l3-overview"></a>
## 1. Overview

**Core Job:** When I have a repository and at least one coding agent, I want to make VOLY ready for a safe task without manually assembling its configuration, so I can delegate work while retaining control and evidence.

**Success criteria:** no YAML or `.env` editing before readiness; no paid execution during preflight; actionable result in under five minutes; every blocker has one next action.

**Bigger result:** delegate recurring development work without losing control of cost or correctness.

**First value moment:** VOLY correctly identifies the repository and executor state and prints a safe, copyable first-run command.

## 2. Target users

In scope: developers with a local Git repository and at least one supported file-capable executor installed or intentionally not yet installed. Their dominant criterion is a low-effort, reversible start.

Out of scope: non-technical users, teams requiring hosted multi-tenant administration, and users expecting VOLY to install or purchase third-party agents automatically.

<a id="l3-requirements"></a>
## 3. Functional requirements

### Critical path

1. Start quickstart.
2. Resolve and validate repository path.
3. Detect supported executor binaries.
4. Inspect existing VOLY configuration without changing it.
5. Classify checks as ready, optional, or blocking.
6. Print the minimum next action and safe first-run command.
7. Only with explicit confirmation, create missing configuration.

Break sites: invalid path; non-Git directory; no executor; executor binary present but unusable; malformed existing config; non-interactive terminal; permission error.

### R1 — Deterministic preflight

User can run `voly quickstart --check [--cwd PATH]` and receive a stable readiness summary without filesystem writes.

Acceptance criteria:

- exits `0` when the repository is ready for a first task;
- exits non-zero when a blocking condition exists;
- performs no network requests, subprocess authentication, package installation, or file writes;
- reports the repository, config state, detected executors, and next command;
- supports machine-readable `--json` output.

### R2 — Safe configuration creation

User can run `voly quickstart --cwd PATH` and approve creation of `voly.yaml` when it is missing.

Acceptance criteria:

- never overwrites an existing file;
- never writes secrets;
- non-interactive mode requires an explicit `--yes` flag;
- configuration creation is skipped if any repository safety check fails.

### R3 — Executor guidance

User receives a ranked list of locally detected supported executors and one recommended executor for the first run.

Acceptance criteria:

- detection uses local binary availability only;
- an unavailable executor includes one concise installation or authentication hint;
- no executor is installed or launched by quickstart;
- recommendation is deterministic and identifies why it was chosen.

### R4 — First-run handoff

User receives an exact copyable command using the resolved repository and recommended executor.

Acceptance criteria:

- defaults to dry-run or an equivalent reversible mode;
- never invents a task supplied by the user;
- when no task is supplied, prints a placeholder and explains that no agent was run;
- paths with spaces are safely quoted for the active platform.

> <sub>**▸ methodology trace.** R1–R4 perform the Core Job “make VOLY ready without manual configuration” for the Big Job “delegate development work with cost and correctness control.” Mechanics: take the setup Job off the user, kill manual discovery, and repair the pre-activation chain break. The first value moment occurs after R1/R4, before any paid run.</sub>

<a id="l3-edge"></a>
## 4. Edge cases

| # | Context | Path location | What breaks | Severity | Required handling |
|---:|---|---|---|---|---|
| 1 | Path does not exist | Repository resolution | User cannot tell what path VOLY used | Critical | Fail with resolved path and correction example |
| 2 | Existing malformed `voly.yaml` | Config inspection | Quickstart overwrites or hides a real problem | Critical | Fail closed; never write |
| 3 | No supported executor found | Executor detection | User reaches a dead end | High | List supported executors and one next action |
| 4 | Executor exists but auth is unknown | Executor detection | False “ready” claim | High | Label as detected, not authenticated |
| 5 | Non-interactive shell | Confirmation | Command blocks forever | High | Require `--yes` for writes; check mode never prompts |
| 6 | Repository has uncommitted files | Safety | User fears losing work | High | Warn; first command remains dry-run |
| 7 | Existing config in parent directory | Config inspection | Wrong project configuration is used | Medium | Show the exact selected config path |
| 8 | Directory is not Git-controlled | Repository validation | Safety guarantees differ | Medium | Warn and require explicit continuation later |
| 9 | Unicode or spaces in path | Handoff | Generated command cannot be copied | Medium | Platform-safe quoting and tests |
| 10 | Capability registry is offline | Optional services | Optional cloud feature looks fatal | Medium | Mark optional and continue locally |
| 11 | Network is offline | Preflight | Diagnostic unexpectedly stalls | High | R1 is fully offline |
| 12 | Windows executable aliases | Detection | Store shim is mistaken for usable runtime | Medium | Report resolved executable path |

## 5. Competitive parity

The first slice should match the short install/login/run mental model used by modern developer CLIs. Its wedge is not a prettier installer; it is a preflight that understands local file-capable executors, repository safety, budgets, and evidence.

## 6. Success metrics

- Median time from command start to actionable readiness: under 60 seconds.
- Median time from installation start to first safe task command: under five minutes.
- At least four of five observed first-time users reach the first value moment without assistance.
- Zero paid agent launches and zero repository writes in `--check` mode.
- Every failed session maps to a named blocker rather than “unknown error.”

<a id="l3-risk"></a>
## 7. Risks and out of scope

| ID | Positive assumption to validate | Fatal? | Cheapest falsifying test |
|---|---|---:|---|
| R1 | Qualified users abandon because setup is too costly | Yes | Five observed current-path sessions |
| R2 | A readiness summary creates enough value before an agent run | Yes | Compare comprehension before and after the summary |
| R3 | `uvx` or `uv tool install` works on target clean machines | No | Windows/macOS/Linux CI and VM smoke tests |
| R4 | Binary presence is sufficient for a useful first recommendation | No | Record false-ready cases in five pilots |
| R5 | Dry-run is the right default for the first task | No | Ask users to choose before showing the default |
| R6 | The current default configuration is safe and small enough | No | Diff generated config against minimum fields actually read |

Deferred: Docker self-hosted distribution, native signed applications, automatic executor installation, automatic login, Cloud team onboarding, marketplace selection, and an automatically generated coding task.

## 8. Non-functional requirements

- Python 3.10–3.14 and Windows/macOS/Linux compatibility.
- Stable text output suitable for screenshots and support.
- JSON schema suitable for future UI onboarding.
- No secrets in output or generated files.
- Unit tests must not depend on installed third-party executors.

## Verification checklist

- [ ] Observe five first-time users before expanding the build.
- [ ] Test `--check` on clean Windows, macOS, and Linux environments.
- [ ] Verify zero writes and zero network calls in check mode.
- [ ] Confirm every requirement traces to the focused setup Job.
- [ ] Revisit native packaging only if runtime installation remains a measured blocker.

---

*Methodology: [Next Move Theory](https://nextmovetheory.com/?utm_source=nmt-product-requirements&utm_medium=skill-artifact) by Ivan Zamesin. This document is a hypothesis to validate, not a substitute for customer evidence.*
