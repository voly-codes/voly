"""CLI: explicit bounded agent workflows."""

from __future__ import annotations

import json
import os

import click


@click.group("workflow")
def workflow_cmd() -> None:
    """Run bounded multi-agent workflows."""


@workflow_cmd.command("stats")
@click.option("--limit", default=10, show_default=True, type=click.IntRange(1, 200))
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def workflow_stats(ctx: click.Context, limit: int, output_json: bool) -> None:
    """Summarize completed review workflows for a guarded rollout."""
    from collections import Counter

    from voly.runtime.runs import RUNNING, RunTracker

    config = ctx.obj["config"]
    records = [
        rec for rec in RunTracker(config.telemetry.runs_dir).list()
        if (
            rec.workflow == "review-until-clean"
            and rec.status != RUNNING
            and rec.workflow_metrics
        )
    ][:limit]
    metrics = [rec.workflow_metrics for rec in records]
    count = len(metrics)
    stops = Counter(str(item.get("stop_reason") or "unknown") for item in metrics)
    payload = {
        "workflow": "review-until-clean",
        "sample_size": count,
        "verified": sum(bool(item.get("verified_completion")) for item in metrics),
        "verified_rate": round(
            (
                sum(bool(item.get("verified_completion")) for item in metrics) / count
                if count else 0.0
            ),
            3,
        ),
        "manual_interventions": sum(
            int(item.get("manual_interventions") or 0) for item in metrics
        ),
        "average_laps": round(
            (
                sum(int(item.get("laps") or 0) for item in metrics) / count
                if count else 0.0
            ),
            2,
        ),
        "total_cost_usd": round(
            sum(float(item.get("cost_usd") or 0.0) for item in metrics), 6
        ),
        "average_duration_ms": round(
            (
                sum(float(item.get("duration_ms") or 0.0) for item in metrics) / count
                if count else 0.0
            ),
            1,
        ),
        "stop_reasons": dict(sorted(stops.items())),
    }
    if output_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(f"workflow:             {payload['workflow']}")
    click.echo(f"sample:               {payload['sample_size']}/{limit}")
    click.echo(f"verified:             {payload['verified']} ({payload['verified_rate']:.1%})")
    click.echo(f"manual interventions: {payload['manual_interventions']}")
    click.echo(f"average laps:          {payload['average_laps']:.2f}")
    click.echo(f"total cost:            ${payload['total_cost_usd']:.6f}")
    click.echo(f"average duration:      {payload['average_duration_ms']:.1f}ms")
    click.echo(f"stop reasons:          {payload['stop_reasons']}")


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
