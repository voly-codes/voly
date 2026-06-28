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
      provider: "codeops",
      capabilities: { streaming: false, tasks: true, mcp: `${root}/mcp` },
      skills: [
        skill("implement", "Implementation", "Writes and implements code", ["code", "implement", "feature"], [
          "Implement OAuth2 login",
        ]),
      ],
    },
    {
      name: "architect",
      description: "Архитектурное планирование",
      url: `${root}/agents/architect`,
      version: "1.0.0",
      provider: "codeops",
      capabilities: { streaming: false, tasks: true, mcp: `${root}/mcp` },
      skills: [skill("design", "System Design", "Designs architecture", ["architecture", "design"])],
    },
    {
      name: "reviewer",
      description: "Код-ревью",
      url: `${root}/agents/reviewer`,
      version: "1.0.0",
      provider: "codeops",
      capabilities: { streaming: false, tasks: true, mcp: `${root}/mcp` },
      skills: [skill("review", "Code Review", "Reviews code", ["review", "code"])],
    },
    {
      name: "tester",
      description: "Тестирование",
      url: `${root}/agents/tester`,
      version: "1.0.0",
      provider: "codeops",
      capabilities: { streaming: false, tasks: true, mcp: `${root}/mcp` },
      skills: [skill("test", "Testing", "Writes tests", ["test", "qa"])],
    },
    {
      name: "bugfixer",
      description: "Исправление багов",
      url: `${root}/agents/bugfixer`,
      version: "1.0.0",
      provider: "codeops",
      capabilities: { streaming: false, tasks: true, mcp: `${root}/mcp` },
      skills: [skill("bugfix", "Bug Fix", "Fixes bugs", ["bug", "fix"])],
    },
    {
      name: "devops",
      description: "Деплой",
      url: `${root}/agents/devops`,
      version: "1.0.0",
      provider: "codeops",
      capabilities: { streaming: false, tasks: true, mcp: `${root}/mcp` },
      skills: [skill("deploy", "Deployment", "Deploy and CI", ["deploy", "ci"])],
    },
    {
      name: "security",
      description: "Безопасность",
      url: `${root}/agents/security`,
      version: "1.0.0",
      provider: "codeops",
      capabilities: { streaming: false, tasks: true, mcp: `${root}/mcp` },
      skills: [skill("security", "Security", "Security scan", ["security", "audit"])],
    },
  ];
}

export function getBuiltinAgent(name: string, baseUrl: string): AgentCardDef | undefined {
  return buildBuiltinAgents(baseUrl).find((a) => a.name === name);
}
