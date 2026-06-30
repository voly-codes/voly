"""Routes: /api/dspy/* — DSPy optimizer status and program inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/dspy/status")
def dspy_status(request: Request) -> dict[str, Any]:
    config = request.app.state.app.config
    if config is None:
        from codeops.config import load_config
        config = load_config()

    cfg = config.dspy

    # Check dspy package
    dspy_version: str | None = None
    try:
        import dspy
        dspy_version = getattr(dspy, "__version__", "installed")
    except ImportError:
        pass

    # Programs inventory
    programs: list[dict[str, Any]] = []
    try:
        from codeops.dspy.store import DSPyProgramStore
        from codeops.dspy.versioning import ProgramVersionManager
        from codeops.dspy.programs import get_registry

        store = DSPyProgramStore(cfg.programs_dir)
        version_mgr = ProgramVersionManager(cfg.programs_dir)
        registry = get_registry()
        index = version_mgr.list_programs()

        for program_id, versions in sorted(store.list_programs().items()):
            tags = index.get(program_id, {}).get("tags", {})
            definition = registry.get(program_id)
            programs.append({
                "program_id": program_id,
                "agents": list(definition.agents) if definition else [],
                "versions": sorted(versions),
                "latest": max(versions),
                "tags": tags,
            })
    except Exception:
        pass

    # Datasets
    datasets: list[dict[str, Any]] = []
    ds_path = Path(cfg.datasets_dir)
    if ds_path.exists():
        for f in sorted(ds_path.glob("*.jsonl")):
            try:
                lines = sum(
                    1 for line in f.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")
                )
            except Exception:
                lines = 0
            datasets.append({"name": f.stem, "examples": lines})

    return {
        "config": {
            "enabled": cfg.enabled,
            "mode": cfg.mode,
            "optimizer": cfg.optimizer,
            "compile_budget": cfg.compile_budget,
            "min_examples": cfg.min_examples,
            "agents": cfg.agents or [],
            "active_tag": getattr(cfg, "active_tag", "production"),
            "shadow_tag": getattr(cfg, "shadow_tag", "candidate"),
            "programs_dir": cfg.programs_dir,
            "datasets_dir": cfg.datasets_dir,
        },
        "package": {
            "installed": dspy_version is not None,
            "version": dspy_version,
        },
        "programs": programs,
        "datasets": datasets,
        "ready": cfg.enabled and dspy_version is not None,
    }
