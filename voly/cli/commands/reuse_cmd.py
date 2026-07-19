"""CLI: voly reuse — search / pack / pick / apply / run code reuse pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import click


@click.group("reuse")
def reuse_cmd() -> None:
    """Find similar GitHub repos and reuse modules with a license gate."""
    pass


def _cfg(ctx: click.Context):
    return ctx.obj["config"]


def _print_candidates(report) -> None:
    click.echo(f"query: {report.query}")
    if not report.candidates:
        click.echo("(no candidates)")
        for n in report.notes:
            click.echo(f"note: {n}")
        return
    for i, c in enumerate(report.candidates, 1):
        lic = c.license_spdx or "?"
        flag = "ok" if c.license_allowed else "deny"
        err = f" ERR={c.error}" if c.error else ""
        click.echo(
            f"{i}. {c.full_name}  ★{c.stars}  {c.language or '-'}  "
            f"license={lic}[{flag}]{err}"
        )
        if c.description:
            click.echo(f"   {c.description[:120]}")
        if c.relevant_files:
            click.echo(f"   files: {', '.join(c.relevant_files[:5])}")


@reuse_cmd.command("search")
@click.argument("task")
@click.option("--limit", default=None, type=int, help="Max repos (default: config)")
@click.option("--lang", "language", default="", help="GitHub language filter")
@click.option("--pack/--no-pack", default=True, help="Clone+pack candidates (default: pack)")
@click.option("--json-out", "json_out", is_flag=True, help="Print JSON report")
@click.pass_context
def reuse_search(
    ctx: click.Context,
    task: str,
    limit: int | None,
    language: str,
    pack: bool,
    json_out: bool,
) -> None:
    """Search GitHub for repos matching the task; optionally clone+pack."""
    from voly.reuse.pipeline import search_and_pack
    from voly.reuse.report import save_report

    config = _cfg(ctx)
    report = search_and_pack(
        task, config=config, limit=limit, language=language, pack=pack,
    )
    reports_dir = Path(config.reuse.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = Path.cwd() / reports_dir
    path = save_report(report, reports_dir)
    report.notes.append(f"saved: {path}")

    if json_out:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_candidates(report)
        click.echo(f"report: {path}")


@reuse_cmd.command("pack")
@click.argument("repo")
@click.option("--task", default="", help="Task text for keyword scoring")
@click.option("--json-out", "json_out", is_flag=True)
@click.pass_context
def reuse_pack(ctx: click.Context, repo: str, task: str, json_out: bool) -> None:
    """Clone and pack a single owner/repo candidate."""
    from voly.reuse.pipeline import pack_one
    from voly.reuse.report import ReuseReport, save_report

    config = _cfg(ctx)
    try:
        cand = pack_one(repo, task=task, config=config)
    except Exception as exc:
        click.echo(f"pack failed: {exc}", err=True)
        raise SystemExit(1) from exc

    report = ReuseReport(task=task or f"pack {repo}", candidates=[cand])
    reports_dir = Path(config.reuse.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = Path.cwd() / reports_dir
    path = save_report(report, reports_dir)

    if json_out:
        click.echo(json.dumps(cand.__dict__, ensure_ascii=False, indent=2))
    else:
        click.echo(f"{cand.full_name}  sha={cand.sha}  cache={cand.cache_path}")
        click.echo(f"license={cand.license_spdx} allowed={cand.license_allowed}")
        click.echo(f"scanner: {cand.scanner_summary}")
        click.echo(f"relevant: {', '.join(cand.relevant_files[:10])}")
        click.echo(f"report: {path}")


@reuse_cmd.command("pick")
@click.argument("report_file", type=click.Path(exists=True, dir_okay=False), required=False)
@click.option("--task", default="", help="Override task text for picker")
@click.option("--json-out", "json_out", is_flag=True)
@click.pass_context
def reuse_pick(
    ctx: click.Context,
    report_file: str | None,
    task: str,
    json_out: bool,
) -> None:
    """Pick modules from a report via AIGateway (or heuristic fallback)."""
    from voly.reuse.picker import pick_modules
    from voly.reuse.report import latest_report_path, load_report, save_report

    config = _cfg(ctx)
    path = report_file
    if not path:
        latest = latest_report_path(config.reuse.reports_dir)
        if latest is None:
            click.echo("No report found; run `voly reuse search` first.", err=True)
            raise SystemExit(2)
        path = str(latest)

    report = load_report(path)
    task_text = task or report.task
    gateway = None
    try:
        from voly.reuse.pipeline import _build_gateway

        gateway = _build_gateway(config)
    except Exception:
        pass

    report.picked = pick_modules(task_text, report.candidates, gateway)
    out = save_report(report, Path(path).parent)

    if json_out:
        click.echo(json.dumps([p.__dict__ for p in report.picked], indent=2))
    else:
        if not report.picked:
            click.echo("(no modules picked)")
        for p in report.picked:
            click.echo(f"- {p.repo}:{p.path}  conf={p.confidence:.2f}  {p.reason[:80]}")
        click.echo(f"report: {out}")


@reuse_cmd.command("apply")
@click.argument("report_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--cwd", default=None, help="Target project path")
@click.option("--write", is_flag=True, help="Actually copy files (default: dry-run)")
@click.option("--dest", default=None, help="Destination under cwd (default: config)")
@click.option("--json-out", "json_out", is_flag=True)
@click.pass_context
def reuse_apply(
    ctx: click.Context,
    report_file: str,
    cwd: str | None,
    write: bool,
    dest: str | None,
    json_out: bool,
) -> None:
    """Apply picked modules from a report (dry-run unless --write)."""
    from voly.reuse.apply import apply_picks
    from voly.reuse.report import load_report, save_report

    config = _cfg(ctx)
    target = cwd or getattr(config, "default_cwd", "") or str(Path.cwd())
    report = load_report(report_file)
    if not report.picked:
        click.echo("Report has no picked modules; run `voly reuse pick` first.", err=True)
        raise SystemExit(2)

    report = apply_picks(
        report,
        cwd=target,
        dest_rel=dest or config.reuse.apply_dest,
        dry_run=not write,
        allowed_licenses=config.reuse.allowed_licenses,
        deny_licenses=config.reuse.deny_licenses,
    )
    out = save_report(report, Path(report_file).parent)

    if json_out:
        click.echo(json.dumps([a.__dict__ for a in report.apply_actions], indent=2))
    else:
        mode = "WRITE" if write else "DRY-RUN"
        click.echo(f"mode: {mode}  cwd: {target}")
        for a in report.apply_actions:
            click.echo(f"  [{a.status}] {a.src} → {a.dest}  {a.detail}")
        click.echo(f"report: {out}")

    blocked = any(a.status == "blocked" for a in report.apply_actions)
    raise SystemExit(1 if blocked and write else 0)


@reuse_cmd.command("run")
@click.argument("task")
@click.option("--cwd", default=None, help="Target project path")
@click.option("--limit", default=None, type=int)
@click.option("--lang", "language", default="")
@click.option("--write", is_flag=True, help="Actually copy (default: dry-run apply)")
@click.option("--json-out", "json_out", is_flag=True)
@click.pass_context
def reuse_run(
    ctx: click.Context,
    task: str,
    cwd: str | None,
    limit: int | None,
    language: str,
    write: bool,
    json_out: bool,
) -> None:
    """Full pipeline: search → pack → pick → apply (dry-run by default)."""
    from voly.reuse.pipeline import run_reuse

    config = _cfg(ctx)
    target = cwd or getattr(config, "default_cwd", "") or str(Path.cwd())
    report = run_reuse(
        task,
        cwd=target,
        config=config,
        dry_run=not write,
        write=write,
        limit=limit,
        language=language,
    )

    if json_out:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return

    _print_candidates(report)
    click.echo("picked:")
    for p in report.picked:
        click.echo(f"  - {p.repo}:{p.path} ({p.confidence:.2f})")
    mode = "WRITE" if write else "DRY-RUN"
    click.echo(f"apply ({mode}):")
    for a in report.apply_actions:
        click.echo(f"  [{a.status}] {a.src} → {a.dest}")
    for n in report.notes:
        click.echo(f"note: {n}")
