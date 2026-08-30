# Skill Registry

## Introduction

**Skill Registry** is the centralized skill store and management system in VOLY. The registry provides a single API and CLI for registering, searching, versioning, and auto-creating skills. Any VOLY agent uses the registry to find a suitable skill for the current task based on context, compatibility, and request attributes.

## What skills are

A **skill** is a modular, reusable description of an agent's ability to perform a concrete action. A skill can represent:
- an external API call (e.g. `deploy-to-kubernetes`)
- a script launch (`run-tests`)
- service interaction (`create-jira-ticket`)
- a command sequence for CI/CD

Skills are separated from agent logic. Agents *reference* skills, while skills are defined in the registry — this allows reusing a capability across different agents and projects.

## Skill sources (`SkillSource`)

| Source | Description | Priority |
|----------|----------|-----------|
| `BUILTIN` | Built-in VOLY core skills | Base |
| `PROJECT` | Project skills from `.voly/skills/` | High |
| `ORGANIZATION` | Organization skills from a shared repository | High |
| `MARKETPLACE` | Community skills (Cloudflare Worker) | Medium |
| `GENERATED` | Auto-generated from successful runs | Draft until approved |

## Built-in skills

| ID | Name | Tags |
|----|----------|------|
| `skill-architecture` | Software Architecture | architecture, design, system |
| `skill-nextjs` | Next.js Development | nextjs, react, frontend |
| `skill-dotnet` | .NET Development | dotnet, csharp, aspnet |
| `skill-postgres` | PostgreSQL | postgres, sql, database |
| `skill-docker` | Docker & Containers | docker, container, devops |
| `skill-kubernetes` | Kubernetes | kubernetes, k8s, orchestration |
| `skill-security` | Security Best Practices | security, owasp, compliance |
| `skill-testing` | Testing Strategy | testing, quality, tdd |
| `skill-temporal` | Temporal Workflows | temporal, workflow |
| `skill-cloudflare` | Cloudflare Platform | cloudflare, serverless, edge |

## Skill structure

```python
@dataclass
class Skill:
    id: str                          # unique identifier
    name: str                        # human-readable name
    description: str                 # description
    source: SkillSource              # source (builtin/project/org/marketplace/generated)
    tags: list[str]                  # search tags
    capabilities: list[str]          # what it can do (architecture, frontend, testing...)
    required_tools: list[str]        # required MCP tools
    compatible_agents: list[str]     # agents that may use the skill
    compatible_languages: list[str]  # programming languages (* = all)
    compatible_frameworks: list[str] # frameworks (* = all)
    content: str                     # skill body (instructions / best practices)
    version: str                     # skill version
    usage_count: int                 # usage counter
    success_rate: float              # successful application rate (0.0–1.0)
```

## Registering a skill from YAML

**Step 1: create file `.voly/skills/deploy-service.yaml`**

```yaml
id: deploy-service
name: Deploy Service
description: Deploys a service to Kubernetes from a manifest
source: project
tags:
  - kubernetes
  - deploy
  - microservices
capabilities:
  - deployment
  - orchestration
required_tools:
  - kubernetes
compatible_agents:
  - devops
  - architect
compatible_languages:
  - "*"
compatible_frameworks:
  - "*"
content: |
  For deploy use kubectl apply -f <manifest>.
  Always check readiness probe before finalizing the deploy.
  Roll back with kubectl rollout undo.
```

**Step 2: files from `.voly/skills/` are picked up automatically** when running `voly` from the project directory.

## Searching skills via CLI

```bash
# All skills
voly registry skills

# By tag
voly registry skills --tag kubernetes
voly registry skills --tag deploy --tag devops

# By compatible agent
voly registry skills --agent devops

# By language
voly registry skills --lang python
voly registry skills --lang typescript --lang go

# Combined search
voly registry skills --tag security --agent reviewer --lang python
```

## Auto-generating skills

After each successful task run, VOLY analyzes the result and may generate a new skill:

```python
# Inside pipeline.py — called automatically
skill = registry.auto_generate(
    task="task",
    result="execution result",
    agent_name="developer",
)
# skill.source = SkillSource.GENERATED
# skill.status = SkillStatus.CANDIDATE
```

A generated skill enters the candidate queue. To confirm:

```python
from voly.registry.skills import SkillRegistry

reg = SkillRegistry()
reg.approve_candidate("skill-id")  # moves to ACTIVE
reg.reject_candidate("skill-id")   # removes the candidate
```

## Programmatic access

```python
from voly.registry.skills import SkillRegistry, Skill, SkillSource

reg = SkillRegistry()

# Search
skills = reg.search(tags=["kubernetes"], agent="devops", language="go")

# Register
reg.register(Skill(
    id="my-skill",
    name="My Skill",
    description="...",
    source=SkillSource.PROJECT,
    tags=["custom"],
    capabilities=["custom-action"],
    compatible_agents=["developer"],
    compatible_languages=["python"],
    compatible_frameworks=["*"],
    content="Instructions for the agent...",
))

# Get a specific skill
skill = reg.get("skill-postgres")
print(skill.content)
```

## Marketplace CLI

Marketplace is deployed as a Cloudflare Worker. URL is set in `voly.yaml`:

```yaml
registry:
  skills_path: ".voly/skills"
  marketplace_url: "${CF_WORKER_MARKETPLACE_URL}"
```

Or via environment variables: `CF_WORKER_MARKETPLACE_URL`, `MARKETPLACE_URL`.

```bash
# List skills in marketplace
voly skill list

# Local registry (builtin + .voly/skills/)
voly skill list --local

# Semantic search
voly skill search "react frontend"

# Install into .voly/skills/
voly skill install skill-nextjs

# Publish YAML
voly skill publish .voly/skills/my-skill.yaml

# Skill details
voly skill show skill-nextjs
voly skill show my-skill --local
```

## Programmatic marketplace access

```python
from voly.registry.skills import create_skill_registry

reg = create_skill_registry(
    skills_path=".voly/skills",
    marketplace_url="${CF_WORKER_MARKETPLACE_URL}",
)

# Install from marketplace
skill = reg.install_from_marketplace("skill-nextjs")

# Publish
reg.publish_to_marketplace({"id": "my-skill", "name": "My Skill", ...})
```
