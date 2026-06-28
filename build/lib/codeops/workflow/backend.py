"""
Persistent workflow backend — sync WorkflowInstance with remote Worker + D1.
"""

from __future__ import annotations

from typing import Any

from codeops.workflow import (
    StepState,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowState,
    WorkflowStep,
)
from codeops.workflow.client import WorkflowClient


def _definition_from_payload(definition_data: dict[str, Any], workflow_name: str) -> WorkflowDefinition:
    wf_def = WorkflowDefinition(
        name=definition_data.get("name", workflow_name),
        description=definition_data.get("description", ""),
        version=definition_data.get("version", "1.0.0"),
    )
    steps_data = definition_data.get("steps") or []
    if isinstance(steps_data, list):
        for sdata in steps_data:
            wf_def.steps[sdata["name"]] = WorkflowStep(
                name=sdata["name"],
                agent=sdata["agent"],
                task_template=sdata.get("task_template", ""),
                depends_on=list(sdata.get("depends_on") or []),
                approval=sdata.get("approval", "auto"),
                max_retries=int(sdata.get("max_retries") or 3),
            )
    elif isinstance(steps_data, dict):
        for sname, sdata in steps_data.items():
            if isinstance(sdata, dict) and "agent" in sdata:
                wf_def.steps[sname] = WorkflowStep(
                    name=sname,
                    agent=sdata["agent"],
                    task_template=sdata.get("task_template", ""),
                    depends_on=list(sdata.get("depends_on") or []),
                    approval=sdata.get("approval", "auto"),
                    max_retries=int(sdata.get("max_retries") or 3),
                )
    return wf_def


def instance_to_remote_payload(instance: WorkflowInstance, task: str = "") -> dict[str, Any]:
    steps: dict[str, Any] = {}
    for name, step in instance.steps.items():
        steps[name] = {
            "name": step.name,
            "agent": step.agent,
            "task_template": step.task_template,
            "depends_on": step.depends_on,
            "approval": step.approval,
            "max_retries": step.max_retries,
            "state": step.state.value,
            "result": step.result,
            "error": step.error,
            "retries": step.retries,
        }

    definition = instance.definition.to_dict()
    definition["steps"] = list(definition["steps"].values())

    return {
        "id": instance.id,
        "workflow": instance.definition.name,
        "state": instance.state.value,
        "task": task,
        "inputs": instance.inputs,
        "definition": definition,
        "steps": steps,
        "approvals_pending": list(instance.approvals_pending),
        "created_at": int(instance.created_at * 1000),
        "started_at": int(instance.started_at * 1000) if instance.started_at else 0,
        "finished_at": int(instance.finished_at * 1000) if instance.finished_at else 0,
        "progress": instance.progress(),
    }


def instance_from_remote_payload(data: dict[str, Any]) -> WorkflowInstance:
    workflow_name = str(data.get("workflow", "unknown"))
    definition_data = data.get("definition") or {}
    if isinstance(definition_data, dict) and definition_data.get("steps"):
        wf_def = _definition_from_payload(definition_data, workflow_name)
    else:
        wf_def = WorkflowDefinition(name=workflow_name)

    instance = WorkflowInstance(
        id=str(data["id"]),
        definition=wf_def,
        inputs=dict(data.get("inputs") or {}),
    )
    instance.state = WorkflowState(str(data.get("state", "created")))
    instance.approvals_pending = set(data.get("approvals_pending") or [])

    remote_steps = data.get("steps") or {}
    for sname, sdata in remote_steps.items():
        if sname not in instance.steps:
            continue
        step = instance.steps[sname]
        try:
            step.state = StepState(str(sdata.get("state", "pending")))
        except ValueError:
            step.state = StepState.PENDING
        step.result = str(sdata.get("result") or "")
        step.error = str(sdata.get("error") or "")
        step.retries = int(sdata.get("retries") or 0)

    created_ms = int(data.get("created_at") or 0)
    if created_ms > 0:
        instance.created_at = created_ms / 1000.0
    started_ms = int(data.get("started_at") or 0)
    if started_ms > 0:
        instance.started_at = started_ms / 1000.0
    finished_ms = int(data.get("finished_at") or 0)
    if finished_ms > 0:
        instance.finished_at = finished_ms / 1000.0

    return instance


class PersistentWorkflowBackend:
    def __init__(self, client: WorkflowClient):
        self.client = client
        self._tasks: dict[str, str] = {}

    def remember_task(self, instance_id: str, task: str) -> None:
        self._tasks[instance_id] = task

    def task_for(self, instance_id: str) -> str:
        if instance_id in self._tasks:
            return self._tasks[instance_id]
        try:
            data = self.client.get_status(instance_id)
            task = str(data.get("task") or "")
            if task:
                self._tasks[instance_id] = task
            return task
        except Exception:
            return ""

    def start_remote(self, workflow_name: str, task: str, inputs: dict[str, Any] | None = None) -> str:
        instance_id = self.client.start(workflow_name, task, inputs)
        self.remember_task(instance_id, task)
        return instance_id

    def load(self, instance_id: str) -> WorkflowInstance | None:
        try:
            data = self.client.get_status(instance_id)
        except Exception:
            return None
        instance = instance_from_remote_payload(data)
        if "task" in data:
            self.remember_task(instance_id, str(data["task"]))
        return instance

    def save(self, instance: WorkflowInstance, task: str | None = None) -> None:
        task_text = task if task is not None else self.task_for(instance.id)
        payload = instance_to_remote_payload(instance, task=task_text)
        self.client.save_instance(instance.id, payload)

    def approve_remote(self, instance_id: str, step: str) -> bool:
        try:
            self.client.approve(instance_id, step)
            return True
        except Exception:
            return False

    def reject_remote(self, instance_id: str, step: str) -> bool:
        try:
            self.client.reject(instance_id, step)
            return True
        except Exception:
            return False

    def list_remote(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.client.list_instances(limit=limit)
