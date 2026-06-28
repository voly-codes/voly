"""
DSPy CLI — manage DSPy optimizer programs, datasets, and evaluation.

Commands:
    codeops dspy status                     Show DSPy config and program inventory
    codeops dspy dataset build              Build JSONL dataset from telemetry events
    codeops dspy compile --agent reviewer   Compile optimized program for an agent
    codeops dspy eval --agent reviewer      Evaluate compiled program on dataset
    codeops dspy promote reviewer.v2        Promote a compiled program version to active
    codeops dspy programs                   List all saved programs
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.group("dspy")
def dspy_cmd() -> None:
    """DSPy optimizer — compile, evaluate and promote agent programs."""
    pass


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@dspy_cmd.command("status")
@click.pass_context
def dspy_status(ctx: click.Context) -> None:
    """Show DSPy configuration and saved program inventory."""
    config = ctx.obj["config"]
    cfg = config.dspy

    click.echo("DSPy Optimizer")
    click.echo("=" * 50)
    click.echo(f"  enabled:        {cfg.enabled}")
    click.echo(f"  mode:           {cfg.mode}  (off | shadow | active)")
    click.echo(f"  routing_mode:   {cfg.routing_mode}")
    click.echo(f"  optimizer:      {cfg.optimizer}")
    click.echo(f"  compile_budget: {cfg.compile_budget}")
    click.echo(f"  min_examples:   {cfg.min_examples}")
    click.echo(f"  agents:         {cfg.agents or '(all)'}")
    click.echo(f"  programs_dir:   {cfg.programs_dir}")
    click.echo(f"  datasets_dir:   {cfg.datasets_dir}")
    click.echo(f"  active_tag:     {cfg.active_tag}")
    click.echo(f"  shadow_tag:     {cfg.shadow_tag}")
    if cfg.program_overrides:
        click.echo("  program_overrides:")
        for agent, program_id in cfg.program_overrides.items():
            click.echo(f"    {agent}: {program_id}")

    # Check dspy availability
    try:
        import dspy
        click.echo(f"\n  dspy package:   installed (version {getattr(dspy, '__version__', '?')})")
    except ImportError:
        click.echo("\n  dspy package:   NOT installed")
        click.echo("  Install with:   pip install codeops[dspy]  or  pip install dspy>=2.5.0")

    # List programs
    try:
        from codeops.dspy.store import DSPyProgramStore
        from codeops.dspy.versioning import ProgramVersionManager
        from codeops.dspy.programs import get_registry

        store = DSPyProgramStore(cfg.programs_dir)
        version_mgr = ProgramVersionManager(cfg.programs_dir)
        registry = get_registry()
        index = version_mgr.list_programs()
        programs = store.list_programs()
        if programs:
            click.echo("\nCompiled Programs:")
            for program_id, versions in sorted(programs.items()):
                latest = max(versions)
                tags = index.get(program_id, {}).get("tags", {})
                tags_str = ", ".join(f"{tag}→v{ver}" for tag, ver in sorted(tags.items())) or "-"
                definition = registry.get(program_id)
                agents = ",".join(definition.agents) if definition else "?"
                click.echo(
                    f"  {program_id:24s}  agents=[{agents}]  versions={versions}  latest=v{latest}  tags={tags_str}"
                )
        else:
            click.echo("\nCompiled Programs: (none)")
    except Exception as exc:
        click.echo(f"\nCould not read programs: {exc}")

    # Datasets
    ds_path = Path(cfg.datasets_dir)
    if ds_path.exists():
        files = list(ds_path.glob("*.jsonl"))
        click.echo(f"\nDatasets ({len(files)}):")
        for f in sorted(files):
            lines = sum(1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#"))
            click.echo(f"  {f.stem:20s}  {lines} examples")
    else:
        click.echo("\nDatasets: (none — run `codeops dspy dataset build` first)")


# ---------------------------------------------------------------------------
# dataset build
# ---------------------------------------------------------------------------

@dspy_cmd.group("dataset")
def dspy_dataset() -> None:
    """Manage DSPy training datasets."""
    pass


@dspy_dataset.command("build")
@click.option("--agent", "-a", default=None, help="Build dataset for a specific agent (default: all)")
@click.option("--from-events", default=None, help="Events directory (default: from config)")
@click.option("--min-score", default=0.5, type=float, show_default=True,
              help="Minimum routing_score to include in dataset")
@click.pass_context
def dataset_build(ctx: click.Context, agent: str | None, from_events: str | None, min_score: float) -> None:
    """Build JSONL training datasets from CodeOps telemetry events."""
    config = ctx.obj["config"]
    cfg = config.dspy

    events_dir = from_events or config.telemetry.events_dir
    datasets_dir = Path(cfg.datasets_dir)
    datasets_dir.mkdir(parents=True, exist_ok=True)

    from codeops.telemetry import load_events

    events = load_events(events_dir)
    if not events:
        raise click.ClickException(f"No events found in {events_dir}")

    click.echo(f"Loaded {len(events)} events from {events_dir}")

    # Group events by agent
    by_agent: dict[str, list] = {}
    for ev in events:
        if ev.status not in ("completed",):
            continue
        if ev.routing_score < min_score:
            continue
        a = ev.agent
        by_agent.setdefault(a, []).append(ev)

    agents_to_build = [agent] if agent else list(by_agent.keys())

    for ag in agents_to_build:
        ag_events = by_agent.get(ag, [])
        if not ag_events:
            click.echo(f"  {ag:20s}  0 examples (skipped)")
            continue

        out_path = datasets_dir / f"{ag}.jsonl"
        records = []
        for ev in ag_events:
            record: dict = {
                "task": ev.error or f"Task by {ev.agent}",  # placeholder
                "agent": ev.agent,
                "model": ev.model,
                "provider": ev.provider,
                "cost_usd": ev.cost_usd,
                "duration_ms": ev.duration_ms,
                "routing_score": ev.routing_score,
                "status": ev.status,
                "task_type": ev.task_type or "",
            }
            # Infer complexity from routing_score
            if ev.routing_score >= 0.8:
                record["complexity"] = "high"
            elif ev.routing_score >= 0.5:
                record["complexity"] = "medium"
            else:
                record["complexity"] = "low"

            records.append(record)

        out_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )
        click.echo(f"  {ag:20s}  {len(records)} examples → {out_path}")

    click.echo(f"\nDone. Run `codeops dspy compile --agent <agent>` to compile programs.")


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------

@dspy_cmd.command("compile")
@click.option("--agent", "-a", required=True, help="Agent or program id to compile")
@click.option("--optimizer", default=None, help="Override optimizer from config")
@click.option("--budget", default=None, type=click.Choice(["small", "medium", "large"]),
              help="Override compile budget from config")
@click.pass_context
def dspy_compile(ctx: click.Context, agent: str, optimizer: str | None, budget: str | None) -> None:
    """Compile an optimized DSPy program for an agent."""
    config = ctx.obj["config"]
    cfg = config.dspy

    if not cfg.enabled:
        raise click.ClickException(
            "DSPy is disabled in config. Set dspy.enabled: true in codeops.yaml"
        )

    try:
        import dspy as _dspy  # noqa: F401
    except ImportError:
        raise click.ClickException(
            "DSPy is not installed. Run: pip install codeops[dspy]  "
            "or: pip install 'dspy>=2.5.0'"
        )

    _optimizer = optimizer or cfg.optimizer
    _budget = budget or cfg.compile_budget
    _min_examples = cfg.min_examples

    from codeops.dspy.programs import get_registry
    from codeops.dspy.versioning import ProgramVersionManager, ProgramVersionRecord

    registry = get_registry()
    program_def = registry.get(agent) or registry.get_primary(agent)
    if not program_def:
        raise click.ClickException(f"Unknown agent or program id: {agent}")

    program_id = program_def.program_id
    dataset_id = program_def.primary_agent

    click.echo(f"Compiling DSPy program: {program_id}")
    click.echo(f"  dataset_id:   {dataset_id}")
    click.echo(f"  optimizer:    {_optimizer}")
    click.echo(f"  budget:       {_budget}")
    click.echo(f"  min_examples: {_min_examples}")

    try:
        from codeops.dspy.compiler import compile_program
        from codeops.dspy.store import DSPyProgramStore

        compiled, n_examples = compile_program(
            program_id=program_id,
            dataset_id=dataset_id,
            datasets_dir=cfg.datasets_dir,
            optimizer=_optimizer,
            compile_budget=_budget,
            min_examples=_min_examples,
        )
        store = DSPyProgramStore(cfg.programs_dir)
        path, version = store.save(compiled, program_id)

        version_mgr = ProgramVersionManager(cfg.programs_dir)
        version_mgr.record_version(
            program_id,
            ProgramVersionRecord(
                version=version,
                optimizer=_optimizer,
                dataset=dataset_id,
                compile_id=f"{program_id}-v{version}",
            ),
            tags=[cfg.shadow_tag or "candidate"],
        )

        click.echo(f"\nCompiled {n_examples} examples → {path}")
        click.echo(f"Tagged version v{version} as '{cfg.shadow_tag or 'candidate'}'")
        click.echo("Run `codeops dspy programs` to inspect inventory.")

    except ValueError as exc:
        raise click.ClickException(str(exc))
    except Exception as exc:
        raise click.ClickException(f"Compilation failed: {exc}")


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

@dspy_cmd.command("eval")
@click.option("--agent", "-a", required=True, help="Agent or program id to evaluate")
@click.option("--version", "-v", default=None, type=int, help="Program version (default: latest)")
@click.pass_context
def dspy_eval(ctx: click.Context, agent: str, version: int | None) -> None:
    """Evaluate a compiled DSPy program on its dataset."""
    config = ctx.obj["config"]
    cfg = config.dspy

    try:
        import dspy as _dspy  # noqa: F401
    except ImportError:
        raise click.ClickException("DSPy is not installed. Run: pip install codeops[dspy]")

    from codeops.dspy.compiler import load_dataset
    from codeops.dspy.store import DSPyProgramStore
    from codeops.dspy.programs import get_registry

    registry = get_registry()
    program_def = registry.get(agent) or registry.get_primary(agent)
    if not program_def:
        raise click.ClickException(f"Unknown agent or program id: {agent}")

    program_id = program_def.program_id

    store = DSPyProgramStore(cfg.programs_dir)
    program = program_def.factory()
    loaded, used_version = store.load(
        program_id,
        program,
        version,
        aliases=tuple(program_def.agents),
    )
    if not loaded:
        raise click.ClickException(
            f"No compiled program found for {program_id}. Run: codeops dspy compile --agent {agent}"
        )

    dataset = load_dataset(cfg.datasets_dir, program_def.primary_agent)
    if not dataset:
        raise click.ClickException(f"No dataset found for {program_def.primary_agent}")

    metric = program_def.metric
    scores = []
    for ex in dataset:
        try:
            pred = program(**{k: getattr(ex, k, "") for k in ex.inputs()})
            scores.append(metric(ex, pred))
        except Exception as exc:
            logger.debug("eval error on example: %s", exc)
            scores.append(0.0)

    avg = sum(scores) / len(scores) if scores else 0.0
    v = used_version if version is None else version

    click.echo(f"\nEval results for {program_id} v{v}:")
    click.echo(f"  examples: {len(scores)}")
    click.echo(f"  avg score: {avg:.3f}")
    click.echo(f"  min score: {min(scores):.3f}")
    click.echo(f"  max score: {max(scores):.3f}")


# ---------------------------------------------------------------------------
# programs
# ---------------------------------------------------------------------------

@dspy_cmd.command("programs")
@click.pass_context
def dspy_programs(ctx: click.Context) -> None:
    """List all compiled DSPy programs."""
    config = ctx.obj["config"]
    cfg = config.dspy

    from codeops.dspy.store import DSPyProgramStore
    from codeops.dspy.versioning import ProgramVersionManager
    from codeops.dspy.programs import get_registry

    store = DSPyProgramStore(cfg.programs_dir)
    version_mgr = ProgramVersionManager(cfg.programs_dir)
    registry = get_registry()

    programs = store.list_programs()

    if not programs:
        click.echo("No compiled programs found.")
        click.echo("Run: codeops dspy compile --agent <agent>")
        return

    index = version_mgr.list_programs()

    click.echo("Compiled Programs:")
    click.echo(f"  {'Program':24s}  {'Agents':20s}  {'Versions':20s}  Tags")
    click.echo("  " + "-" * 80)
    for program_id, versions in sorted(programs.items()):
        latest = max(versions)
        v_str = ",".join(f"v{v}" for v in versions)
        tags = index.get(program_id, {}).get("tags", {})
        tags_str = ", ".join(f"{tag}→v{ver}" for tag, ver in sorted(tags.items(), key=lambda item: item[0])) or "-"
        definition = registry.get(program_id)
        agents = ",".join(definition.agents) if definition else "?"
        click.echo(f"  {program_id:24s}  {agents:20s}  {v_str:20s}  latest=v{latest}  {tags_str}")


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

@dspy_cmd.command("promote")
@click.argument("program_spec")
@click.option("--tag", "-t", default="production", help="Tag to assign (e.g. production, candidate)")
@click.pass_context
def dspy_promote(ctx: click.Context, program_spec: str, tag: str) -> None:
    """Assign a deployment tag to a compiled program version.

    PROGRAM_SPEC format: <agent_or_program>.<version>  e.g.  code-review.v2
    """
    config = ctx.obj["config"]
    cfg = config.dspy

    if "." not in program_spec:
        raise click.ClickException(
            "program_spec must be in format <program>.<version> e.g. code-review.v2"
        )
    name, version_part = program_spec.rsplit(".", 1)
    version_str = version_part.lstrip("v")
    try:
        version = int(version_str)
    except ValueError:
        raise click.ClickException(f"Invalid version in spec: {program_spec}")

    from codeops.dspy.programs import get_registry
    from codeops.dspy.store import DSPyProgramStore
    from codeops.dspy.versioning import ProgramVersionManager

    registry = get_registry()
    program_def = registry.get(name) or registry.get_primary(name)
    if not program_def:
        raise click.ClickException(f"Unknown agent or program id: {name}")

    program_id = program_def.program_id
    store = DSPyProgramStore(cfg.programs_dir)
    path = store.path_for(program_id, version, aliases=tuple(program_def.agents))
    if not path.exists():
        raise click.ClickException(f"Compiled program not found: {path}")

    version_mgr = ProgramVersionManager(cfg.programs_dir)
    version_mgr.assign_tag(program_id, tag, version)

    click.echo(f"Assigned tag '{tag}' to {program_id} v{version}")
