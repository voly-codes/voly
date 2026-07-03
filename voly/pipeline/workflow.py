"""_WorkflowMixin: run_workflow, approve_workflow_step, resume_workflow."""

from __future__ import annotations

from typing import Any


class _WorkflowMixin:
    """Mixin for Pipeline: workflow orchestration methods."""

    def run_workflow(
        self,
        workflow_name: str,
        task: str,
        inputs: dict[str, Any] | None = None,
        *,
        instance_id: str | None = None,
    ) -> str:
        from voly.workflow import StepState, WorkflowState

        if instance_id:
            instance = self.workflow.get_instance(instance_id)  # type: ignore[attr-defined]
            if not instance:
                raise ValueError(f"Workflow instance not found: {instance_id}")
        else:
            instance_id = self.workflow.start(workflow_name, inputs, task=task)  # type: ignore[attr-defined]
            instance = self.workflow.get_instance(instance_id)  # type: ignore[attr-defined]
            if not instance:
                raise ValueError(f"Workflow instance not found: {instance_id}")

        instance.state = WorkflowState.RUNNING
        if not instance.started_at:
            instance.started_at = __import__("time").time()
        self.workflow.persist(instance, task=task)  # type: ignore[attr-defined]

        while True:
            ready = instance.pending_steps()
            if not ready:
                if instance.approvals_pending:
                    for step_name in list(instance.approvals_pending):
                        step = instance.steps[step_name]
                        step.state = StepState.WAITING_APPROVAL
                    instance.state = WorkflowState.PAUSED
                    self.workflow.persist(instance, task=task)  # type: ignore[attr-defined]
                    return instance_id
                break

            for step_name in ready:
                step = instance.steps[step_name]
                step.state = StepState.RUNNING
                self.workflow.persist(instance, task=task)  # type: ignore[attr-defined]

                step_task = step.task_template.replace("{task}", task)
                try:
                    result = self.run(step_task)  # type: ignore[attr-defined]
                    if result.success:
                        step.state = StepState.COMPLETED
                        step.result = result.response.content if result.response else ""
                    else:
                        if step.retries < step.max_retries:
                            step.retries += 1
                            step.state = StepState.PENDING
                        else:
                            step.state = StepState.FAILED
                            step.error = result.error
                except Exception as e:
                    if step.retries < step.max_retries:
                        step.retries += 1
                        step.state = StepState.PENDING
                    else:
                        step.state = StepState.FAILED
                        step.error = str(e)
                self.workflow.persist(instance, task=task)  # type: ignore[attr-defined]

        self._check_workflow_done(instance)
        self.workflow.persist(instance, task=task)  # type: ignore[attr-defined]
        return instance_id

    def approve_workflow_step(self, instance_id: str, step_name: str) -> bool:
        instance = self.workflow.get_instance(instance_id)  # type: ignore[attr-defined]
        if not instance:
            return False
        approved = instance.approve(step_name)
        if approved:
            backend = getattr(self.workflow, "_persistent", None)  # type: ignore[attr-defined]
            if backend:
                backend.approve_remote(instance_id, step_name)
                refreshed = self.workflow.get_instance(instance_id)  # type: ignore[attr-defined]
                if refreshed:
                    instance = refreshed
            self.workflow.persist(instance)  # type: ignore[attr-defined]
        return approved

    def resume_workflow(self, instance_id: str, task: str | None = None) -> str | None:
        from voly.workflow import WorkflowState

        instance = self.workflow.get_instance(instance_id)  # type: ignore[attr-defined]
        if not instance or instance.state != WorkflowState.PAUSED:
            return None
        backend = getattr(self.workflow, "_persistent", None)  # type: ignore[attr-defined]
        resolved_task = task or (backend.task_for(instance_id) if backend else "") or ""
        if not resolved_task:
            return None
        instance.state = WorkflowState.RUNNING
        self.workflow.persist(instance, task=resolved_task)  # type: ignore[attr-defined]
        return self.run_workflow(
            instance.definition.name,
            resolved_task,
            instance.inputs,
            instance_id=instance_id,
        )

    def _check_workflow_done(self, instance: Any) -> None:
        from voly.workflow import StepState, WorkflowState

        all_done = all(
            s.state in (StepState.COMPLETED, StepState.FAILED, StepState.SKIPPED)
            for s in instance.steps.values()
        )
        if all_done:
            has_failure = any(s.state == StepState.FAILED for s in instance.steps.values())
            instance.state = WorkflowState.FAILED if has_failure else WorkflowState.COMPLETED
            instance.finished_at = __import__("time").time()
