"""CLI: explicit bounded agent workflows."""

from __future__ import annotations

import json
import os

import click


@click.group("workflow")
def workflow_cmd() -> None:
    """Run bounded multi-agent workflows."""


@workflow_cmd.command("review-until-clean")
@click.argument("task", required=False)
@click.option("--cwd", required=True, type=click.Path(file_okay=False))
@click.option("--executor", default="claude-code", show_default=True)
@click.option("--max-rounds", default=3, show_default=True, type=click.IntRange(1, 20))
@click.option("--deadline", "deadline_seconds", default=900.0, show_default=True, type=float)
@click.option("--timeout", "executor_timeout", default=300, show_default=True, type=int)
@click.option("--max-turns", default=30, show_default=True, type=int)
@click.option("--reviewer-model", default="")
@click.option("--reviewer-provider", default="")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def review_until_clean_cmd(
    ctx: click.Context,
    task: str | None,
    cwd: str,
    executor: str,
    max_rounds: int,
    deadline_seconds: float,
    executor_timeout: int,
    max_turns: int,
    reviewer_model: str,
    reviewer_provider: str,
    output_json: bool,
) -> None:
    """Repair and independently review a coding task until clean or bounded stop."""
    if not task:
        task = click.prompt("Task description")
    result = _execute_review(
        ctx.obj["config"],
        task,
        cwd=os.path.abspath(os.path.expanduser(cwd)),
        executor=executor,
        max_rounds=max_rounds,
        deadline_seconds=deadline_seconds,
        executor_timeout=executor_timeout,
        max_turns=max_turns,
        reviewer_model=reviewer_model,
        reviewer_provider=reviewer_provider,
    )
    payload = result.to_dict()
    if output_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo(f"workflow:    {payload['workflow']}")
        click.echo(f"task_id:     {payload['task_id']}")
        click.echo(f"stop_reason: {payload['stop_reason']}")
        click.echo(f"laps:        {len(payload['laps'])}/{max_rounds}")
        click.echo(f"cost:        ${payload['total_cost_usd']:.6f}")
        for lap in payload["laps"]:
            click.echo(
                f"  lap {lap['number']}: {lap['developer_executor']} -> reviewer "
                f"verdict={lap['verdict'] or 'error'} files={len(lap['files_touched'])}"
            )
        if payload["error"]:
            click.echo(f"error:       {payload['error']}", err=True)
    if not result.success:
        raise click.exceptions.Exit(1)


def _execute_review(config, task: str, **kwargs):
    from voly.pipeline import Pipeline
    from voly.runner.agent_runner import AgentRunner
    from voly.runtime.runs import RunTracker
    from voly.telemetry import new_task_id
    from voly.workflow import ReviewUntilClean

    pipeline = Pipeline(config)
    try:
        workflow = ReviewUntilClean(
            runner=AgentRunner(config),
            gateway=pipeline.gateway,
        )
        return workflow.run(
            task,
            tracker=RunTracker(config.telemetry.runs_dir),
            workflow_id=new_task_id(),
            **kwargs,
        )
    finally:
        pipeline.shutdown()
