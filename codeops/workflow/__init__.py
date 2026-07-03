"""
Workflow Engine — детерминированные multi-agent цепочки.

Позволяет:
    - Определять последовательности агентов (DAG-based)
    - Retries с exponential backoff
    - Checkpoints для возобновления
    - Pause/Resume с человеческими approval gates
    - Долгие задачи с отслеживанием прогресса
    - Вложенные workflow (саб-воркфлоу)

Формат определения workflow:
    workflow = Workflow("feature-delivery")
    workflow.step("architect", agent="architect", depends_on=[])
    workflow.step("develop", agent="developer", depends_on=["architect"])
    workflow.step("review", agent="reviewer", depends_on=["develop"])
    workflow.step("test", agent="tester", depends_on=["review"])
    workflow.step("deploy", agent="devops", depends_on=["test"], approval="human")

Рекомендуемый backend: Temporal (будущее)
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class StepState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowState(Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowStep:
    name: str
    agent: str
    task_template: str = ""
    depends_on: list[str] = field(default_factory=list)
    approval: str = "auto"
    retries: int = 0
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    timeout_seconds: float = 300.0
    state: StepState = StepState.PENDING
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    input_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent": self.agent,
            "task_template": self.task_template,
            "depends_on": self.depends_on,
            "approval": self.approval,
            "max_retries": self.max_retries,
            "state": self.state.value,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class WorkflowDefinition:
    name: str
    description: str = ""
    version: str = "1.0.0"
    steps: dict[str, WorkflowStep] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def step(
        self,
        name: str,
        agent: str,
        task_template: str = "",
        depends_on: list[str] | None = None,
        approval: str = "auto",
        max_retries: int = 3,
        retry_delay: float = 5.0,
        timeout: float = 300.0,
    ) -> WorkflowDefinition:
        self.steps[name] = WorkflowStep(
            name=name,
            agent=agent,
            task_template=task_template,
            depends_on=depends_on or [],
            approval=approval,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay,
            timeout_seconds=timeout,
        )
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "metadata": self.metadata,
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        step_names = set(self.steps.keys())

        for step in self.steps.values():
            for dep in step.depends_on:
                if dep not in step_names:
                    errors.append(f"Step '{step.name}' depends on unknown step '{dep}'")

        if self._has_cycles():
            errors.append("Workflow contains a cycle")

        if not step_names:
            errors.append("Workflow has no steps")

        return errors

    def _has_cycles(self) -> bool:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {name: WHITE for name in self.steps}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for dep in self.steps[node].depends_on:
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    return True
                if color[dep] == WHITE and dfs(dep):
                    return True
            color[node] = BLACK
            return False

        for name in self.steps:
            if color[name] == WHITE and dfs(name):
                return True
        return False


class WorkflowEngine:
    def __init__(self, persistent_backend: Any | None = None):
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._instances: dict[str, WorkflowInstance] = {}
        self._persistent = persistent_backend
        for name, wf in BUILTIN_WORKFLOWS.items():
            self._definitions[name] = wf

    def register(self, wf: WorkflowDefinition) -> None:
        self._definitions[wf.name] = wf

    def get(self, name: str) -> WorkflowDefinition | None:
        return self._definitions.get(name)

    def list_definitions(self) -> list[str]:
        return list(self._definitions.keys())

    def start(self, name: str, inputs: dict[str, Any] | None = None, *, task: str = "") -> str:
        wf_def = self._definitions.get(name)
        if not wf_def:
            raise ValueError(f"Unknown workflow: {name}")

        if self._persistent and task:
            instance_id = self._persistent.start_remote(name, task, inputs)
            instance = self._persistent.load(instance_id)
            if instance:
                self._instances[instance_id] = instance
            return instance_id

        instance_id = str(uuid.uuid4())
        instance = WorkflowInstance(
            id=instance_id,
            definition=wf_def,
            inputs=inputs or {},
        )
        self._instances[instance_id] = instance
        if self._persistent:
            self._persistent.remember_task(instance_id, task)
            self._persistent.save(instance, task=task)
        return instance_id

    def get_instance(self, instance_id: str) -> WorkflowInstance | None:
        if instance_id in self._instances:
            return self._instances[instance_id]
        if self._persistent:
            instance = self._persistent.load(instance_id)
            if instance:
                self._instances[instance_id] = instance
            return instance
        return None

    def persist(self, instance: WorkflowInstance, task: str | None = None) -> None:
        if self._persistent:
            self._persistent.save(instance, task=task)

    def list_instances(self) -> list[WorkflowInstance]:
        if self._persistent:
            remote = self._persistent.list_remote()
            instances: list[WorkflowInstance] = []
            for row in remote:
                inst = self.get_instance(str(row["id"]))
                if inst:
                    instances.append(inst)
            return instances
        return list(self._instances.values())

    def cancel(self, instance_id: str) -> bool:
        instance = self._instances.get(instance_id)
        if instance and instance.state in (WorkflowState.CREATED, WorkflowState.RUNNING, WorkflowState.PAUSED):
            for step in instance.steps.values():
                if step.state in (StepState.PENDING, StepState.RUNNING):
                    step.state = StepState.SKIPPED
            instance.state = WorkflowState.FAILED
            instance.finished_at = time.time()
            return True
        return False


class WorkflowInstance:
    def __init__(
        self,
        id: str,
        definition: WorkflowDefinition,
        inputs: dict[str, Any] | None = None,
    ):
        self.id = id
        self.definition = definition
        self.state = WorkflowState.CREATED
        self.inputs = inputs or {}
        self.steps: dict[str, WorkflowStep] = {}
        self.created_at = time.time()
        self.started_at = 0.0
        self.finished_at = 0.0
        self.approvals_pending: set[str] = set()

        for sname, sdef in definition.steps.items():
            step = WorkflowStep(
                name=sdef.name,
                agent=sdef.agent,
                task_template=sdef.task_template,
                depends_on=list(sdef.depends_on),
                approval=sdef.approval,
                max_retries=sdef.max_retries,
                retry_delay_seconds=sdef.retry_delay_seconds,
                timeout_seconds=sdef.timeout_seconds,
            )
            if sdef.approval == "human":
                self.approvals_pending.add(sname)
            self.steps[sname] = step

    def pending_steps(self) -> list[str]:
        ready: list[str] = []
        for sname, step in self.steps.items():
            if step.state != StepState.PENDING:
                continue
            if all(
                self.steps[dep].state == StepState.COMPLETED
                for dep in step.depends_on
            ):
                ready.append(sname)
        return ready

    def approve(self, step_name: str) -> bool:
        if step_name not in self.steps:
            return False
        step = self.steps[step_name]
        if step.state == StepState.WAITING_APPROVAL:
            step.state = StepState.PENDING
            self.approvals_pending.discard(step_name)
            return True
        return False

    def reject(self, step_name: str) -> bool:
        if step_name not in self.steps:
            return False
        step = self.steps[step_name]
        if step.state == StepState.WAITING_APPROVAL:
            step.state = StepState.SKIPPED
            self.approvals_pending.discard(step_name)
            return True
        return False

    def progress(self) -> dict[str, Any]:
        total = len(self.steps)
        completed = sum(1 for s in self.steps.values() if s.state == StepState.COMPLETED)
        failed = sum(1 for s in self.steps.values() if s.state == StepState.FAILED)
        skipped = sum(1 for s in self.steps.values() if s.state == StepState.SKIPPED)
        running = sum(1 for s in self.steps.values() if s.state == StepState.RUNNING)
        pending = sum(1 for s in self.steps.values() if s.state == StepState.PENDING)
        waiting = sum(1 for s in self.steps.values() if s.state == StepState.WAITING_APPROVAL)

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "running": running,
            "pending": pending,
            "waiting_approval": waiting,
            "percent": round((completed / total * 100) if total > 0 else 0, 1),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow": self.definition.name,
            "state": self.state.value,
            "progress": self.progress(),
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "approvals_pending": list(self.approvals_pending),
        }


BUILTIN_WORKFLOWS: dict[str, WorkflowDefinition] = {}


def _register_builtins() -> None:
    wf = WorkflowDefinition(
        name="feature-delivery",
        description="Стандартный процесс: архитектура → разработка → ревью → тесты → деплой",
    )
    wf.step("architect", agent="architect", task_template="Спроектируй решение для: {task}")
    wf.step("develop", agent="developer", depends_on=["architect"], task_template="Реализуй: {task}")
    wf.step("review", agent="reviewer", depends_on=["develop"], task_template="Проверь код для: {task}")
    wf.step("test", agent="tester", depends_on=["review"], task_template="Напиши тесты для: {task}")
    wf.step("deploy", agent="devops", depends_on=["test"], approval="human", task_template="Подготовь деплой для: {task}")
    BUILTIN_WORKFLOWS["feature-delivery"] = wf

    wf = WorkflowDefinition(
        name="bugfix",
        description="Процесс исправления бага: анализ → фикс → ревью → тесты",
    )
    wf.step("analyze", agent="developer", task_template="Проанализируй баг: {task}")
    wf.step("fix", agent="bugfixer", depends_on=["analyze"], task_template="Исправь баг: {task}")
    wf.step("review", agent="reviewer", depends_on=["fix"], task_template="Проверь исправление: {task}")
    wf.step("test", agent="tester", depends_on=["review"], task_template="Проверь, что баг исправлен: {task}")
    BUILTIN_WORKFLOWS["bugfix"] = wf

    wf = WorkflowDefinition(
        name="code-review",
        description="Полное код-ревью: статика → архитектура → безопасность",
    )
    wf.step("static-analysis", agent="reviewer", task_template="Статический анализ: {task}")
    wf.step("architecture-review", agent="architect", task_template="Архитектурное ревью: {task}")
    wf.step("security-scan", agent="security", task_template="Проверка безопасности: {task}")
    wf.step("report", agent="reviewer",
            depends_on=["static-analysis", "architecture-review", "security-scan"],
            task_template="Сформируй отчёт ревью для: {task}")
    BUILTIN_WORKFLOWS["code-review"] = wf


_register_builtins()


def create_workflow_engine(workflow_url: str = "") -> WorkflowEngine:
    from voly.workflow.backend import PersistentWorkflowBackend
    from voly.workflow.client import create_workflow_client

    client = create_workflow_client(workflow_url)
    if client:
        return WorkflowEngine(persistent_backend=PersistentWorkflowBackend(client))
    return WorkflowEngine()
