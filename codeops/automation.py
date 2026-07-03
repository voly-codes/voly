"""
Automation Score — оценка автоматизации задачи и сэкономленных ручных шагов.
"""

from __future__ import annotations

from voly.executor.base import ExecutorResult

FILE_EDITING_EXECUTORS = frozenset({"cursor", "claude-code", "opencode"})
TEXT_ONLY_EXECUTORS = frozenset({"deepseek", "mimo", "zen"})

# Базовый score по типу executor
EXECUTOR_BASE_SCORE: dict[str, float] = {
    "cursor": 0.92,
    "claude-code": 0.90,
    "opencode": 0.88,
    "deepseek": 0.55,
    "mimo": 0.50,
    "zen": 0.60,
}

# Сколько ручных шагов заменяет один turn агента
STEPS_PER_TURN: dict[str, int] = {
    "cursor": 4,
    "claude-code": 4,
    "opencode": 3,
    "deepseek": 1,
    "mimo": 1,
    "zen": 2,
}


def compute_automation_metrics(
    executor: str,
    result: ExecutorResult,
    *,
    task_type: str | None = None,
    via_pipeline: bool = False,
) -> tuple[float, int]:
    """
    Возвращает (automation_score 0..1, manual_steps_removed).

    Для pipeline-only вызовов (без file executor) score ниже.
    """
    if via_pipeline:
        base = 0.45 if task_type in ("docs", "summarization") else 0.55
        steps = max(1, result.num_turns or 1)
        if result.success:
            return min(1.0, base + 0.1), steps
        return base * 0.5, 0

    base = EXECUTOR_BASE_SCORE.get(executor, 0.5)
    turns = max(result.num_turns, 1 if result.success else 0)
    steps_per = STEPS_PER_TURN.get(executor, 2)
    manual_steps = turns * steps_per if result.success else 0

    if not result.success:
        return round(base * 0.4, 2), 0

    # Бонус за многоходовое выполнение (сложная задача автоматизирована целиком)
    turn_bonus = min(0.08, turns * 0.01)
    score = min(1.0, base + turn_bonus)
    return round(score, 2), manual_steps
