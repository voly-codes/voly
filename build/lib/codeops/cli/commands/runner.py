"""Agent Runner CLI — codeops runner <agent> \"task\"."""
from __future__ import annotations

import json
import os
import sys

import click

from codeops.runner.agent_runner import AgentRunner, EXECUTOR_NAMES, resolve_executor


@click.command("runner")
@click.argument("agent")
@click.argument("task", required=False)
@click.option("--cwd", default=None, help="Working directory for the agent")
@click.option("--max-turns", default=30, show_default=True, help="Max agent turns")
@click.option("--timeout", default=300, show_default=True, help="Timeout in seconds")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def runner(
    ctx: click.Context,
    agent: str,
    task: str | None,
    cwd: str | None,
    max_turns: int,
    timeout: int,
    output_json: bool,
) -> None:
    """Run an IDE agent with budget control, RTK, and telemetry.

    AGENT can be an executor (cursor, claude-code, opencode) or a role
    (developer, architect, reviewer) — resolved via config/registry.

    Examples:

      codeops runner cursor "migrate buttons to shared component"

      codeops runner developer "fix login bug" --cwd /path/to/project

      codeops runner claude-code "refactor api.ts"

      codeops runner opencode "add unit tests"
    """
    config = ctx.obj["config"]
    if not task:
        task = click.prompt("Task description")

    work_dir = cwd or os.getcwd()
    executor_name, agent_role = resolve_executor(agent, config)

    if not output_json:
        click.echo(f"Agent:   {agent_role}")
        click.echo(f"Executor: {executor_name}")
        click.echo(f"cwd:     {work_dir}")
        if config.cost_policy.enabled:
            click.echo(f"Budget:  ${config.cost_policy.max_task_cost_usd:.2f} per task")
        click.echo(f"Task:    {task[:80]}{'...' if len(task) > 80 else ''}\n")

    runner_inst = AgentRunner(config)
    try:
        result = runner_inst.run(
            task,
            agent,
            cwd=work_dir,
            max_turns=max_turns,
            timeout=timeout,
        )
    except ValueError as exc:
        valid_exec = ", ".join(sorted(EXECUTOR_NAMES))
        click.echo(f"{exc}\nExecutors: {valid_exec}", err=True)
        sys.exit(1)

    if output_json:
        click.echo(json.dumps({
            "success": result.success,
            "agent": result.agent,
            "executor": result.executor,
            "task_id": result.task_id,
            "output": result.result.output,
            "error": result.result.error,
            "cost_usd": result.result.cost_usd,
            "input_tokens": result.result.input_tokens,
            "output_tokens": result.result.output_tokens,
            "duration_ms": result.result.duration_ms,
            "num_turns": result.result.num_turns,
            "automation_score": result.automation_score,
            "manual_steps_removed": result.manual_steps_removed,
            "task_type": result.task_type,
            "budget_exceeded": result.budget_exceeded,
        }, ensure_ascii=False, indent=2))
        if not result.success:
            sys.exit(1)
        return

    if result.success:
        if result.result.output:
            click.echo(result.result.output)
        click.echo(
            f"\n--- {result.executor} | {result.result.num_turns} turns | "
            f"${result.result.cost_usd:.4f} | {result.result.duration_ms:.0f}ms | "
            f"automation {result.automation_score:.0%} | "
            f"-{result.manual_steps_removed} manual steps ---"
        )
    else:
        if result.budget_exceeded:
            click.echo(
                f"Budget exceeded: ${result.result.cost_usd:.4f} > "
                f"${config.cost_policy.max_task_cost_usd:.2f}",
                err=True,
            )
        else:
            click.echo(f"Error: {result.result.error}", err=True)
        sys.exit(1)
