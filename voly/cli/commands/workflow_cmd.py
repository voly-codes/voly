"""CLI: explicit bounded agent workflows."""

from __future__ import annotations

import json
import os

import click


@click.group("workflow")
def workflow_cmd() -> None:
    """Run bounded multi-agent workflows."""


@workflow_cmd.command("validate")
@click.argument("workflow_file", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def workflow_validate(ctx: click.Context, workflow_file: str) -> None:
    """Validate a Workflow YAML/JSON definition (docs/proposals/agent-workflow-sdk.md
    Phase 5) without running it. Distinct from ``voly plan validate``, which
    validates an already-compiled Plan/PlanStep document."""
    from voly.sdk.loader import load_workflow_file
    from voly.sdk.workflow import WorkflowError

    config = ctx.obj["config"]
    try:
        workflow, task, _cwd = load_workflow_file(workflow_file, config=config)
        plan = workflow.compile(task)
    except WorkflowError as exc:
        click.echo(f"invalid: {exc}", err=True)
        raise SystemExit(1) from exc
    order = [s.id for s in plan.steps]
    click.echo(f"ok: {workflow.name}  nodes={len(plan.steps)}  order={order}")


@workflow_cmd.command("run")
@click.argument("workflow_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--task", default=None, help="Override the document's task")
@click.option("--cwd", default=None, help="Override the document's cwd")
@click.option(
    "--mode",
    type=click.Choice(["shadow", "active"], case_sensitive=False),
    default=None,
    help="Workflow.run() mode (default: active)",
)
@click.option("--timeout-seconds", "timeout_seconds", default=None, type=float)
@click.option("--json-out", "json_out", is_flag=True, help="Print result summary as JSON")
@click.pass_context
def workflow_run(
    ctx: click.Context,
    workflow_file: str,
    task: str | None,
    cwd: str | None,
    mode: str | None,
    timeout_seconds: float | None,
    json_out: bool,
) -> None:
    """Load a Workflow YAML/JSON definition, compile it and run it through
    PlanRunner. See ``voly plan run`` for running an already-compiled Plan
    document directly."""
    from voly.sdk.loader import load_workflow_file
    from voly.sdk.workflow import WorkflowError

    config = ctx.obj["config"]
    try:
        workflow, doc_task, doc_cwd = load_workflow_file(workflow_file, config=config)
    except WorkflowError as exc:
        click.echo(f"Failed to load workflow: {exc}", err=True)
        raise SystemExit(2) from exc

    try:
        result = workflow.run(
            task if task is not None else doc_task,
            cwd=cwd if cwd is not None else doc_cwd,
            mode=mode,
            timeout_seconds=timeout_seconds,
        )
    except WorkflowError as exc:
        click.echo(f"Failed to run workflow: {exc}", err=True)
        raise SystemExit(2) from exc

    _print_workflow_result(result, json_out=json_out)
    raise SystemExit(0 if result.success else 1)


@workflow_cmd.command("resume")
@click.argument("plan_id")
@click.option(
    "--mode",
    type=click.Choice(["shadow", "active"], case_sensitive=False),
    default=None,
)
@click.option("--timeout-seconds", "timeout_seconds", default=None, type=float)
@click.option("--json-out", "json_out", is_flag=True)
@click.pass_context
def workflow_resume(
    ctx: click.Context,
    plan_id: str,
    mode: str | None,
    timeout_seconds: float | None,
    json_out: bool,
) -> None:
    """Continue a previously run Workflow's persisted Plan by its plan_id —
    e.g. after an approval node was decided via ``voly decide``, or after a
    process restart recovers a stale-running step."""
    from voly.plan.runner import PlanRunner
    from voly.plan.types import VERIFIED
    from voly.sdk.workflow import NodeResult, WorkflowResult

    config = ctx.obj["config"]
    runner = PlanRunner(config, emit_event=False)
    plan_result = runner.resume(plan_id, mode=mode, timeout_seconds=timeout_seconds)
    node_results = [
        NodeResult(
            node_id=s.id, status=s.status, success=s.status == VERIFIED,
            output=s.output, error=s.error, cost_usd=s.cost_usd,
            duration_ms=s.duration_ms, files_touched=list(s.files_touched),
        )
        for s in plan_result.plan.steps
    ]
    result = WorkflowResult(
        plan=plan_result.plan,
        success=plan_result.success,
        status=plan_result.plan.status,
        node_results=node_results,
        cost_usd=round(sum(n.cost_usd for n in node_results), 6),
        duration_ms=plan_result.duration_ms,
        error=plan_result.error,
    )
    _print_workflow_result(result, json_out=json_out)
    raise SystemExit(0 if result.success else 1)


@workflow_cmd.command("show")
@click.argument("plan_id")
@click.option("--json-out", "json_out", is_flag=True)
@click.pass_context
def workflow_show(ctx: click.Context, plan_id: str, json_out: bool) -> None:
    """Show a stored Workflow-compiled Plan, including per-node cost and
    duration (``voly plan show`` prints status/deps/acceptance only)."""
    from voly.plan.store import PlanStore

    config = ctx.obj["config"]
    store = PlanStore(getattr(config.plan, "store_dir", ".voly/plans"))
    plan = store.load(plan_id)
    if plan is None:
        click.echo(f"No plan {plan_id!r}", err=True)
        raise SystemExit(1)
    if json_out:
        click.echo(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(f"workflow: {plan.metadata.get('workflow_name', '—')}")
    click.echo(f"plan_id:  {plan.plan_id}")
    click.echo(f"status:   {plan.status}")
    click.echo(f"cwd:      {plan.cwd or '—'}")
    total_cost = sum(s.cost_usd for s in plan.steps)
    click.echo(f"cost:     ${total_cost:.6f}")
    click.echo("nodes:")
    for s in plan.steps:
        click.echo(
            f"  - {s.id}: status={s.status} role={s.role} "
            f"cost=${s.cost_usd:.6f} duration={s.duration_ms:.0f}ms "
            f"deps={s.depends_on or []}"
        )
        if s.error:
            click.echo(f"      error: {s.error[:160]}")


def _print_workflow_result(result, *, json_out: bool) -> None:
    if json_out:
        payload = {
            "plan_id": result.plan.plan_id,
            "success": result.success,
            "status": result.status,
            "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms,
            "error": result.error,
            "nodes": [
                {
                    "node_id": n.node_id, "status": n.status, "success": n.success,
                    "cost_usd": n.cost_usd, "duration_ms": n.duration_ms,
                    "error": n.error,
                }
                for n in result.node_results
            ],
        }
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(f"plan_id:  {result.plan.plan_id}")
    click.echo(f"status:   {result.status}")
    click.echo(f"cost:     ${result.cost_usd:.6f}")
    click.echo(f"duration: {result.duration_ms:.0f}ms")
    for n in result.node_results:
        mark = {"verified": "✓", "failed": "✗", "verifying": "…", "pending": " "}.get(n.status, "?")
        click.echo(f"  [{mark}] {n.node_id:<16} {n.status:<10} ${n.cost_usd:.6f}")
        if n.error:
            click.echo(f"       error: {n.error[:160]}")
    if result.error:
        click.echo(f"error:    {result.error}")


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
