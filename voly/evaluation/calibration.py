"""Local calibration metrics for rubric LLM judges."""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CALIBRATION_REPORT_SCHEMA_VERSION = 1
DEFAULT_MIN_SAMPLES = 20


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    observed = successes / total
    denominator = 1 + z * z / total
    center = (observed + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            observed * (1 - observed) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def _lineage(record: Any, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": record.evaluation.policy_id if record.evaluation else "",
        "policy_version": record.evaluation.policy_version if record.evaluation else "",
        "rubric_id": str(detail.get("rubric_id") or "unknown"),
        "model": str(detail.get("model") or record.execution.model or "unknown"),
        "provider": str(detail.get("provider") or record.execution.provider or "unknown"),
        "threshold": float(detail.get("threshold") or 0.0),
    }


def _lineage_key(lineage: dict[str, Any]) -> str:
    return json.dumps(lineage, sort_keys=True, separators=(",", ":"))


def _latest_event(detail: dict[str, Any]) -> dict[str, Any] | None:
    events = detail.get("calibration_events")
    if not isinstance(events, list):
        return None
    valid = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("human_label") in {"pass", "fail"}
        and event.get("judge_label") in {"pass", "fail"}
    ]
    return valid[-1] if valid else None


def _group_metrics(
    lineage: dict[str, Any],
    samples: list[dict[str, Any]],
    min_samples: int,
) -> dict[str, Any]:
    tp = sum(s["human_label"] == "pass" and s["judge_label"] == "pass" for s in samples)
    tn = sum(s["human_label"] == "fail" and s["judge_label"] == "fail" for s in samples)
    fp = sum(s["human_label"] == "fail" and s["judge_label"] == "pass" for s in samples)
    fn = sum(s["human_label"] == "pass" and s["judge_label"] == "fail" for s in samples)
    total = len(samples)
    agreement = tp + tn
    human_fail = tn + fp
    human_pass = tp + fn
    return {
        "lineage": lineage,
        "sample_status": "sufficient" if total >= min_samples else "informational",
        "sample_count": total,
        "confusion_matrix": {
            "true_pass": tp,
            "true_fail": tn,
            "false_pass": fp,
            "false_fail": fn,
        },
        "metrics": {
            "agreement_rate": _ratio(agreement, total),
            "agreement_wilson_95": _wilson(agreement, total),
            "false_pass_rate": _ratio(fp, human_fail),
            "false_fail_rate": _ratio(fn, human_pass),
            "precision_pass": _ratio(tp, tp + fp),
            "recall_pass": _ratio(tp, human_pass),
        },
        "disagreements": [
            {
                "task_id": sample["task_id"],
                "human_label": sample["human_label"],
                "judge_label": sample["judge_label"],
                "feedback_kind": sample["feedback_kind"],
            }
            for sample in samples
            if sample["human_label"] != sample["judge_label"]
        ],
    }


def build_calibration_report(
    evidence_dir: str | Path,
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[str, Any]:
    """Aggregate latest explicit labels without rewriting source evidence."""
    # Lazy import avoids evidence.schema → evaluation.schema → evaluation.__init__
    # cycling during web/test module collection.
    from voly.evidence.schema import EvidenceRecord

    if min_samples < 1:
        raise ValueError("min_samples must be at least 1")
    root = Path(evidence_dir)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    lineages: dict[str, dict[str, Any]] = {}
    scanned = invalid = judge_decisions = labeled = 0
    if root.exists() and not root.is_dir():
        raise ValueError(f"evidence path is not a directory: {root}")
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        scanned += 1
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            record = EvidenceRecord.from_dict(raw)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            invalid += 1
            continue
        if record.evaluation is None:
            continue
        for check in record.evaluation.checks:
            if check.evaluator != "llm_judge" or check.status not in {"passed", "failed"}:
                continue
            judge_decisions += 1
            event = _latest_event(check.detail)
            if event is None:
                continue
            labeled += 1
            lineage = _lineage(record, check.detail)
            key = _lineage_key(lineage)
            lineages[key] = lineage
            groups[key].append(
                {
                    "task_id": record.task_id,
                    "human_label": event["human_label"],
                    "judge_label": event["judge_label"],
                    "feedback_kind": str(event.get("feedback_kind") or ""),
                }
            )
    results = [
        _group_metrics(lineages[key], groups[key], min_samples)
        for key in sorted(groups)
    ]
    return {
        "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"evidence_dir": str(root), "records_scanned": scanned, "invalid": invalid},
        "summary": {
            "judge_decisions": judge_decisions,
            "labeled_decisions": labeled,
            "unlabeled_decisions": judge_decisions - labeled,
            "lineages": len(results),
            "min_samples": min_samples,
        },
        "groups": results,
        "policy": {
            "latest_feedback_per_judge_decision": True,
            "automatic_threshold_changes": False,
            "automatic_routing_changes": False,
        },
    }


def save_calibration_report(report: dict[str, Any], path: str | Path) -> Path:
    """Atomically save a local calibration report."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
