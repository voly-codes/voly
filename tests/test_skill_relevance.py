"""Skill relevance filtering: installed ≠ always injected (P1 skills gate)."""

from __future__ import annotations

from voly.pipeline.skills import _SkillsMixin
from voly.registry.skills import Skill, SkillSource


class _FakeRegistry:
    def __init__(self, skills: list[Skill]):
        self._skills = skills

    def search(self, **kwargs) -> list[Skill]:
        source = kwargs.get("source")
        agent = kwargs.get("agent")
        query = kwargs.get("query")
        out = []
        for s in self._skills:
            if source is not None and s.source != source:
                continue
            if agent is not None and agent not in (s.compatible_agents or []):
                continue
            if query is not None:
                hay = " ".join([s.name, s.description, *s.tags]).lower()
                if query.lower() not in hay:
                    continue
            if kwargs.get("language") is not None and kwargs["language"].lower() not in [
                x.lower() for x in s.compatible_languages
            ]:
                continue
            if kwargs.get("framework") is not None and kwargs["framework"].lower() not in [
                x.lower() for x in s.compatible_frameworks
            ]:
                continue
            out.append(s)
        return out


class _ScannerCfg:
    enabled = False


class _Cfg:
    scanner = _ScannerCfg()


class _Harness(_SkillsMixin):
    def __init__(self, skills: list[Skill]):
        self.skill_registry = _FakeRegistry(skills)
        self.config = _Cfg()

    def scan_project(self):  # scanner disabled — never called
        raise AssertionError("scan_project should not be called")


def _skill(sid: str, source: SkillSource, *, tags=None, agents=None, langs=None) -> Skill:
    return Skill(
        id=sid,
        name=sid.replace("-", " "),
        description=f"{sid} description",
        source=source,
        tags=list(tags or []),
        compatible_agents=list(agents or []),
        compatible_languages=list(langs or []),
        content="body",
    )


TASK = "Implement a FastAPI endpoint returning mission statistics and add pytest tests"


def test_unrelated_installed_marketplace_skill_is_dropped() -> None:
    noise = _skill("marketing-ops", SkillSource.MARKETPLACE,
                   tags=["marketing", "campaigns"], agents=["developer"])
    got = _Harness([noise]).match_skills_for_task(TASK, agent_name="developer")
    assert got == []


def test_marketplace_skill_with_task_keywords_kept() -> None:
    # Uncurated sources need two signals — two task keywords here.
    relevant = _skill("fastapi-patterns", SkillSource.MARKETPLACE, tags=["fastapi", "pytest"])
    noise = _skill("board-deck", SkillSource.MARKETPLACE, tags=["slides"])
    got = _Harness([relevant, noise]).match_skills_for_task(TASK, agent_name="developer")
    assert [s.id for s in got] == ["fastapi-patterns"]


def test_single_generic_keyword_not_enough_for_org_skill() -> None:
    """Regression: cfo-review leaked into a DELETE-endpoint task via the word 'review'."""
    cfo = Skill(
        id="cfo-review", name="cfo-review",
        description="Numerate-skeptic interrogation of any plan that touches money",
        source=SkillSource.ORGANIZATION, tags=["finance"], content="body",
    )
    karpathy = Skill(
        id="karpathy-coder", name="karpathy-coder",
        description="Use when writing, reviewing, or committing code",
        source=SkillSource.ORGANIZATION, tags=[], content="body",
    )
    task = "Add a DELETE endpoint with authorization checks, write pytest tests, review the changes"
    got = _Harness([cfo, karpathy]).match_skills_for_task(task, agent_name="developer")
    assert got == []


def test_substring_does_not_count_as_keyword_hit() -> None:
    """'write' must not match 'writing' — token boundaries only."""
    s = Skill(
        id="writing-guide", name="writing guide",
        description="prose writing style guide", source=SkillSource.MARKETPLACE,
        tags=["writing"], content="body",
    )
    got = _Harness([s]).match_skills_for_task("write pytest tests for the endpoint")
    assert got == []


def test_project_source_skill_always_kept() -> None:
    proj = _skill("project-conventions", SkillSource.PROJECT, tags=["anything"])
    got = _Harness([proj]).match_skills_for_task("totally unrelated words here")
    assert [s.id for s in got] == ["project-conventions"]


def test_builtin_agent_skill_kept_without_keywords() -> None:
    builtin = _skill("skill-testing", SkillSource.BUILTIN, tags=["quality"], agents=["tester"])
    got = _Harness([builtin]).match_skills_for_task("fix the flaky thing", agent_name="tester")
    assert [s.id for s in got] == ["skill-testing"]


def test_frontend_skills_not_injected_on_python_backend_task() -> None:
    """Monorepo TypeScript/ui must not leak nextjs/svelte into FastAPI work."""

    class _Profile:
        languages = [type("L", (), {"name": "TypeScript"})(), type("L", (), {"name": "Python"})()]
        frameworks = [type("F", (), {"name": "Svelte"})(), type("F", (), {"name": "FastAPI"})()]

    class _ScanHarness(_Harness):
        def __init__(self, skills):
            super().__init__(skills)
            self.config = type("C", (), {"scanner": type("S", (), {"enabled": True})()})()

        def scan_project(self):
            return _Profile()

    nextjs = Skill(
        id="skill-nextjs",
        name="Next.js Development",
        description="Next.js App Router",
        source=SkillSource.BUILTIN,
        tags=["nextjs", "react", "frontend"],
        capabilities=["frontend"],
        compatible_agents=["developer", "architect"],
        compatible_languages=["typescript", "javascript"],
        compatible_frameworks=["nextjs", "react"],
        content="body",
    )
    svelte = Skill(
        id="svelte-frontend",
        name="svelte-frontend",
        description="Svelte and React UI",
        source=SkillSource.MARKETPLACE,
        tags=["frontend", "svelte", "react", "typescript", "ui"],
        compatible_agents=["developer"],
        compatible_languages=["typescript", "javascript"],
        compatible_frameworks=["svelte", "react"],
        content="body",
    )
    fastapi = _skill(
        "fastapi-patterns", SkillSource.MARKETPLACE,
        tags=["fastapi", "pytest"], agents=["developer"], langs=["python"],
    )
    h = _ScanHarness([nextjs, svelte, fastapi])
    got = {s.id for s in h.match_skills_for_task(TASK, agent_name="developer")}
    assert "skill-nextjs" not in got
    assert "svelte-frontend" not in got
    assert "fastapi-patterns" in got


def test_frontend_skill_kept_when_task_mentions_ui() -> None:
    nextjs = Skill(
        id="skill-nextjs",
        name="Next.js Development",
        description="Next.js App Router react frontend",
        source=SkillSource.BUILTIN,
        tags=["nextjs", "react", "frontend"],
        capabilities=["frontend"],
        compatible_agents=["developer"],
        compatible_languages=["typescript"],
        compatible_frameworks=["nextjs", "react"],
        content="body",
    )
    got = _Harness([nextjs]).match_skills_for_task(
        "Build a Next.js react frontend dashboard page",
        agent_name="developer",
    )
    assert [s.id for s in got] == ["skill-nextjs"]


def test_lead_respects_explicit_empty_skill_choice() -> None:
    from voly.a2a.decomposer import Subtask
    from voly.a2a.lead import LeadOrchestrator

    class _Gw:
        def chat(self, messages, *, model, provider_name, agent=None, **k):
            # Lead answers and deliberately assigns no skills.
            return {"content": '[{"idx":0,"tier":"standard","skills":[]}]',
                    "usage": {"input_tokens": 1, "output_tokens": 1}}

    cand = _skill("fastapi-patterns", SkillSource.MARKETPLACE, tags=["fastapi"])
    lead = LeadOrchestrator(gateway=_Gw(), skill_matcher=lambda task, role: [cand])
    assignments = lead.assign(TASK, [Subtask("implement", "developer")])
    assert assignments[0].skills == []


def test_lead_deterministic_fallback_still_injects_candidates() -> None:
    from voly.a2a.decomposer import Subtask
    from voly.a2a.lead import LeadOrchestrator

    class _DeadGw:
        def chat(self, *a, **k):
            raise RuntimeError("lead unavailable")

    cand = _skill("fastapi-patterns", SkillSource.MARKETPLACE, tags=["fastapi"])
    lead = LeadOrchestrator(gateway=_DeadGw(), skill_matcher=lambda task, role: [cand])
    assignments = lead.assign(TASK, [Subtask("implement", "developer")])
    assert assignments[0].skills == ["fastapi-patterns"]


def test_markdown_skills_do_not_attach_to_every_role_via_generic_words() -> None:
    """Regression: md-review / markdown-html leaked onto FastAPI A2A roles."""
    md = Skill(
        id="md-review",
        name="md-review",
        description="Review markdown and code documentation quality",
        source=SkillSource.ORGANIZATION,
        tags=["markdown", "review", "code"],
        compatible_agents=["documenter", "reviewer"],
        content="body",
    )
    html = Skill(
        id="markdown-html-orchestrator",
        name="markdown html",
        description="Transform markdown writing into HTML",
        source=SkillSource.ORGANIZATION,
        tags=["markdown", "html", "writing"],
        compatible_agents=["documenter"],
        content="body",
    )
    fastapi = _skill(
        "fastapi-patterns", SkillSource.MARKETPLACE,
        tags=["fastapi", "pytest"], agents=["developer"],
    )
    h = _Harness([md, html, fastapi])
    for role in ("architect", "developer", "tester", "devops"):
        got = {s.id for s in h.match_skills_for_task(TASK, agent_name=role)}
        assert "md-review" not in got
        assert "markdown-html-orchestrator" not in got
    assert [s.id for s in h.match_skills_for_task(TASK, agent_name="developer")] == [
        "fastapi-patterns"
    ]


def test_scout_filters_suggestions_without_task_overlap(monkeypatch) -> None:
    from voly.registry import scout as scout_mod
    from voly.registry.scout import SkillScout

    class _MP:
        def __init__(self, url):
            pass

        def search(self, query, limit=10):
            return {"skills": [
                {"id": "fastapi-patterns", "name": "FastAPI patterns",
                 "description": "REST endpoint recipes", "tags": ["fastapi"]},
                {"id": "board-deck", "name": "Board deck",
                 "description": "Investor slides", "tags": ["slides"]},
            ]}

    class _Index:
        def list_all(self):
            return []

    class _Reg:
        index = _Index()

    import voly.registry.marketplace as mp_mod
    monkeypatch.setattr(mp_mod, "MarketplaceClient", _MP)
    scout = SkillScout(_Reg(), "https://marketplace.example")
    got = scout.find_missing(TASK)
    assert [s["id"] for s in got] == ["fastapi-patterns"]
    _ = scout_mod

def test_lead_auto_mode_skips_llm_for_standard_roles() -> None:
    from voly.a2a.decomposer import Subtask
    from voly.a2a.lead import LeadOrchestrator

    calls = []

    class _Gw:
        def chat(self, *a, **k):
            calls.append(k.get("agent"))
            return {"content": "[]", "usage": {}}

    lead = LeadOrchestrator(gateway=_Gw(), skill_matcher=None, lead_mode="auto")
    subs = [
        Subtask("plan", "architect"),
        Subtask("impl", "developer", depends_on=[0]),
        Subtask("test", "tester", depends_on=[0, 1]),
    ]
    assignments = lead.assign("build service", subs)
    assert calls == []  # no premium lead chat for a standard decomposition
    # architect tier changed to "standard" (P4: avoid Anthropic lock-in for plan-only role)
    assert [a.tier for a in assignments] == ["standard", "standard", "standard"]


def test_lead_auto_mode_asks_llm_for_unknown_role() -> None:
    from voly.a2a.decomposer import Subtask
    from voly.a2a.lead import LeadOrchestrator

    calls = []

    class _Gw:
        def chat(self, *a, **k):
            calls.append(k.get("agent"))
            return {"content": "[]", "usage": {}}

    lead = LeadOrchestrator(gateway=_Gw(), skill_matcher=None, lead_mode="auto")
    lead.assign("build", [Subtask("analyze data", "data-scientist")])
    assert calls == ["lead"]


def test_lead_deterministic_mode_never_calls_llm() -> None:
    from voly.a2a.decomposer import Subtask
    from voly.a2a.lead import LeadOrchestrator

    class _Gw:
        def chat(self, *a, **k):
            raise AssertionError("must not be called")

    lead = LeadOrchestrator(gateway=_Gw(), skill_matcher=None, lead_mode="deterministic")
    got = lead.assign("build", [Subtask("odd", "custom-role")])
    assert got[0].tier == "standard"
