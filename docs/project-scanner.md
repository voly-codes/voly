# Project Scanner

## Purpose

Project Scanner analyzes a repository and builds a project profile (`ProjectProfile`) used at two levels:

1. **AgentRouter** — selects agents and skills that match the stack
2. **SkillRegistry** — filters skills by compatible language and framework

Without scanning, the router behaves as a generic agent without project context.

## What the Scanner detects

### Languages (`LanguageInfo`)

| Field | Description |
|------|----------|
| `name` | Language name (Python, TypeScript...) |
| `percentage` | Share of files for this language |
| `files_count` | Number of files |
| `version` | Version from `pyproject.toml`, `package.json`, `.tool-versions` |
| `package_manager` | pip, npm, yarn, pnpm, cargo, go mod... |

Detected via file extensions and config files (`go.mod`, `Cargo.toml`, `pubspec.yaml`, etc.)

### Frameworks (`FrameworkInfo`)

| Field | Description |
|------|----------|
| `name` | Framework name |
| `language` | Related language |
| `config_file` | Config file used for detection |
| `version` | Version from dependencies |

Example detection patterns:

| Config file | Framework |
|------------|-----------|
| `next.config.js/ts` | Next.js |
| `pyproject.toml` + `[tool.fastapi]` | FastAPI |
| `angular.json` | Angular |
| `Cargo.toml` + `actix-web` dep | Actix |
| `pom.xml` / `build.gradle` | Spring Boot |
| `mix.exs` | Phoenix |

### CI/CD (`CIInfo`)

| Field | Description |
|------|----------|
| `provider` | github-actions, gitlab-ci, circleci, travis... |
| `config_path` | Path to config file |
| `has_deploy` | Whether deploy steps exist |
| `has_tests` | Whether test steps exist |

### Infrastructure (`InfraInfo`)

Detected by presence of files:

| File | Tool |
|------|-----------|
| `Dockerfile` / `docker-compose.yml` | Docker |
| `*.tf` | Terraform |
| `kubernetes/`, `k8s/`, `*.yaml` with `kind: Deployment` | Kubernetes |
| `serverless.yml` | Serverless Framework |
| `cdk.json` | AWS CDK |

## ProjectProfile — full structure

```python
@dataclass
class ProjectProfile:
    # Base metadata
    name: str              # directory name
    root_path: str         # absolute path
    total_files: int       # total files
    total_lines: int       # total lines of code

    # Stack
    languages: list[LanguageInfo]     # by descending percentage
    frameworks: list[FrameworkInfo]
    ci: CIInfo | None
    infra: InfraInfo

    # Typology
    project_type: str      # web-app, api, library, cli, monorepo...
    has_tests: bool
    has_docs: bool
    has_docker: bool

    # Recommendations
    recommended_agents: list[str]    # agent ids suitable for the project
    recommended_skills: list[str]    # skill ids suitable for the project
    complexity_score: float          # 0.0–1.0
```

## CLI

```bash
# Scan current directory
voly scan

# Scan a specific path
voly scan /path/to/project

# JSON output
voly scan --json

# Languages and frameworks only (fast mode)
voly scan --summary
```

### Example output

```
Project Profile
══════════════════════════════════════════

Name:        my-saas
Path:        /home/user/projects/my-saas
Files:       1,247
Lines:       89,341
Type:        web-app
Complexity:  0.73

Languages:
  TypeScript  68%  (847 files)   v5.4    [npm]
  Python      24%  (299 files)   v3.12   [pip]
  SQL          8%  (101 files)

Frameworks:
  Next.js   15.0  →  next.config.ts
  FastAPI   0.111 →  pyproject.toml

CI/CD:  github-actions
  Config:    .github/workflows/
  Tests:     yes
  Deploy:    yes

Infra:  Docker, Kubernetes
  docker-compose.yml, k8s/

Recommended Agents:  developer, architect, devops
Recommended Skills:  skill-nextjs, skill-postgres, skill-docker, skill-kubernetes
```

### JSON output

```json
{
  "name": "my-saas",
  "root_path": "/home/user/projects/my-saas",
  "total_files": 1247,
  "total_lines": 89341,
  "project_type": "web-app",
  "complexity_score": 0.73,
  "languages": [
    {"name": "TypeScript", "percentage": 68, "files_count": 847, "version": "5.4", "package_manager": "npm"},
    {"name": "Python", "percentage": 24, "files_count": 299, "version": "3.12", "package_manager": "pip"}
  ],
  "frameworks": [
    {"name": "Next.js", "language": "TypeScript", "config_file": "next.config.ts", "version": "15.0"},
    {"name": "FastAPI", "language": "Python", "config_file": "pyproject.toml", "version": "0.111"}
  ],
  "ci": {"provider": "github-actions", "config_path": ".github/workflows/", "has_tests": true, "has_deploy": true},
  "infra": {"docker": true, "kubernetes": true, "terraform": false},
  "recommended_agents": ["developer", "architect", "devops"],
  "recommended_skills": ["skill-nextjs", "skill-postgres", "skill-docker", "skill-kubernetes"]
}
```

## Impact on AgentRouter

After scanning, `AgentRouter` uses `ProjectProfile` when computing `routing_score`:

```
routing_score = base_score × language_match × framework_match × skill_coverage
```

- `language_match` — match of task language to project languages (0.0–1.0)
- `framework_match` — framework match (0.0–1.0)
- `skill_coverage` — share of agent skills covering the project stack

An agent with `language_match=0.9` and `framework_match=0.85` is preferred over a generic agent with `routing_score=0.5`.

## Extending detection

### Add a new language

```python
from voly.scanner import Scanner

scanner = Scanner(".")
scanner.add_language_pattern(
    name="Zig",
    extensions=[".zig"],
    config_files=["build.zig"],
    version_source="build.zig.zon",
)
```

### Add a new framework

```python
scanner.add_framework_pattern(
    name="Bun",
    language="TypeScript",
    config_file="bun.lockb",
    dep_key="bun",         # looks in package.json dependencies
)
```

## Programmatic access

```python
from voly.scanner import Scanner

scanner = Scanner("/path/to/project")
profile = scanner.scan()

print(profile.project_type)          # "web-app"
print(profile.complexity_score)      # 0.73
print([l.name for l in profile.languages])   # ["TypeScript", "Python"]
print(profile.recommended_skills)    # ["skill-nextjs", "skill-postgres"]

# Export to dict
data = profile.to_dict()

# Save to .voly/profile.json for caching
profile.save()

# Load cache without re-scanning
profile = Scanner.load_cached("/path/to/project")
```

> **Status**: supported core utility (Stage 0 decision, 2026-07-05). Live consumers: `voly scan`, project skill generation (`voly skill`), `Pipeline.scan_project()`. Language and framework detection work; `recommended_agents`/`recommended_skills` are heuristic; AgentRouter `routing_score` integration is as needed.
