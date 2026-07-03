"""
Executor layer — запускает агентов которые РЕАЛЬНО выполняют код, не просто генерируют текст.

Разница с providers:
  providers.py → один вызов LLM, возвращает текст
  executor/    → агент с инструментами (Read/Write/Bash), реально изменяет файлы

Типы исполнителей:
  cursor       → Cursor Agent API (agentic, file access via cursor-sdk) — DEFAULT
  claude-code  → claude -p "task" --output-format json (полный доступ к инструментам)
  opencode     → OpenCode Go (agentic, file access via CLI или API)
  deepseek     → DeepSeek API (OpenAI-compatible, дешёвая генерация кода)
  zen          → OpenCode Zen (анализ, планирование, review)
  mimo         → MiMo API (OpenAI-совместимый, дешёвый батч)

Multi-agent:
  MultiAgentOrchestrator → параллельный запуск задач на нескольких агентах
"""

from voly.executor.base import Executor, ExecutorResult
from voly.executor.cursor import CursorExecutor
from voly.executor.claude_code import ClaudeCodeExecutor
from voly.executor.deepseek import DeepSeekExecutor
from voly.executor.mimo import MiMoExecutor
from voly.executor.multi_agent import AgentTask, MultiAgentOrchestrator, OrchestrationReport
from voly.executor.opencode import OpenCodeExecutor
from voly.executor.zen import ZenExecutor

__all__ = [
    "Executor",
    "ExecutorResult",
    "CursorExecutor",
    "ClaudeCodeExecutor",
    "DeepSeekExecutor",
    "MiMoExecutor",
    "OpenCodeExecutor",
    "ZenExecutor",
    "AgentTask",
    "MultiAgentOrchestrator",
    "OrchestrationReport",
]
