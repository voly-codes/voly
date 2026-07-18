"""CLI command: voly run."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click

from voly.executor.base import format_executor_failure, executor_failure_details


@click.command()
@click.argument("task", required=False)
@click.option("--agent", "-a", default=None, help="Force specific agent")
@click.option("--model", "-m", default=None, help="Force specific model")
@click.option(
    "--executor",
    "-e",
    default=None,
    help="Executor type: cursor, claude-code, mimo, opencode, deepseek, zen, wrangler, cf-containers",
)
@click.option("--cwd", default=None, help="Working directory for executor")
@click.option("--max-turns", default=30, help="Max agent turns (claude-code executor)")
@click.option(
    "--timeout", default=300, show_default=True,
    help="Executor timeout in seconds (total deadline, incl. internal model fallback)",
)
@click.option("--a2a-delegate", is_flag=True, help="Delegate to A2A agents")
@click.option(
    "--dry-run", is_flag=True,
    help="Run the executor but roll back all file changes afterwards (diff preview kept)",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def run(
    ctx: click.Context,
    task: str | None,
    agent: str | None,
    model: str | None,
    executor: str | None,
    cwd: str | None,
    max_turns: int,
    timeout: int,
    a2a_delegate: bool,
    dry_run: bool,
    output_json: bool,
) -> None:
    """Run a task through the VOLY pipeline."""
    if executor:
        _run_with_executor(
            task, executor, cwd, max_turns, timeout, output_json, ctx,
            model=model, dry_run=dry_run,
        )
        return
    if dry_run:
        click.echo("--dry-run applies to executor runs; ignored on the pipeline path", err=True)

    from voly.pipeline import Pipeline

    config = ctx.obj["config"]
    pipeline = Pipeline(config)
    pipeline.setup_environment()

    if not task:
        task = click.prompt("Task description")

    result = pipeline.run(
        task,
        # Same as the web route: --cwd reaches hybrid multi-agent via context.
        context={"cwd": cwd} if cwd else None,
        delegate_to_a2a=a2a_delegate,
        force_model=model,
        force_agent=agent,
    )

    pipeline.shutdown()

    if output_json:
        output: dict[str, Any] = {
            "success": result.success,
            "stage": result.stage.value,
            "duration_ms": result.duration_ms,
        }
        if result.route:
            output["agent"] = result.route.agent
            output["model"] = result.route.model
            output["provider"] = result.route.provider
        if result.response:
            output["content"] = result.response.content
            output["usage"] = {
                "input_tokens": result.response.usage.input_tokens,
                "output_tokens": result.response.usage.output_tokens,
            }
        if result.error:
            output["error"] = result.error
        assigns = _a2a_assignments(result)
        if assigns:
            output["a2a_assignments"] = assigns
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            if result.route:
                click.echo(f"Agent: {result.route.agent}")
                click.echo(f"Model:  {result.route.model} ({result.route.provider})")
            if result.response:
                click.echo(f"\n{result.response.content}")
            _echo_a2a_role_summary(result)
            click.echo(f"\n--- completed in {result.duration_ms:.0f}ms ---")
        else:
            if result.response and result.response.content:
                click.echo(f"\n{result.response.content}")
            _echo_a2a_role_summary(result)
            click.echo(f"Error: {result.error or 'pipeline failed (partial result)'}", err=True)
            sys.exit(1)


def _a2a_assignments(result: Any) -> list[dict[str, Any]]:
    ev = getattr(result, "event", None)
    raw = getattr(ev, "a2a_assignments", None) if ev is not None else None
    if not raw and ev is not None and isinstance(ev, dict):
        raw = ev.get("a2a_assignments")
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for a in raw:
        if isinstance(a, dict):
            out.append(a)
        elif hasattr(a, "to_event_dict"):
            out.append(a.to_event_dict())
    return out


def _echo_a2a_role_summary(result: Any) -> None:
    """Compact per-role mode / files / verify line after multi-agent runs."""
    assigns = _a2a_assignments(result)
    if not assigns:
        return
    click.echo("\nA2A roles:")
    for a in assigns:
        role = a.get("role", "?")
        ok = "ok" if a.get("ok") else "fail"
        mode = a.get("mode") or "chat"
        n_files = len(a.get("files_touched") or [])
        verify = a.get("plan_verify_ok")
        verify_s = (
            "verify=yes" if verify is True else "verify=no" if verify is False else "verify=—"
        )
        click.echo(f"  {role}: {ok} mode={mode} files={n_files} {verify_s}")


def _run_with_executor(
    task: str | None,
    executor_type: str,
    cwd: str | None,
    max_turns: int,
    timeout: int,
    output_json: bool,
    ctx: click.Context,
    *,
    model: str | None = None,
    dry_run: bool = False,
) -> None:
    from voly.runner.agent_runner import AgentRunner

    if not task:
        task = click.prompt("Task description")

    config = ctx.obj["config"]
    work_dir = cwd or os.getcwd()

    runner_inst = AgentRunner(config)
    try:
        result = runner_inst.run(
            task,
            executor_type,
            cwd=work_dir,
            max_turns=max_turns,
            timeout=timeout,
            model=model or "",
            dry_run=dry_run,
        )
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    if output_json:
        payload: dict = {
            "success": result.success,
            "executor": result.executor,
            "agent": result.agent,
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
            "budget_exceeded": result.budget_exceeded,
        }
        if not result.success:
            payload.update(executor_failure_details(result.result, executor_name=result.executor))
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo(f"Executor: {result.executor}  cwd: {work_dir}")
        click.echo(f"Task: {task[:80]}{'...' if len(task) > 80 else ''}\n")
        if result.success:
            if result.result.output:
                click.echo(result.result.output)
            click.echo(
                f"\n--- {result.executor} | {result.result.num_turns} turns | "
                f"${result.result.cost_usd:.4f} | {result.result.duration_ms:.0f}ms | "
                f"automation {result.automation_score:.0%} ---"
            )
        elif result.budget_exceeded:
            click.echo(f"Budget exceeded: ${result.result.cost_usd:.4f}", err=True)
        else:
            click.echo(
                f"Error: {format_executor_failure(result.result, executor_name=result.executor)}",
                err=True,
            )

    if not result.success:
        sys.exit(1)
