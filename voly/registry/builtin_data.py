"""Default builtin skill definitions — used to seed the CF Marketplace.

These are NOT auto-loaded into SkillRegistry at runtime.
Skills are only active after a user explicitly installs them via:
  - UI: Skill Marketplace → Install
  - CLI: voly skill install <id>

To push these to CF Marketplace run:
  voly skill seed  (seeds missing builtins without overwriting existing)
"""

from __future__ import annotations

from voly.registry.skills import Skill, SkillSource

BUILTIN_SKILLS: list[Skill] = [
    Skill(
        id="skill-architecture",
        name="Software Architecture",
        description="Architecture design principles: microservices, monoliths, event-driven, CQRS",
        source=SkillSource.BUILTIN,
        tags=["architecture", "design", "system"],
        capabilities=["architecture", "system-design"],
        compatible_agents=["architect"],
        compatible_languages=["*"],
        compatible_frameworks=["*"],
        content="Architecture principles: SOLID, DDD, Clean Architecture, Hexagonal Architecture...",
    ),
    Skill(
        id="skill-nextjs",
        name="Next.js Development",
        description="Next.js 14/15 development: App Router, Server Components, API Routes, Middleware",
        source=SkillSource.BUILTIN,
        tags=["nextjs", "react", "frontend", "vercel"],
        capabilities=["frontend", "ssr", "api"],
        compatible_agents=["developer", "architect"],
        compatible_languages=["typescript", "javascript"],
        compatible_frameworks=["nextjs", "react"],
        content="Next.js best practices: use the App Router and Server Components by default...",
    ),
    Skill(
        id="skill-dotnet",
        name=".NET Development",
        description=".NET 8/9 development: ASP.NET Core, Entity Framework, Minimal APIs, SignalR",
        source=SkillSource.BUILTIN,
        tags=["dotnet", "csharp", "aspnet", "backend"],
        capabilities=["backend", "api", "orm"],
        compatible_agents=["developer", "architect"],
        compatible_languages=["csharp"],
        compatible_frameworks=["dotnet", "aspnet", "entity-framework"],
        content=".NET best practices: use Minimal APIs, primary constructors, Native AOT...",
    ),
    Skill(
        id="skill-postgres",
        name="PostgreSQL",
        description="Working with PostgreSQL: migrations, indexes, query optimization, replication",
        source=SkillSource.BUILTIN,
        tags=["postgres", "sql", "database", "migration"],
        capabilities=["database", "sql", "migrations"],
        required_tools=["postgresql"],
        compatible_agents=["developer", "architect", "devops"],
        compatible_languages=["*"],
        compatible_frameworks=["*"],
        content="PostgreSQL best practices: use EXPLAIN ANALYZE, proper indexes, connection pooling...",
    ),
    Skill(
        id="skill-docker",
        name="Docker & Containers",
        description="Application containerization: Dockerfile, docker-compose, multi-stage builds",
        source=SkillSource.BUILTIN,
        tags=["docker", "container", "devops"],
        capabilities=["containerization", "deployment"],
        required_tools=["docker"],
        compatible_agents=["devops", "developer"],
        compatible_languages=["*"],
        compatible_frameworks=["*"],
        content="Docker best practices: multi-stage builds, .dockerignore, non-root user, healthchecks...",
    ),
    Skill(
        id="skill-kubernetes",
        name="Kubernetes",
        description="Kubernetes orchestration: deployment, services, ingress, configmaps, secrets",
        source=SkillSource.BUILTIN,
        tags=["kubernetes", "k8s", "orchestration", "devops"],
        capabilities=["orchestration", "deployment", "scaling"],
        required_tools=["kubernetes"],
        compatible_agents=["devops", "architect"],
        compatible_languages=["*"],
        compatible_frameworks=["*"],
        content="Kubernetes best practices: resource limits, readiness probes, pod anti-affinity...",
    ),
    Skill(
        id="skill-security",
        name="Security Best Practices",
        description="Security: OWASP Top 10, secrets management, dependency scanning, SAST",
        source=SkillSource.BUILTIN,
        tags=["security", "owasp", "compliance"],
        capabilities=["security-audit", "vulnerability-scanning"],
        compatible_agents=["security", "reviewer"],
        compatible_languages=["*"],
        compatible_frameworks=["*"],
        content="Security checklist: OWASP Top 10, secrets in env vars (not code), dependency audit, input validation...",
    ),
    Skill(
        id="skill-testing",
        name="Testing Strategy",
        description="Testing strategy: unit, integration, e2e, contract tests, TDD",
        source=SkillSource.BUILTIN,
        tags=["testing", "quality", "tdd"],
        capabilities=["testing", "unit-tests", "integration-tests"],
        compatible_agents=["tester", "developer"],
        compatible_languages=["*"],
        compatible_frameworks=["*"],
        content="Testing pyramid: many unit tests, fewer integration tests, minimal e2e...",
    ),
    Skill(
        id="skill-temporal",
        name="Temporal Workflows",
        description="Temporal development: workflows, activities, signals, queries, retries",
        source=SkillSource.BUILTIN,
        tags=["temporal", "workflow", "orchestration"],
        capabilities=["workflow", "orchestration"],
        required_tools=["temporal"],
        compatible_agents=["architect", "developer"],
        compatible_languages=["typescript", "go", "java", "python"],
        compatible_frameworks=["temporal", "nextjs", "dotnet"],
        content="Temporal best practices: deterministic workflows, idempotent activities, heartbeats for long-running...",
    ),
    Skill(
        id="skill-cloudflare",
        name="Cloudflare Platform",
        description="Working with Cloudflare: Workers, R2, D1, Pages, Queues, KV",
        source=SkillSource.BUILTIN,
        tags=["cloudflare", "serverless", "edge"],
        capabilities=["serverless", "storage", "edge-computing"],
        required_tools=["cloudflare"],
        compatible_agents=["developer", "devops"],
        compatible_languages=["typescript", "javascript", "rust"],
        compatible_frameworks=["nextjs", "hono", "remix"],
        content="Cloudflare best practices: Workers for edge compute, R2 for object storage, D1 for SQLite...",
    ),
    Skill(
        id="skill-pmbok6",
        name="PMBOK 6th Edition",
        description=(
            "PMBOK® Guide 6th Edition — the complete PMI project management methodology. "
            "5 process groups, 10 knowledge areas, 49 processes, EVM/PERT formulas, "
            "Agile adaptation, charter/WBS/register templates. Use for project planning, "
            "audits, PMP preparation, and risk assessment."
        ),
        source=SkillSource.BUILTIN,
        tags=[
            "pmbok", "project-management", "pmp", "risk-management",
            "wbs", "earned-value", "stakeholder", "agile", "planning",
        ],
        capabilities=[
            "project-planning", "risk-analysis", "scheduling",
            "cost-management", "stakeholder-management",
        ],
        compatible_agents=["architect", "developer", "reviewer"],
        compatible_languages=["*"],
        compatible_frameworks=["*"],
        author="PMI / mb-mal",
        version="6.0.0",
        content=(
            "PMBOK 6 skill package — installs references (17 files) and templates (4 files). "
            "After install: SKILL.md is the navigator. "
            "Key files: references/process-map.md, references/formulas.md, "
            "references/itto-*.md (10 knowledge areas), templates/project-charter.md."
        ),
        metadata={
            "repository": "https://github.com/mb-mal/pmbok6.git",
            "install_kind": "git",
        },
    ),
]
