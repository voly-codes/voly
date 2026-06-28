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

from codeops.executor.base import Executor, ExecutorResult
from codeops.executor.cursor import CursorExecutor
from codeops.executor.claude_code import ClaudeCodeExecutor
from codeops.executor.deepseek import DeepSeekExecutor
from codeops.executor.mimo import MiMoExecutor
from codeops.executor.multi_agent import AgentTask, MultiAgentOrchestrator, OrchestrationReport
from codeops.executor.opencode import OpenCodeExecutor
from codeops.executor.zen import ZenExecutor

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
