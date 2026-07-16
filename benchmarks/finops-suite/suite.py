"""Load and validate the FinOps benchmark suite (BO002 Phase 1–2)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUITE_DIR = Path(__file__).resolve().parent
TASKS_PATH = SUITE_DIR / "tasks.yaml"
FIXTURE_DIR = SUITE_DIR / "fixture_project"
RESULTS_DIR = SUITE_DIR / "results"

REQUIRED_TASK_KEYS = ("id", "category", "prompt", "expected_files", "scenarios", "mock")
VALID_SCENARIOS = frozenset({"baseline", "voly_chain", "billing_fallback"})


@dataclass
class MockSpec:
    billing_fail_executors: list[str]
    succeed_executor: str
    costs_usd: dict[str, float]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MockSpec:
        return cls(
            billing_fail_executors=list(data.get("billing_fail_executors") or []),
            succeed_executor=str(data["succeed_executor"]),
            costs_usd={str(k): float(v) for k, v in (data.get("costs_usd") or {}).items()},
        )


@dataclass
class BenchTask:
    id: str
    category: str
    prompt: str
    expected_files: list[str]
    size: str
    scenarios: list[str]
    mock: MockSpec
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class BenchSuite:
    version: int
    suite_id: str
    claims: list[str]
    billing_fallback_chain: list[str]
    tasks: list[BenchTask]
    path: Path = TASKS_PATH

    def task_ids(self) -> list[str]:
        return [t.id for t in self.tasks]

    def by_id(self, task_id: str) -> BenchTask:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)


def load_suite(path: Path | None = None) -> BenchSuite:
    """Parse tasks.yaml and run structural validation."""
    tasks_path = path or TASKS_PATH
    data = yaml.safe_load(tasks_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{tasks_path}: root must be a mapping")

    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError(f"{tasks_path}: tasks must be a non-empty list")

    tasks: list[BenchTask] = []
    seen: set[str] = set()
    for i, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            raise ValueError(f"tasks[{i}]: must be a mapping")
        for key in REQUIRED_TASK_KEYS:
            if key not in item:
                raise ValueError(f"tasks[{i}]: missing required key {key!r}")
        tid = str(item["id"])
        if tid in seen:
            raise ValueError(f"duplicate task id: {tid}")
        seen.add(tid)

        scenarios = [str(s) for s in item["scenarios"]]
        unknown = set(scenarios) - VALID_SCENARIOS
        if unknown:
            raise ValueError(f"task {tid}: unknown scenarios {sorted(unknown)}")

        expected = [str(p) for p in item["expected_files"]]
        for rel in expected:
            if not (FIXTURE_DIR / rel).exists():
                raise ValueError(
                    f"task {tid}: expected_files entry {rel!r} missing under fixture_project/"
                )

        mock = MockSpec.from_dict(item["mock"])
        if not mock.succeed_executor:
            raise ValueError(f"task {tid}: mock.succeed_executor required")
        if mock.succeed_executor not in mock.costs_usd:
            raise ValueError(
                f"task {tid}: costs_usd must include succeed_executor "
                f"{mock.succeed_executor!r}"
            )
        for ex in mock.billing_fail_executors:
            if ex not in mock.costs_usd:
                raise ValueError(f"task {tid}: costs_usd missing billing fail executor {ex!r}")

        prompt = str(item["prompt"]).strip()
        if len(prompt) < 10:
            raise ValueError(f"task {tid}: prompt too short")

        tasks.append(
            BenchTask(
                id=tid,
                category=str(item["category"]),
                prompt=prompt,
                expected_files=expected,
                size=str(item.get("size") or "xs"),
                scenarios=scenarios,
                mock=mock,
                notes=str(item.get("notes") or "").strip(),
                raw=item,
            )
        )

    if len(tasks) < 5:
        raise ValueError(f"suite must have ≥5 tasks, got {len(tasks)}")

    chain = [str(x) for x in (data.get("billing_fallback_chain") or [])]
    if len(chain) < 2:
        raise ValueError("billing_fallback_chain must list ≥2 executors (cross-vendor)")

    return BenchSuite(
        version=int(data.get("version") or 1),
        suite_id=str(data.get("suite_id") or "finops"),
        claims=[str(c) for c in (data.get("claims") or [])],
        billing_fallback_chain=chain,
        tasks=tasks,
        path=tasks_path,
    )


def materialize_fixture(dest: Path, *, clean: bool = True) -> Path:
    """Copy fixture_project into dest (temp cwd for a run)."""
    dest = Path(dest)
    if clean and dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE_DIR, dest, dirs_exist_ok=True)
    return dest


def inventory(suite: BenchSuite) -> dict[str, Any]:
    """JSON-serializable suite inventory for mock smoke / CI."""
    return {
        "suite_id": suite.suite_id,
        "version": suite.version,
        "claims": suite.claims,
        "billing_fallback_chain": suite.billing_fallback_chain,
        "task_count": len(suite.tasks),
        "task_ids": suite.task_ids(),
        "categories": sorted({t.category for t in suite.tasks}),
        "billing_fallback_tasks": [
            t.id for t in suite.tasks if "billing_fallback" in t.scenarios
        ],
        "cross_vendor_mock_tasks": [
            t.id
            for t in suite.tasks
            if len(set(t.mock.billing_fail_executors) | {t.mock.succeed_executor}) >= 2
        ],
    }
