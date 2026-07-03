from __future__ import annotations

_ROLE_LABELS: dict[str, str] = {
    "developer": "Implementation",
    "reviewer": "Code Review",
    "tester": "Tests",
    "architect": "Architecture",
    "devops": "Deployment",
    "security": "Security Review",
}


class ResultMerger:
    def merge(self, task: str, a2a_tasks: list) -> str:
        sections: list[str] = []

        for a2a_task in a2a_tasks:
            agent = a2a_task.metadata.get("agent", "unknown")
            role_label = _ROLE_LABELS.get(agent, agent.title())
            header = f"## [{agent.title()}] {role_label}"

            if self._is_failed(a2a_task):
                content = f'(failed: {a2a_task.metadata.get("error", "unknown")})'
            else:
                content = self._extract_content(a2a_task)

            sections.append(f"{header}\n\n{content}")

        return "\n---\n".join(sections)

    def _is_failed(self, a2a_task) -> bool:
        state = a2a_task.state
        if hasattr(state, "value"):
            return state.value == "failed"
        return str(state) == "failed"

    def _extract_content(self, a2a_task) -> str:
        # A2ATask.result is a plain str (not artifacts/parts)
        result = getattr(a2a_task, "result", None)
        if result:
            return result
        return "(no output)"
