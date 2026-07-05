export interface AgentSkillDef {
  id: string;
  name: string;
  description: string;
  tags: string[];
  examples: string[];
  inputModes: string[];
  outputModes: string[];
}

export interface AgentCardDef {
  name: string;
  description: string;
  url: string;
  version: string;
  provider: string;
  skills: AgentSkillDef[];
  capabilities: Record<string, unknown>;
}

function skill(
  id: string,
  name: string,
  description: string,
  tags: string[],
  examples: string[] = [],
): AgentSkillDef {
  return {
    id,
    name,
    description,
    tags,
    examples,
    inputModes: ["text"],
    outputModes: ["text"],
  };
}

export function buildBuiltinAgents(baseUrl: string): AgentCardDef[] {
  const root = baseUrl.replace(/\/$/, "");
  return [
    {
      name: "developer",
      description: "Реализация кода и фич",
      url: `${root}/agents/developer`,
      version: "1.0.0",
      provider: "voly",
      capabilities: { streaming: false, tasks: true },
      skills: [
        skill("implement", "Implementation", "Writes and implements code", ["code", "implement", "feature"], [
          "Implement OAuth2 login",
          "Add API endpoint",
        ]),
        skill("refactor", "Refactoring", "Refactors existing code", ["refactor", "cleanup"], ["Refactor auth module"]),
      ],
    },
    {
      name: "architect",
      description: "Архитектурное планирование",
      url: `${root}/agents/architect`,
      version: "1.0.0",
      provider: "voly",
      capabilities: { streaming: false, tasks: true },
      skills: [
        skill("design", "System Design", "Designs architecture and APIs", ["architecture", "design", "api"], [
          "Design payment service",
        ]),
      ],
    },
    {
      name: "reviewer",
      description: "Код-ревью и статический анализ",
      url: `${root}/agents/reviewer`,
      version: "1.0.0",
      provider: "voly",
      capabilities: { streaming: false, tasks: true },
      skills: [
        skill("review", "Code Review", "Reviews code quality and security", ["review", "code", "quality"], [
          "Review this PR",
        ]),
      ],
    },
    {
      name: "tester",
      description: "Тестирование и QA",
      url: `${root}/agents/tester`,
      version: "1.0.0",
      provider: "voly",
      capabilities: { streaming: false, tasks: true },
      skills: [
        skill("test", "Testing", "Writes and runs tests", ["test", "unittest", "qa"], [
          "Write unit tests for auth",
        ]),
      ],
    },
    {
      name: "bugfixer",
      description: "Исправление багов",
      url: `${root}/agents/bugfixer`,
      version: "1.0.0",
      provider: "voly",
      capabilities: { streaming: false, tasks: true },
      skills: [
        skill("bugfix", "Bug Fix", "Analyzes and fixes bugs", ["bug", "fix", "debug"], ["Fix login 500 error"]),
      ],
    },
    {
      name: "devops",
      description: "Деплой и инфраструктура",
      url: `${root}/agents/devops`,
      version: "1.0.0",
      provider: "voly",
      capabilities: { streaming: false, tasks: true },
      skills: [
        skill("deploy", "Deployment", "Prepares deployment and CI", ["deploy", "ci", "infra"], [
          "Prepare staging deploy",
        ]),
      ],
    },
    {
      name: "security",
      description: "Проверка безопасности",
      url: `${root}/agents/security`,
      version: "1.0.0",
      provider: "voly",
      capabilities: { streaming: false, tasks: true },
      skills: [
        skill("security", "Security Scan", "Security review and scanning", ["security", "audit"], [
          "Scan auth for vulnerabilities",
        ]),
      ],
    },
  ];
}

export function getBuiltinAgent(name: string, baseUrl: string): AgentCardDef | undefined {
  return buildBuiltinAgents(baseUrl).find((a) => a.name === name);
}
