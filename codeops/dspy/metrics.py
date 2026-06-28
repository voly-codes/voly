"""
DSPy metrics for CodeOps.

Metrics are used during compilation (optimization) to evaluate
program quality on a dataset. Each agent has its own metric function.

Design:
  - All metrics take (example, prediction, trace=None) → float
  - Score range: 0.0 to 1.0
  - Metrics are intentionally lenient at compile time (precision over recall)
  - No dspy import at module level — metrics are plain functions.

Metric contract (DSPy BootstrapFewShot):
    def metric(example, prediction, trace=None) -> bool | float

Where:
    example    = dspy.Example from the trainset
    prediction = dspy.Prediction returned by the module
    trace      = optional trace for beam-search optimizers
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Routing metric
# ---------------------------------------------------------------------------

def routing_metric(example: Any, prediction: Any, trace: Any = None) -> float:
    """
    Score a routing prediction against the gold example.

    Fields compared:
      agent:      exact match  (weight 0.5)
      complexity: exact match  (weight 0.2)
      confidence: >= 0.5       (weight 0.3)
    """
    score = 0.0

    pred_agent = getattr(prediction, "agent", "")
    gold_agent = getattr(example, "agent", "")
    if pred_agent and pred_agent.strip().lower() == gold_agent.strip().lower():
        score += 0.5

    pred_complexity = getattr(prediction, "complexity", "")
    gold_complexity = getattr(example, "complexity", "")
    if pred_complexity and pred_complexity.strip().lower() == gold_complexity.strip().lower():
        score += 0.2

    pred_confidence = getattr(prediction, "confidence", 0.0)
    try:
        if float(pred_confidence) >= 0.5:
            score += 0.3
    except (TypeError, ValueError):
        pass

    return score


# ---------------------------------------------------------------------------
# Code review metric
# ---------------------------------------------------------------------------

def review_metric(example: Any, prediction: Any, trace: Any = None) -> float:
    """
    Score a code review prediction.

    Criteria (heuristic, no ground truth needed at compile time):
      - summary is non-empty                (0.2)
      - risks list is non-empty             (0.2)
      - bugs list present (can be empty)    (0.1)
      - security_issues list present        (0.1)
      - suggested_patch format looks valid  (0.4)
    """
    score = 0.0

    summary = getattr(prediction, "summary", "")
    if summary and len(summary.strip()) > 20:
        score += 0.2

    risks = getattr(prediction, "risks", [])
    if isinstance(risks, list) and len(risks) > 0:
        score += 0.2

    bugs = getattr(prediction, "bugs", None)
    if bugs is not None:
        score += 0.1

    security = getattr(prediction, "security_issues", None)
    if security is not None:
        score += 0.1

    patch = getattr(prediction, "suggested_patch", "")
    if patch and ("---" in patch or "+++" in patch or "@@ " in patch):
        score += 0.4
    elif patch == "":
        # Empty patch is acceptable — reviewer correctly found nothing fixable
        score += 0.2

    return score


# ---------------------------------------------------------------------------
# Documentation metric
# ---------------------------------------------------------------------------

def docs_metric(example: Any, prediction: Any, trace: Any = None) -> float:
    """
    Score a documentation generation prediction.

    Criteria:
      - title is non-empty and short       (0.1)
      - overview has 1–3 sentences         (0.2)
      - architecture section is present    (0.3)
      - usage contains a code example      (0.3)
      - limitations field present          (0.1)
    """
    score = 0.0

    title = getattr(prediction, "title", "")
    if title and 3 <= len(title.strip()) <= 100:
        score += 0.1

    overview = getattr(prediction, "overview", "")
    if overview and len(overview.strip()) > 20:
        score += 0.2

    architecture = getattr(prediction, "architecture", "")
    if architecture and len(architecture.strip()) > 30:
        score += 0.3

    usage = getattr(prediction, "usage", "")
    if usage and ("```" in usage or ">>>" in usage or "import" in usage or "example" in usage.lower()):
        score += 0.3
    elif usage and len(usage.strip()) > 20:
        score += 0.15

    limitations = getattr(prediction, "limitations", None)
    if limitations is not None:
        score += 0.1

    return score


# ---------------------------------------------------------------------------
# Architecture metric
# ---------------------------------------------------------------------------

def architecture_metric(example: Any, prediction: Any, trace: Any = None) -> float:
    """
    Score an architecture analysis prediction.

    Criteria:
      - diagnosis is non-empty             (0.2)
      - proposed_design is non-empty       (0.2)
      - migration_plan has >= 2 steps      (0.4)
      - risks list is non-empty            (0.2)
    """
    score = 0.0

    diagnosis = getattr(prediction, "diagnosis", "")
    if diagnosis and len(diagnosis.strip()) > 20:
        score += 0.2

    design = getattr(prediction, "proposed_design", "")
    if design and len(design.strip()) > 20:
        score += 0.2

    plan = getattr(prediction, "migration_plan", [])
    if isinstance(plan, list):
        if len(plan) >= 2:
            score += 0.4
        elif len(plan) == 1:
            score += 0.2

    risks = getattr(prediction, "risks", [])
    if isinstance(risks, list) and len(risks) > 0:
        score += 0.2

    return score


# ---------------------------------------------------------------------------
# Bug analysis metric
# ---------------------------------------------------------------------------

def bugfix_metric(example: Any, prediction: Any, trace: Any = None) -> float:
    """
    Score a bug analysis prediction.

    Criteria:
      - root_cause is specific             (0.3)
      - fix_description is non-empty       (0.2)
      - patch is non-empty and valid diff  (0.4)
      - test_suggestion is non-empty       (0.1)
    """
    score = 0.0

    root_cause = getattr(prediction, "root_cause", "")
    if root_cause and len(root_cause.strip()) > 15:
        score += 0.3

    fix_desc = getattr(prediction, "fix_description", "")
    if fix_desc and len(fix_desc.strip()) > 10:
        score += 0.2

    patch = getattr(prediction, "patch", "")
    if patch and ("---" in patch or "+++" in patch or "@@ " in patch):
        score += 0.4
    elif patch and len(patch.strip()) > 5:
        score += 0.2

    test = getattr(prediction, "test_suggestion", "")
    if test and len(test.strip()) > 10:
        score += 0.1

    return score


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AGENT_METRICS: dict[str, callable] = {
    "reviewer": review_metric,
    "documenter": docs_metric,
    "architect": architecture_metric,
    "bugfixer": bugfix_metric,
    "router": routing_metric,
}


def get_metric(agent: str) -> callable:
    """Return the metric function for the given agent, defaulting to docs_metric."""
    return AGENT_METRICS.get(agent, docs_metric)
