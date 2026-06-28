"""Tests for Workflow Engine."""

from codeops.workflow import (
    BUILTIN_WORKFLOWS,
    WorkflowDefinition,
    WorkflowEngine,
    StepState,
    WorkflowState,
)


def test_workflow_definition() -> None:
    wf = WorkflowDefinition(name="test", description="Test workflow")
    wf.step("step1", agent="developer", task_template="Do {task}")
    wf.step("step2", agent="reviewer", depends_on=["step1"], task_template="Review {task}")

    assert len(wf.steps) == 2
    assert wf.steps["step2"].depends_on == ["step1"]


def test_workflow_validation_valid() -> None:
    wf = WorkflowDefinition(name="test")
    wf.step("a", agent="developer")
    wf.step("b", agent="reviewer", depends_on=["a"])
    errors = wf.validate()
    assert errors == []


def test_workflow_validation_missing_dep() -> None:
    wf = WorkflowDefinition(name="test")
    wf.step("a", agent="developer", depends_on=["nonexistent"])
    errors = wf.validate()
    assert len(errors) > 0
    assert any("nonexistent" in e for e in errors)


def test_workflow_validation_empty() -> None:
    wf = WorkflowDefinition(name="test")
    errors = wf.validate()
    assert len(errors) > 0


def test_workflow_cycles() -> None:
    wf = WorkflowDefinition(name="test")
    wf.step("a", agent="developer", depends_on=["b"])
    wf.step("b", agent="reviewer", depends_on=["a"])
    errors = wf.validate()
    assert any("cycle" in e.lower() for e in errors)


def test_workflow_engine_register() -> None:
    engine = WorkflowEngine()
    assert "feature-delivery" in engine.list_definitions()
    assert "bugfix" in engine.list_definitions()
    assert "code-review" in engine.list_definitions()


def test_workflow_engine_start() -> None:
    engine = WorkflowEngine()
    instance_id = engine.start("bugfix", {"task": "Fix login"})
    assert instance_id

    instance = engine.get_instance(instance_id)
    assert instance is not None
    assert instance.definition.name == "bugfix"
    assert instance.state == WorkflowState.CREATED


def test_workflow_pending_steps() -> None:
    engine = WorkflowEngine()
    instance_id = engine.start("bugfix")
    instance = engine.get_instance(instance_id)
    assert instance is not None

    ready = instance.pending_steps()
    assert len(ready) == 1
    assert ready[0] == "analyze"


def test_workflow_progress() -> None:
    engine = WorkflowEngine()
    instance_id = engine.start("bugfix")
    instance = engine.get_instance(instance_id)
    assert instance is not None

    progress = instance.progress()
    assert progress["total"] == 4
    assert progress["pending"] == 4
    assert progress["completed"] == 0
    assert progress["percent"] == 0


def test_workflow_approval_gate() -> None:
    wf = WorkflowDefinition(name="test-approval")
    wf.step("deploy", agent="devops", approval="human")

    engine = WorkflowEngine()
    engine.register(wf)
    instance_id = engine.start("test-approval")
    instance = engine.get_instance(instance_id)
    assert instance is not None
    assert "deploy" in instance.approvals_pending


def test_workflow_cancel() -> None:
    engine = WorkflowEngine()
    instance_id = engine.start("bugfix")
    assert engine.cancel(instance_id) is True
    instance = engine.get_instance(instance_id)
    assert instance is not None
    assert instance.state == WorkflowState.FAILED


def test_builtin_workflows_have_steps() -> None:
    for name, wf in BUILTIN_WORKFLOWS.items():
        assert len(wf.steps) > 0, f"Workflow {name} has no steps"
        assert wf.validate() == [], f"Workflow {name} has errors: {wf.validate()}"
