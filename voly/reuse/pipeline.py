"""Orchestrator: search → clone → pack → pick → apply."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from voly.config import ReuseConfig, VOLYConfig
from voly.reuse.apply import apply_picks
from voly.reuse.clone import CloneError, clone_repo, resolve_head_sha
from voly.reuse.github_search import (
    GitHubSearchError,
    get_repo,
    infer_language,
    search_repositories,
    task_to_query,
)
from voly.reuse.license import is_allowed, resolve_license
from voly.reuse.pack import pack_repo
from voly.reuse.picker import pick_modules, plan_search_query
from voly.reuse.report import CandidatePack, ReuseReport, save_report

_log = logging.getLogger("voly.reuse.pipeline")


def _reuse_cfg(config: VOLYConfig | None) -> ReuseConfig:
    if config is None:
        return ReuseConfig()
    return getattr(config, "reuse", None) or ReuseConfig()


def _build_gateway(config: VOLYConfig) -> Any:
    from voly.ai_gateway import AIGateway

    gw = AIGateway(
        account_id=config.ai_gateway.account_id,
        gateway_id=config.ai_gateway.gateway_id,
        api_token=config.ai_gateway.api_token,
    )
    gw._enabled = config.ai_gateway.enabled
    return gw


def search_and_pack(
    task: str,
    *,
    config: VOLYConfig | None = None,
    limit: int | None = None,
    language: str = "",
    gateway: Any = None,
    pack: bool = True,
) -> ReuseReport:
    """Search GitHub, optionally clone+pack each candidate. No apply."""
    cfg = _reuse_cfg(config)
    report = ReuseReport(task=task)

    lang = language or infer_language(task)
    if gateway is not None:
        query = plan_search_query(task, gateway)
    else:
        query = task_to_query(task, language=lang)
    if lang and f"language:{lang}" not in query:
        query = f"{query} language:{lang}"
    report.query = query

    max_repos = limit if limit is not None else cfg.max_repos
    try:
        hits = search_repositories(query, limit=max_repos, min_stars=cfg.min_stars)
    except GitHubSearchError as e:
        report.notes.append(f"search failed: {e}")
        return report

    for hit in hits:
        spdx = resolve_license(github_spdx=hit.license_spdx)
        cand = CandidatePack(
            full_name=hit.full_name,
            html_url=hit.html_url,
            clone_url=hit.clone_url,
            description=hit.description,
            stars=hit.stars,
            language=hit.language,
            license_spdx=spdx,
            license_allowed=is_allowed(
                spdx,
                allowed=cfg.allowed_licenses,
                denied=cfg.deny_licenses,
            ),
            default_branch=hit.default_branch,
        )
        if not pack:
            report.candidates.append(cand)
            continue
        if not hit.clone_url:
            cand.error = "no clone_url"
            report.candidates.append(cand)
            continue
        try:
            cache_path = clone_repo(
                hit.clone_url,
                full_name=hit.full_name,
                cache_dir=cfg.cache_dir,
            )
            cand.cache_path = str(cache_path)
            cand.sha = resolve_head_sha(cache_path)
            # Re-resolve license from LICENSE file if needed
            cand.license_spdx = resolve_license(
                github_spdx=cand.license_spdx,
                repo_dir=cache_path,
            )
            cand.license_allowed = is_allowed(
                cand.license_spdx,
                allowed=cfg.allowed_licenses,
                denied=cfg.deny_licenses,
            )
            pack_repo(
                cache_path,
                task=task,
                max_chars=cfg.pack_max_chars,
                candidate=cand,
            )
        except CloneError as e:
            cand.error = str(e)
            _log.warning("clone failed %s: %s", hit.full_name, e)
        report.candidates.append(cand)

    return report


def pack_one(
    full_name: str,
    *,
    task: str = "",
    config: VOLYConfig | None = None,
) -> CandidatePack:
    """Clone + pack a single owner/repo."""
    cfg = _reuse_cfg(config)
    hit = get_repo(full_name)
    spdx = resolve_license(github_spdx=hit.license_spdx)
    cand = CandidatePack(
        full_name=hit.full_name,
        html_url=hit.html_url,
        clone_url=hit.clone_url,
        description=hit.description,
        stars=hit.stars,
        language=hit.language,
        license_spdx=spdx,
        license_allowed=is_allowed(
            spdx,
            allowed=cfg.allowed_licenses,
            denied=cfg.deny_licenses,
        ),
        default_branch=hit.default_branch,
    )
    cache_path = clone_repo(
        hit.clone_url,
        full_name=hit.full_name,
        cache_dir=cfg.cache_dir,
    )
    cand.cache_path = str(cache_path)
    cand.sha = resolve_head_sha(cache_path)
    cand.license_spdx = resolve_license(github_spdx=cand.license_spdx, repo_dir=cache_path)
    cand.license_allowed = is_allowed(
        cand.license_spdx,
        allowed=cfg.allowed_licenses,
        denied=cfg.deny_licenses,
    )
    return pack_repo(
        cache_path,
        task=task,
        max_chars=cfg.pack_max_chars,
        candidate=cand,
    )


def auto_reuse(
    task: str,
    *,
    cwd: str | Path,
    config: VOLYConfig | None = None,
    gateway: Any = None,
) -> ReuseReport | None:
    """Run search+pick automatically before an executor call.

    Skips silently if: auto disabled, no GitHub token, fresh report already exists,
    or any network/API error occurs. Never raises — must not block the main run.
    """
    import time

    cfg = _reuse_cfg(config)
    if not cfg.auto:
        return None

    reports_dir = Path(cfg.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = Path(cwd).expanduser() / reports_dir

    try:
        from voly.reuse.report import latest_report_path, load_report

        path = latest_report_path(reports_dir)
        if path is not None:
            age = time.time() - path.stat().st_mtime
            if age < cfg.auto_max_age_seconds:
                # Only skip when the fresh report actually has usable candidates.
                # Empty / all-denied reports must not poison auto-search for 7 days.
                usable = False
                try:
                    prev = load_report(path)
                    usable = any(
                        c.license_allowed and not c.error for c in prev.candidates
                    )
                except Exception:
                    usable = False
                if usable:
                    _log.debug(
                        "auto_reuse: fresh usable report exists (%ds old), skipping",
                        int(age),
                    )
                    return None
                _log.info(
                    "auto_reuse: fresh report has no usable candidates — re-searching"
                )
    except Exception:
        pass

    if gateway is None and config is not None:
        try:
            gateway = _build_gateway(config)
        except Exception:
            pass

    try:
        report = search_and_pack(
            task,
            config=config,
            limit=cfg.auto_max_repos,
            gateway=gateway,
            pack=True,
        )
        report.picked = pick_modules(task, report.candidates, gateway)
        path = save_report(report, reports_dir)
        _log.info("auto_reuse: saved %s (%d candidates, %d picked)",
                  path, len(report.candidates), len(report.picked))
        return report
    except Exception as exc:
        _log.warning("auto_reuse: skipped due to error: %s", exc)
        return None


def run_reuse(
    task: str,
    *,
    cwd: str | Path,
    config: VOLYConfig | None = None,
    gateway: Any = None,
    dry_run: bool = True,
    limit: int | None = None,
    language: str = "",
    write: bool = False,
) -> ReuseReport:
    """Full MVP: search → pack → pick → apply (dry-run unless write=True)."""
    cfg = _reuse_cfg(config)
    if write:
        dry_run = False

    # Build gateway if not provided and config available
    if gateway is None and config is not None:
        try:
            gateway = _build_gateway(config)
        except Exception as e:
            _log.debug("AIGateway unavailable: %s", e)
            gateway = None

    report = search_and_pack(
        task,
        config=config,
        limit=limit,
        language=language,
        gateway=gateway,
        pack=True,
    )

    report.picked = pick_modules(task, report.candidates, gateway)
    report = apply_picks(
        report,
        cwd=cwd,
        dest_rel=cfg.apply_dest,
        dry_run=dry_run,
        allowed_licenses=cfg.allowed_licenses,
        deny_licenses=cfg.deny_licenses,
    )

    # Resolve reports_dir relative to cwd when relative
    reports_dir = Path(cfg.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = Path(cwd).expanduser() / reports_dir
    path = save_report(report, reports_dir)
    report.notes.append(f"saved: {path}")
    return report
