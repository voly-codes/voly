"""CombatSupervisor — enrich combat missions with executor/model/skills from catalog."""

from __future__ import annotations

from pathlib import Path

from codeops.catalog.routing import get_mission_plan, resolve_model
from codeops.catalog.types import MissionPlan, MissionStepSpec
from codeops.catalog.zen_sync import fetch_zen_models
from codeops.catalog.store import save_models

SUPERVISOR_MODEL = "claude-opus-4-8"


class CombatSupervisor:
    """Builds MissionPlan and skill-augmented system prompts for combat runs."""

    def __init__(self, project_path: str, codeops_root: Path | None = None):
        self.project_path = Path(project_path)
        self.codeops_root = codeops_root or Path(__file__).resolve().parents[2]

    def sync_catalog(self, *, push_remote: bool = False) -> int:
        models = fetch_zen_models()
        save_models(models, base=self.codeops_root)
        if push_remote:
            try:
                from codeops.catalog.client import CatalogClient

                client = CatalogClient.from_env()
                if client:
                    client.sync_models([m.to_dict() for m in models])
            except Exception:
                pass
        return len(models)

    def plan(self, mission_id: str) -> MissionPlan:
        steps = get_mission_plan(mission_id)
        if not steps:
            return MissionPlan(mission_id=mission_id, supervisor_model=SUPERVISOR_MODEL, steps=[])
        resolved = []
        for spec in steps:
            prefer_free = spec.readonly
            model = resolve_model(
                spec.executor,
                spec.model,
                catalog_base=self.codeops_root,
                prefer_free=prefer_free,
            )
            if spec.readonly and spec.free_fallback_model:
                model = resolve_model(
                    spec.executor,
                    spec.free_fallback_model,
                    catalog_base=self.codeops_root,
                    prefer_free=True,
                )
            resolved.append(
                MissionStepSpec(
                    executor=spec.executor,
                    model=model,
                    agent_role=spec.agent_role,
                    skills=list(spec.skills),
                    readonly=spec.readonly,
                    free_fallback_model=spec.free_fallback_model,
                )
            )
        return MissionPlan(
            mission_id=mission_id,
            supervisor_model=SUPERVISOR_MODEL,
            steps=resolved,
        )

    def skills_prompt(self, skill_ids: list[str]) -> str:
        if not skill_ids:
            return ""
        parts: list[str] = []
        search_dirs = [
            self.project_path / ".claude" / "skills",
            self.codeops_root / ".codeops" / "skills",
            self.codeops_root.parent / ".claude" / "skills",
        ]
        for sid in skill_ids:
            found = False
            for base in search_dirs:
                for ext in (".md", ".yaml", ".yml"):
                    path = base / f"{sid}{ext}"
                    if path.is_file():
                        text = path.read_text(encoding="utf-8")[:6000]
                        parts.append(f"### Skill: {sid}\n{text}")
                        found = True
                        break
                if found:
                    break
            if not found:
                parts.append(f"### Skill: {sid}\n(apply project conventions for {sid})")
        return "\n\n".join(parts)

    def build_system_prompt(self, base_system: str, spec: MissionStepSpec) -> str:
        extra = self.skills_prompt(spec.skills)
        readonly = (
            "\n\nREADONLY MODE: Do NOT edit or create files. Review and report only."
            if spec.readonly
            else ""
        )
        model_note = f"\nAssigned model: {spec.model} via executor {spec.executor}."
        if not extra:
            return f"{base_system.strip()}{model_note}{readonly}"
        return f"{base_system.strip()}\n\n---\n\n# Loaded skills\n\n{extra}{model_note}{readonly}"
