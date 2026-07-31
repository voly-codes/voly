"""CLI for evidence-gated instincts and shadow learning."""

from __future__ import annotations

import json
from pathlib import Path

import click

from voly.learning import InstinctEvidence, InstinctStore


@click.group("learning")
def learning_cmd() -> None:
    """Manage learned instincts; active prompt injection is intentionally absent."""


def _store(ctx: click.Context, cwd: Path) -> InstinctStore:
    path = Path(ctx.obj["config"].learning.store_path)
    return InstinctStore(path if path.is_absolute() else cwd / path)


@learning_cmd.command("propose")
@click.argument("trigger")
@click.argument("action")
@click.option("--project-id", required=True)
@click.option("--evidence-kind", default="observation")
@click.option("--source-id", required=True)
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_propose(
    ctx: click.Context,
    trigger: str,
    action: str,
    project_id: str,
    evidence_kind: str,
    source_id: str,
    cwd: Path,
) -> None:
    """Create or update a project instinct candidate."""
    evidence = InstinctEvidence(evidence_kind, source_id, project_id)
    instinct = _store(ctx, cwd).propose(
        trigger, action, project_id=project_id, evidence=evidence
    )
    click.echo(json.dumps(instinct.to_dict(), ensure_ascii=False, indent=2))


@learning_cmd.command("ingest-evidence")
@click.argument("record", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("trigger")
@click.argument("action")
@click.option("--project-id", required=True)
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_ingest_evidence(
    ctx: click.Context,
    record: Path,
    trigger: str,
    action: str,
    project_id: str,
    cwd: Path,
) -> None:
    """Extract a signal from an EvidenceRecord, including human corrections."""
    from voly.evidence import EvidenceRecord

    evidence_record = EvidenceRecord.from_dict(
        json.loads(record.read_text(encoding="utf-8"))
    )
    instinct = _store(ctx, cwd).ingest_evidence_record(
        evidence_record,
        trigger=trigger,
        action=action,
        project_id=project_id,
    )
    click.echo(json.dumps(instinct.to_dict(), ensure_ascii=False, indent=2))


@learning_cmd.command("evidence")
@click.argument("instinct_id")
@click.argument("kind")
@click.argument("source_id")
@click.option("--project-id", required=True)
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_evidence(
    ctx: click.Context,
    instinct_id: str,
    kind: str,
    source_id: str,
    project_id: str,
    cwd: Path,
) -> None:
    """Attach a test/review/rollback/retry/correction signal."""
    instinct = _store(ctx, cwd).add_evidence(
        instinct_id, InstinctEvidence(kind, source_id, project_id)
    )
    click.echo(json.dumps(instinct.to_dict(), ensure_ascii=False, indent=2))


@learning_cmd.command("approve")
@click.argument("instinct_id")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_approve(ctx: click.Context, instinct_id: str, cwd: Path) -> None:
    """Manually approve an evidence-backed candidate."""
    instinct = _store(ctx, cwd).approve(instinct_id)
    click.echo(f"approved: {instinct.id}")


@learning_cmd.command("shadow")
@click.argument("task")
@click.option("--project-id", required=True)
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_shadow(
    ctx: click.Context, task: str, project_id: str, cwd: Path
) -> None:
    """Preview selection without injecting learned content."""
    selected = _store(ctx, cwd).shadow_select(task, project_id=project_id)
    click.echo(json.dumps([item.to_dict() for item in selected], ensure_ascii=False, indent=2))


@learning_cmd.command("remove")
@click.argument("instinct_id")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_remove(ctx: click.Context, instinct_id: str, cwd: Path) -> None:
    """Remove an instinct and restore baseline selection."""
    if not _store(ctx, cwd).remove(instinct_id):
        raise click.ClickException("instinct not found")
    click.echo(f"removed: {instinct_id}")


@learning_cmd.command("promote-global")
@click.argument("instinct_id")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_promote(ctx: click.Context, instinct_id: str, cwd: Path) -> None:
    """Promote after approval and positive evidence from two projects."""
    instinct = _store(ctx, cwd).promote_global(instinct_id)
    click.echo(f"promoted: {instinct.id}")


@learning_cmd.command("skill-candidates")
@click.option("--cwd", type=click.Path(file_okay=False, path_type=Path), default=Path("."))
@click.pass_context
def learning_skills(ctx: click.Context, cwd: Path) -> None:
    """Cluster stable approved instincts into versioned skill candidates."""
    config = ctx.obj["config"].learning
    candidates = _store(ctx, cwd).skill_candidates(
        min_confidence=config.min_skill_confidence
    )
    click.echo(json.dumps(candidates, ensure_ascii=False, indent=2))
