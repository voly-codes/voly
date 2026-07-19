"""Copy selected modules into --cwd with license gate and path safety."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from voly.executor.safety import DEFAULT_PROTECTED_PATHS, is_protected
from voly.reuse.license import is_allowed
from voly.reuse.report import ApplyAction, CandidatePack, PickedModule, ReuseReport

_log = logging.getLogger("voly.reuse.apply")


class ApplyError(RuntimeError):
    pass


def _safe_join(root: Path, rel: str) -> Path:
    """Resolve rel under root; raise if it escapes."""
    rel_norm = rel.replace("\\", "/").lstrip("/")
    if not rel_norm or rel_norm.startswith("..") or "/../" in f"/{rel_norm}/":
        raise ApplyError(f"unsafe path: {rel}")
    target = (root / rel_norm).resolve()
    root_res = root.resolve()
    if not str(target).startswith(str(root_res) + os.sep) and target != root_res:
        raise ApplyError(f"path escapes root: {rel}")
    return target


def apply_picks(
    report: ReuseReport,
    *,
    cwd: str | Path,
    dest_rel: str = "vendor/reuse",
    dry_run: bool = True,
    allowed_licenses: list[str] | None = None,
    deny_licenses: list[str] | None = None,
    protected: list[str] | tuple[str, ...] | None = None,
) -> ReuseReport:
    """Copy picked modules into cwd/dest_rel/<owner>__<repo>/..."""
    cwd_path = Path(cwd).expanduser().resolve()
    if not cwd_path.is_dir():
        raise ApplyError(f"cwd is not a directory: {cwd}")

    patterns = protected if protected is not None else DEFAULT_PROTECTED_PATHS
    by_repo: dict[str, CandidatePack] = {c.full_name: c for c in report.candidates}
    actions: list[ApplyAction] = []
    report.dry_run = dry_run
    report.apply_dest = dest_rel
    report.cwd = str(cwd_path)

    for pick in report.picked:
        cand = by_repo.get(pick.repo)
        if cand is None:
            actions.append(ApplyAction(
                src=pick.path, dest="", status="skipped",
                detail=f"unknown repo {pick.repo}",
            ))
            continue

        if not is_allowed(
            cand.license_spdx,
            allowed=allowed_licenses,
            denied=deny_licenses,
        ):
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest="",
                status="blocked",
                detail=f"license not allowed: {cand.license_spdx or 'unknown'}",
            ))
            continue

        if not cand.cache_path:
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest="",
                status="skipped",
                detail="repo not cloned",
            ))
            continue

        cache_root = Path(cand.cache_path)
        try:
            src = _safe_join(cache_root, pick.path)
        except ApplyError as e:
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest="",
                status="blocked",
                detail=str(e),
            ))
            continue

        if not src.exists():
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest="",
                status="skipped",
                detail="source path missing",
            ))
            continue

        owner_repo = pick.repo.replace("/", "__")
        rel_dest = f"{dest_rel.rstrip('/')}/{owner_repo}/{pick.path}"
        if is_protected(rel_dest, patterns):
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest=rel_dest,
                status="blocked",
                detail="protected path",
            ))
            continue

        try:
            dest = _safe_join(cwd_path, rel_dest)
        except ApplyError as e:
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest=rel_dest,
                status="blocked",
                detail=str(e),
            ))
            continue

        if dry_run:
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest=rel_dest,
                status="planned",
                detail="dry-run",
            ))
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            # Copy LICENSE next to vendor tree once per repo
            _ensure_license_notice(cache_root, cwd_path / dest_rel / owner_repo, cand)
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest=rel_dest,
                status="copied",
                detail="",
            ))
        except OSError as e:
            actions.append(ApplyAction(
                src=f"{pick.repo}:{pick.path}",
                dest=rel_dest,
                status="skipped",
                detail=str(e)[:200],
            ))

    report.apply_actions = actions
    return report


def _ensure_license_notice(
    cache_root: Path,
    vendor_repo_dir: Path,
    cand: CandidatePack,
) -> None:
    vendor_repo_dir.mkdir(parents=True, exist_ok=True)
    notice = vendor_repo_dir / "NOTICE"
    if not notice.exists():
        notice.write_text(
            f"Source: {cand.full_name}\n"
            f"URL: {cand.html_url}\n"
            f"License: {cand.license_spdx or 'unknown'}\n",
            encoding="utf-8",
        )
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        src = cache_root / name
        if src.is_file():
            dest = vendor_repo_dir / name
            if not dest.exists():
                shutil.copy2(src, dest)
            break
