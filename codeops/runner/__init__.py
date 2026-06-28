"""Agent Runner — унифицированный запуск executors с бюджетом и телеметрией."""

from codeops.runner.agent_runner import AgentRunner, RunnerResult, resolve_executor

__all__ = ["AgentRunner", "RunnerResult", "resolve_executor"]
