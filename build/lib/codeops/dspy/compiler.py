"""
DSPy Compiler — builds optimized programs for CodeOps agents.

Flow:
    1. Load dataset from .codeops/dspy/datasets/<agent>.jsonl
    2. Build a dspy.Module for the agent
    3. Run the configured teleprompter (optimizer)
    4. Save the compiled program to the store

Supported optimizers (config.dspy.optimizer):
    bootstrap_fewshot   → dspy.BootstrapFewShot   (default, fast)
    bootstrap_rs        → dspy.BootstrapFewShotWithRandomSearch
    mipro               → dspy.MIPROv2             (slow, best quality)

Compile budget:
    small    → max_bootstrapped_demos=2, max_labeled_demos=4
    medium   → max_bootstrapped_demos=4, max_labeled_demos=8
    large    → max_bootstrapped_demos=8, max_labeled_demos=16
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DSPY_AVAILABLE = False
try:
    import dspy  # noqa: F401
    _DSPY_AVAILABLE = True
except ImportError:
    pass


def _require_dspy() -> None:
    if not _DSPY_AVAILABLE:
        raise ImportError("DSPy is not installed. Run: pip install codeops[dspy]")


# Budget → optimizer kwargs
_BUDGET_KWARGS: dict[str, dict[str, Any]] = {
    "small":  {"max_bootstrapped_demos": 2, "max_labeled_demos": 4},
    "medium": {"max_bootstrapped_demos": 4, "max_labeled_demos": 8},
    "large":  {"max_bootstrapped_demos": 8, "max_labeled_demos": 16},
}


def load_dataset(datasets_dir: str, dataset_id: str) -> list[Any]:
    """
    Load JSONL dataset from .codeops/dspy/datasets/<dataset_id>.jsonl.

    Each line must be a JSON object with at minimum:
        {"task": "...", "agent": "...", ...}  (routing dataset)
    or agent-specific fields matching the Signature InputFields.

    Returns list of dspy.Example objects.
    """
    _require_dspy()
    import dspy

    path = Path(datasets_dir) / f"{dataset_id}.jsonl"
    if not path.exists():
        logger.warning("dspy.compiler: dataset not found: %s", path)
        return []

    examples = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
            ex = dspy.Example(**record).with_inputs(*list(record.keys()))
            examples.append(ex)
        except Exception as exc:
            logger.debug("dspy.compiler: skipping line %d in %s: %s", i, path, exc)

    logger.info("dspy.compiler: loaded %d examples for %s", len(examples), dataset_id)
    return examples


def build_teleprompter(
    optimizer: str,
    metric: callable,
    budget: str = "small",
) -> Any:
    """
    Build a DSPy teleprompter (optimizer) instance.

    Args:
        optimizer: optimizer name (bootstrap_fewshot | bootstrap_rs | mipro)
        metric:    metric function (example, prediction, trace) → float
        budget:    compile budget (small | medium | large)
    """
    _require_dspy()
    import dspy

    kwargs = _BUDGET_KWARGS.get(budget, _BUDGET_KWARGS["small"]).copy()
    kwargs["metric"] = metric

    if optimizer == "bootstrap_fewshot":
        return dspy.BootstrapFewShot(**kwargs)
    elif optimizer in ("bootstrap_rs", "bootstrap_random_search"):
        num_candidates = {"small": 4, "medium": 8, "large": 16}.get(budget, 4)
        return dspy.BootstrapFewShotWithRandomSearch(
            num_candidate_programs=num_candidates,
            **kwargs,
        )
    elif optimizer in ("mipro", "miprov2"):
        return dspy.MIPROv2(metric=metric, auto="light" if budget == "small" else "medium")
    else:
        logger.warning("dspy.compiler: unknown optimizer %r, defaulting to BootstrapFewShot", optimizer)
        return dspy.BootstrapFewShot(**kwargs)


def compile_program(
    program_id: str,
    *,
    dataset_id: str,
    datasets_dir: str = ".codeops/dspy/datasets",
    optimizer: str = "bootstrap_fewshot",
    compile_budget: str = "small",
    min_examples: int = 20,
) -> tuple[Any, int]:
    """
    Compile a DSPy program identified by program_id using the specified dataset.

    Returns:
        (compiled_program, num_examples_used)

    Raises:
        ImportError:  dspy not installed
        ValueError:   not enough examples in dataset
    """
    _require_dspy()
    from codeops.dspy.programs import get_registry

    registry = get_registry()
    program_def = registry.get(program_id)
    if not program_def:
        raise ValueError(f"Unknown DSPy program: {program_id}")

    dataset = load_dataset(datasets_dir, dataset_id)
    if len(dataset) < min_examples:
        raise ValueError(
            f"Not enough examples for {dataset_id}: need {min_examples}, got {len(dataset)}. "
            f"Run: codeops dspy dataset build --agent {dataset_id}"
        )

    metric = program_def.metric
    program = program_def.factory()
    teleprompter = build_teleprompter(optimizer, metric, compile_budget)

    # Split: 80% train, 20% dev
    split = max(1, int(len(dataset) * 0.8))
    trainset = dataset[:split]
    devset = dataset[split:] or dataset[:1]

    logger.info(
        "dspy.compiler: compiling %s | optimizer=%s budget=%s train=%d dev=%d",
        program_id,
        optimizer,
        compile_budget,
        len(trainset),
        len(devset),
    )

    compiled = teleprompter.compile(program, trainset=trainset, valset=devset)
    logger.info("dspy.compiler: done compiling %s", program_id)

    return compiled, len(dataset)
