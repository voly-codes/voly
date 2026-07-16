#!/usr/bin/env python3
"""FinOps suite runner — Phase 1 inventory + Phase 2 baseline/VOLY harness.

Usage:
  python benchmarks/finops-suite/run.py --mode mock
  python benchmarks/finops-suite/run.py --mode mock --task midchain-quota
  python benchmarks/finops-suite/run.py --mode live --confirm   # gated; no auto-spend yet
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_SUITE_DIR = Path(__file__).resolve().parent
if str(_SUITE_DIR) not in sys.path:
    sys.path.insert(0, str(_SUITE_DIR))

from harness import render_results_md, run_suite_comparison, summarize  # noqa: E402
from suite import RESULTS_DIR, inventory, load_suite, materialize_fixture  # noqa: E402

_LIVE_CRED_ENV = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_mock(*, task_id: str | None = None) -> int:
    suite = load_suite()
    inv = inventory(suite)
    if len(inv["cross_vendor_mock_tasks"]) < 1:
        print("ERROR: no cross-vendor mock tasks (≥2 executors)", file=sys.stderr)
        return 2

    task_ids = [task_id] if task_id else None
    if task_id:
        suite.by_id(task_id)  # KeyError if unknown

    with tempfile.TemporaryDirectory(prefix="voly-finops-") as tmp:
        cwd = materialize_fixture(Path(tmp) / "project")
        rows = run_suite_comparison(suite, str(cwd), task_ids=task_ids)

    if not rows:
        print("ERROR: no rows produced", file=sys.stderr)
        return 2

    summary = summarize(rows)
    if summary["billing_fallback_rows"] and summary["billing_fallback_saved_usd"] <= 0:
        print(
            "ERROR: billing_fallback scenarios must show positive saved_usd "
            f"(got {summary['billing_fallback_saved_usd']})",
            file=sys.stderr,
        )
        return 2

    generated_at = _utc_now()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "mode": "mock",
        "phase": 2,
        "generated_at": generated_at,
        "suite_id": suite.suite_id,
        "claims": suite.claims,
        "billing_fallback_chain": suite.billing_fallback_chain,
        "inventory": inv,
        "summary": summary,
        "rows": [r.as_dict() for r in rows],
        "notes": (
            "Phase 2 mock harness via AgentRunner + fake executors. "
            "Costs from TaskEvent (retry-aware). Not a Layer A provider benchmark."
        ),
    }
    results_json = RESULTS_DIR / "results.json"
    results_md = RESULTS_DIR / "results.md"
    smoke_json = RESULTS_DIR / "mock-smoke.json"

    results_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    results_md.write_text(
        render_results_md(rows, suite_id=suite.suite_id, generated_at=generated_at),
        encoding="utf-8",
    )
    # Keep Phase 1 artifact name as a thin pointer for older scripts/tests.
    smoke_json.write_text(
        json.dumps(
            {
                "mode": "mock",
                "phase": 2,
                "generated_at": generated_at,
                "inventory": inv,
                "results": str(results_json),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"suite_id={suite.suite_id} tasks={summary['task_count']}")
    print(
        f"totals baseline=${summary['baseline_usd_total']:.4f} "
        f"voly=${summary['voly_usd_total']:.4f} "
        f"saved=${summary['saved_usd_total']:.4f} "
        f"({summary['saved_pct_total']}%)"
    )
    print(
        f"billing_fallback_saved=${summary['billing_fallback_saved_usd']:.4f} "
        f"cross_vendor_rows={summary['cross_vendor_rows']}"
    )
    print(f"wrote {results_json}")
    print(f"wrote {results_md}")
    return 0


def run_live(*, task_id: str | None = None, confirm: bool = False) -> int:
    """Live CLI arms still gated — mock harness is the CI path."""
    _ = load_suite()
    if not confirm:
        print(
            "LIVE mode is opt-in and may spend real API/CLI credits.\n"
            "Re-run with --confirm when live arms are implemented.\n"
            "For CI use: --mode mock",
            file=sys.stderr,
        )
        return 3

    present = [k for k in _LIVE_CRED_ENV if os.environ.get(k)]
    if not present:
        print(
            "ERROR: no live credentials found "
            f"(checked {', '.join(_LIVE_CRED_ENV)})",
            file=sys.stderr,
        )
        return 4

    print(
        f"credentials_ok env={present}; task_filter={task_id or 'all'}; "
        "live AgentRunner arms not wired yet — use --mode mock. Aborting before spend."
    )
    return 5


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="VOLY FinOps benchmark suite runner (BO002)")
    p.add_argument("--mode", choices=("mock", "live"), default="mock")
    p.add_argument("--task", dest="task_id", default=None, help="Single task id")
    p.add_argument("--confirm", action="store_true", help="Required for --mode live")
    args = p.parse_args(argv)

    if args.mode == "mock":
        return run_mock(task_id=args.task_id)
    return run_live(task_id=args.task_id, confirm=args.confirm)


if __name__ == "__main__":
    raise SystemExit(main())
