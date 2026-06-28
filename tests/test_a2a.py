"""Tests for A2A Orchestrator."""

from codeops.a2a import (
    AgentCard,
    AgentSkill,
    A2AClient,
    A2AOrchestrator,
    A2ATask,
    TaskState,
)


def test_agent_skill_serialization() -> None:
    skill = AgentSkill(
        id="code-review",
        name="Code Review",
        description="Reviews code for quality and security",
        tags=["code", "review", "quality"],
        examples=["Review this PR", "Check code quality"],
    )
    d = skill.to_dict()
    assert d["id"] == "code-review"
    assert d["name"] == "Code Review"
    assert len(d["tags"]) == 3

    restored = AgentSkill.from_dict(d)
    assert restored.id == skill.id
    assert restored.name == skill.name
    assert restored.tags == skill.tags


def test_agent_card_serialization() -> None:
    card = AgentCard(
        name="Code Reviewer",
        description="Expert code review agent",
        url="http://localhost:9001",
        version="1.0.0",
        skills=[
            AgentSkill(id="review", name="Review", description="Code review", tags=["review"]),
        ],
    )
    d = card.to_dict()
    restored = AgentCard.from_dict(d)
    assert restored.name == card.name
    assert restored.url == card.url
    assert len(restored.skills) == 1


def test_agent_card_match_task() -> None:
    card = AgentCard(
        name="Tester",
        description="Runs tests",
        url="http://localhost:9002",
        skills=[
            AgentSkill(
                id="unit-test",
                name="Unit Testing",
                description="Writes and runs unit tests",
                tags=["test", "unittest"],
                examples=["Write unit tests for module"],
            ),
            AgentSkill(
                id="integration-test",
                name="Integration Testing",
                description="Writes integration tests",
                tags=["test", "integration"],
                examples=["Write integration tests for API"],
            ),
        ],
    )
    matches = card.match_task("Write unit tests for auth module")
    assert len(matches) > 0
    assert matches[0][0].id == "unit-test"
    assert matches[0][1] > 0.3

    no_match = card.match_task("Сделай что-то не связанное с тестами")
    assert len(no_match) == 0


def test_a2a_orchestrator_create_task() -> None:
    orch = A2AOrchestrator()
    task = orch.create_task(
        title="Fix auth bug",
        description="Fix authentication bug in login handler",
    )
    assert task.id
    assert task.title == "Fix auth bug"
    assert task.state == TaskState.SUBMITTED


def test_a2a_orchestrator_register_local() -> None:
    orch = A2AOrchestrator()
    card = AgentCard(
        name="Local Reviewer",
        description="Local review agent",
        url="http://localhost:9100/a2a/reviewer",
        skills=[AgentSkill(id="review", name="Review", description="Code review", tags=["review"])],
    )

    from codeops.a2a import A2AAgent

    agent = A2AAgent(card)
    orch.register_local_agent(agent)

    agents = orch.client._known_agents
    assert card.url in agents


def test_a2a_task_lifecycle() -> None:
    task = A2ATask(id="task-1", title="Test", description="Test task", agent_url="http://localhost:9001")
    assert task.state == TaskState.SUBMITTED
    assert task.created_at > 0

    task.state = TaskState.WORKING
    assert task.state == TaskState.WORKING

    task.state = TaskState.COMPLETED
    assert task.state == TaskState.COMPLETED


def test_a2a_orchestrator_no_agents() -> None:
    orch = A2AOrchestrator()
    task = orch.create_task(title="Unknown task", description="Something no agent can do")
    result = orch.route_and_delegate(task)
    assert result.state == TaskState.FAILED
    assert "No suitable agent" in result.error
