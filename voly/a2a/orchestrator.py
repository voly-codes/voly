"""A2A клиент и оркестратор: обнаружение агентов, делегирование задач, workflows."""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error
import uuid
from typing import Any

from voly.a2a.protocol import A2AAgent, A2ATask, AgentCard, AgentSkill, TaskState

logger = logging.getLogger(__name__)


class A2AClient:
    def __init__(self, base_url: str | None = None, token: str = ""):
        self.base_url = base_url
        self.token = token
        self._known_agents: dict[str, AgentCard] = {}

    def discover(self, agent_url: str) -> AgentCard | None:
        if agent_url in self._known_agents:
            return self._known_agents[agent_url]

        try:
            card_url = agent_url.rstrip("/") + "/.well-known/agent-card.json"
            req = urllib.request.Request(card_url)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode())
                card = AgentCard.from_dict(data)
                self._known_agents[agent_url] = card
                return card
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            return None

    def register(self, card: AgentCard) -> None:
        self._known_agents[card.url] = card

    def find_agent_for_task(self, task: str) -> list[tuple[AgentCard, AgentSkill, float]]:
        results: list[tuple[AgentCard, AgentSkill, float]] = []
        for card in self._known_agents.values():
            matches = card.match_task(task)
            for skill, score in matches:
                results.append((card, skill, score))
        return sorted(results, key=lambda x: x[2], reverse=True)

    def send_task(self, agent_url: str, task: A2ATask) -> A2ATask:
        try:
            api_url = agent_url.rstrip("/") + "/tasks"
            body = {
                "jsonrpc": "2.0",
                "id": task.id,
                "method": "tasks/send",
                "params": {
                    "task": {
                        "id": task.id,
                        "title": task.title,
                        "description": task.description,
                    }
                },
            }
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            req = urllib.request.Request(
                api_url,
                data=json.dumps(body).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode())
                if "result" in data:
                    task.state = TaskState(data["result"].get("state", "working"))
                else:
                    task.state = TaskState.WORKING
                task.updated_at = time.time()
                return task
        except urllib.error.URLError as e:
            task.state = TaskState.FAILED
            task.error = str(e)
            task.updated_at = time.time()
            return task

    def get_task_status(self, agent_url: str, task_id: str) -> A2ATask | None:
        try:
            api_url = f"{agent_url.rstrip('/')}/tasks/{task_id}"
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode())
                state_str = data.get("state", "completed")
                result = data.get("result", "")
                task = A2ATask(id=task_id, agent_url=agent_url)
                try:
                    task.state = TaskState(state_str)
                except ValueError:
                    task.state = TaskState.COMPLETED
                task.result = result
                task.updated_at = time.time()
                return task
        except urllib.error.URLError:
            return None


class A2AOrchestrator:
    def __init__(self, client: A2AClient | None = None, federation: Any | None = None, token: str = ""):
        self.client = client or A2AClient(token=token)
        self._federation = federation
        self._local_agents: dict[str, A2AAgent] = {}
        self._tasks: dict[str, A2ATask] = {}
        if self._federation:
            for card in self._federation.sync_agents():
                self.client.register(card)

    def register_local_agent(self, agent: A2AAgent) -> None:
        self._local_agents[agent.card.name] = agent
        self.client.register(agent.card)
        if self._federation:
            self._federation.register_agent_card(agent.card)

    def register_remote_agent(self, url: str) -> AgentCard | None:
        return self.client.discover(url)

    def refresh_federation(self) -> list[AgentCard]:
        if not self._federation:
            return []
        cards = self._federation.sync_agents()
        for card in cards:
            self.client.register(card)
        return cards

    def create_task(
        self, title: str, description: str, agent_name: str | None = None
    ) -> A2ATask:
        if self._federation and agent_name:
            task = self._federation.create_remote_task(
                title,
                description,
                agent_name=agent_name,
            )
            self._tasks[task.id] = task
            return task

        task = A2ATask(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            state=TaskState.SUBMITTED,
            agent_url=agent_name or "",
        )
        self._tasks[task.id] = task
        return task

    def route_and_delegate(self, task: A2ATask) -> A2ATask:
        logger.debug("route_and_delegate: task_id=%s agent=%s has_federation=%s",
                     task.id, task.metadata.get("agent"), bool(self._federation))
        if self._federation:
            agent_name = task.metadata.get("routed_to") or task.agent_url
            if not agent_name:
                agent_name = task.metadata.get("agent", "")
            logger.debug("route_and_delegate: federation path, agent_name=%r", agent_name)
            if agent_name and not task.metadata.get("routed_to"):
                candidates = self.client.find_agent_for_task(task.description)
                if candidates:
                    card, skill, score = candidates[0]
                    agent_name = card.name
                    task.metadata["routed_to"] = card.name
                    task.metadata["routed_skill"] = skill.name
                    task.metadata["routing_score"] = score
                    task.agent_url = card.url

            if agent_name:
                try:
                    remote = self._federation.create_remote_task(
                        task.title or task.description[:100],
                        task.description,
                        agent_name=str(agent_name),
                    )
                    logger.debug("route_and_delegate: federation created task_id=%s state=%s", remote.id, remote.state)
                    task.id = remote.id
                    task.state = remote.state
                    task.metadata.update(remote.metadata)
                    task.agent_url = remote.agent_url
                    self._tasks[task.id] = task
                except Exception as exc:
                    logger.error("route_and_delegate: federation.create_remote_task failed: %s", exc)
                    task.state = TaskState.FAILED
                    task.error = str(exc)
                return task

        candidates = self.client.find_agent_for_task(task.description)
        if not candidates:
            logger.warning("route_and_delegate: no agent candidates for task_id=%s", task.id)
            task.state = TaskState.FAILED
            task.error = "No suitable agent found for task"
            return task

        card, skill, score = candidates[0]
        task.metadata["routed_to"] = card.name
        task.metadata["routed_skill"] = skill.name
        task.metadata["routing_score"] = score
        task.agent_url = card.url

        if card.name in self._local_agents:
            task.state = TaskState.WORKING
            task.updated_at = time.time()
            return task

        task = self.client.send_task(card.url, task)
        self._tasks[task.id] = task
        return task

    def collect_results(self, task: A2ATask) -> A2ATask:
        if task.state in (TaskState.COMPLETED, TaskState.FAILED):
            return task

        if self._federation:
            updated = self._federation.load_task(task.id)
            if updated:
                self._tasks[task.id] = updated
                return updated
            return task

        if not task.agent_url:
            return task

        updated = self.client.get_task_status(task.agent_url, task.id)
        if updated:
            self._tasks[task.id] = updated
            return updated
        return task

    def dispatch_parallel(self, subtasks: list, timeout_seconds: float = 120.0) -> list:
        '''
        Dispatch subtasks to A2A agents, respecting depends_on ordering.
        Runs independent subtasks in parallel per wave; injects prior wave
        results into dependent subtask descriptions before dispatch.
        Returns list of A2ATask objects in the same order as subtasks.
        '''
        from voly.a2a.decomposer import Subtask, TaskDecomposer

        results: list[A2ATask | None] = [None] * len(subtasks)
        decomposer = TaskDecomposer()
        terminal = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}

        def run_subtask(i: int, subtask: Subtask) -> None:
            logger.info("dispatch_parallel[%d]: agent=%s", i, subtask.agent)
            try:
                a2a_task = self.create_task(
                    title=subtask.agent + ': ' + subtask.description[:80],
                    description=subtask.description,
                )
                a2a_task.metadata['agent'] = subtask.agent
                self.route_and_delegate(a2a_task)
                logger.info("dispatch_parallel[%d]: agent=%s → state=%s id=%s",
                            i, subtask.agent, a2a_task.state, a2a_task.id)
                results[i] = a2a_task
            except Exception as e:
                logger.error("dispatch_parallel[%d]: agent=%s exception: %s", i, subtask.agent, e, exc_info=True)
                a2a_task = self.create_task(title=subtask.agent, description=subtask.description)
                a2a_task.metadata['agent'] = subtask.agent
                a2a_task.metadata['error'] = str(e)
                a2a_task.state = TaskState.FAILED
                results[i] = a2a_task

        def _task_result(task: A2ATask | None) -> str:
            if not task:
                return ""
            return (task.result or task.metadata.get("partial_result") or "").strip()

        def _wait_wave(indices: list[int], deadline: float) -> None:
            while time.monotonic() < deadline:
                pending = [
                    i for i in indices
                    if results[i] is not None and results[i].state not in terminal
                ]
                if not pending:
                    return
                for i in pending:
                    results[i] = self.collect_results(results[i])  # type: ignore[arg-type]
                time.sleep(2.0)

        levels = self._dependency_levels(subtasks)
        wave_deadline = time.monotonic() + timeout_seconds

        for level_indices in levels:
            wave_items: list[tuple[int, Subtask]] = []
            for i in level_indices:
                subtask = subtasks[i]
                prior: list[tuple[str, str]] = []
                for dep_idx in subtask.depends_on:
                    dep_task = results[dep_idx]
                    dep_agent = subtasks[dep_idx].agent
                    prior.append((dep_agent, _task_result(dep_task)))
                if subtask.agent in decomposer.CONTEXT_AGENTS or subtask.depends_on:
                    desc = decomposer.inject_prior_context(subtask.description, prior)
                else:
                    desc = subtask.description
                wave_items.append((i, Subtask(desc, subtask.agent, subtask.depends_on)))

            threads = [
                threading.Thread(target=run_subtask, args=(i, sub))
                for i, sub in wave_items
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=max(0.0, wave_deadline - time.monotonic()))

            _wait_wave(level_indices, wave_deadline)

        return [r for r in results if r is not None]

    @staticmethod
    def _dependency_levels(subtasks: list) -> list[list[int]]:
        """Group subtask indices into waves by dependency depth."""
        depths: list[int] = []
        for i, sub in enumerate(subtasks):
            if not sub.depends_on:
                depths.append(0)
            else:
                depths.append(1 + max(depths[d] for d in sub.depends_on if d < i))
        if not depths:
            return []
        max_depth = max(depths)
        return [
            [i for i, d in enumerate(depths) if d == level]
            for level in range(max_depth + 1)
        ]

    def execute_workflow(self, tasks: list[A2ATask], parallel: bool = False) -> list[A2ATask]:
        results: list[A2ATask] = []

        if parallel:
            threads: list[threading.Thread] = []
            for task in tasks:
                t = threading.Thread(target=lambda: self.route_and_delegate(task))
                threads.append(t)
                t.start()
            for t in threads:
                t.join(timeout=120)
            for task in tasks:
                results.append(self.collect_results(task))
        else:
            for task in tasks:
                self.route_and_delegate(task)
                results.append(self.collect_results(task))

        return results

    def list_agents(self) -> list[AgentCard]:
        if self._federation:
            self.refresh_federation()
        return list(self.client._known_agents.values())


def create_a2a_orchestrator(federation_url: str = "", token: str = "") -> A2AOrchestrator:
    from voly.a2a.backend import FederationBackend
    from voly.a2a.federation import create_federation_client

    fed_client = create_federation_client(federation_url, token=token)
    a2a_client = A2AClient(token=token)
    if fed_client:
        return A2AOrchestrator(a2a_client, federation=FederationBackend(fed_client))
    return A2AOrchestrator(a2a_client)
