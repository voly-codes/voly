"""Local multi-agent execution: a strong lead orchestrator assigns a model tier
and skills to each decomposed sub-agent, then each sub-agent runs in-process
through ``AIGateway.chat()``.

Flow (used by the pipeline's A2A auto-dispatch when ``a2a.execution_mode == 'local'``):

    task → TaskDecomposer → [architect, developer, tester, reviewer, devops]
         → LeadOrchestrator.assign()   # strong model picks tier + skills per role
         → run_local()                 # each role → AIGateway.chat(model=tier, skills)
         → per-agent results + merged report + telemetry assignments

The model pool is the set of *real* configured providers (``router._PROVIDER_MODELS``)
filtered by ``ProviderHealthChecker`` — strong = anthropic/claude, weak = the free/cheap
providers (workers-ai, deepseek, opencode-zen, mimo, omniroute).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from codeops.ai_gateway.health import get_checker
from codeops.router import _PROVIDER_MODELS

_log = logging.getLogger("codeops.a2a.multiagent")

# ── Model tiers → ordered real-provider preference (filtered by health) ──────────
_STRONG = ["anthropic", "cloudflare-dynamic"]
_STANDARD = ["cloudflare-dynamic", "deepseek", "anthropic", "workers-ai"]
_WEAK = ["workers-ai", "deepseek", "opencode-zen", "mimo", "omniroute"]

_TIER_PROVIDERS: dict[str, list[str]] = {
    "premium": _STRONG,
    "strong": _STRONG,
    "standard": _STANDARD,
    "cheap": _WEAK,
    "weak": _WEAK,
    "free": _WEAK,
}

# Role → default tier (fallback when the lead orchestrator is unavailable) + persona.
_ROLE_TIER: dict[str, str] = {
    "architect": "premium",
    "developer": "standard",
    "tester": "cheap",
    "reviewer": "premium",
    "devops": "cheap",
    "security": "premium",
}

_ROLE_PROMPT: dict[str, str] = {
    "architect": "Ты senior software architect. Спроектируй архитектуру: модули, "
                 "интерфейсы, поток данных, ключевые решения и риски. Кратко и по делу.",
    "developer": "Ты senior developer. Реализуй решение на основе архитектуры выше. "
                 "Выдай рабочий код с краткими пояснениями.",
    "tester": "Ты QA-инженер. Напиши тесты (pytest, если Python) для реализации выше — "
              "happy-path, граничные и негативные случаи.",
    "reviewer": "Ты code reviewer. Оцени код и тесты выше: баги, безопасность, читаемость, "
                "производительность. Дай конкретные замечания и вердикт.",
    "devops": "Ты DevOps-инженер. Подготовь деплой для реализации выше: Dockerfile/compose, "
              "CI-шаги, переменные окружения, чек-лист релиза.",
    "security": "Ты application security engineer. Найди уязвимости в коде выше и предложи фиксы.",
}
_DEFAULT_PERSONA = "Ты профильный инженер. Выполни назначенную суб-задачу качественно и кратко."

_VALID_TIERS = ("premium", "standard", "cheap")


@dataclass
class Assignment:
    """A sub-agent with its lead-assigned model tier and skills."""
    idx: int
    role: str
    description: str
    depends_on: list[int]
    tier: str
    model: str
    provider: str
    skills: list[str] = field(default_factory=list)
    # filled after execution
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    ok: bool = False
    error: str = ""
    cache_hit: bool = False       # gateway response cache hit → 0 new tokens billed
    mem_hits: int = 0             # semantic-memory entries injected into this sub-agent
    saved_tokens: int = 0        # tokens saved by Headroom compression on this sub-agent

    def to_event_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "tier": self.tier,
            "model": self.model,
            "provider": self.provider,
            "skills": self.skills,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "ok": self.ok,
            "cache_hit": self.cache_hit,
            "mem_hits": self.mem_hits,
            "saved_tokens": self.saved_tokens,
        }


def _excluded_providers() -> set[str]:
    """Providers to skip when resolving a tier (e.g. out of credits).

    Set via CODEOPS_A2A_EXCLUDE_PROVIDERS="anthropic,openai" (comma-separated).
    """
    import os
    raw = os.environ.get("CODEOPS_A2A_EXCLUDE_PROVIDERS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


def resolve_tier_model(tier: str, checker: Any = None) -> tuple[str, str]:
    """Resolve a (model, provider) for the given tier from the healthy real pool."""
    checker = checker or get_checker()
    excluded = _excluded_providers()

    def _ok(provider: str) -> bool:
        return provider not in excluded and checker.check(provider).healthy

    for provider in _TIER_PROVIDERS.get(tier, _WEAK):
        if provider in _PROVIDER_MODELS and _ok(provider):
            return _PROVIDER_MODELS[provider]
    # No healthy provider in the requested tier → any healthy, non-excluded provider.
    for provider, pair in _PROVIDER_MODELS.items():
        if _ok(provider):
            _log.warning("tier %r: no healthy provider in tier, using %s", tier, pair[1])
            return pair
    # Last resort — anthropic (call will surface a clear auth error if unconfigured).
    return _PROVIDER_MODELS["anthropic"]


class LeadOrchestrator:
    """Strong lead agent that assigns a model tier + skills to each sub-agent."""

    def __init__(
        self,
        gateway: Any,
        skill_matcher: Callable[[str, str], list[Any]] | None = None,
        checker: Any = None,
        lead_model: str = "",
    ):
        self.gateway = gateway
        self.skill_matcher = skill_matcher
        self.checker = checker or get_checker()
        self.lead_model = lead_model

    def _candidate_skills(self, task: str, role: str) -> list[tuple[str, str]]:
        """Return [(skill_id, name)] candidates for a role, from the registry."""
        if not self.skill_matcher:
            return []
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for s in self.skill_matcher(task, role)[:6]:
            sid = getattr(s, "id", "")
            if sid and sid not in seen:
                seen.add(sid)
                out.append((sid, getattr(s, "name", sid)))
        return out

    def assign(self, task: str, subtasks: list[Any]) -> list[Assignment]:
        """Produce an Assignment per sub-task. LLM-lead first, deterministic fallback."""
        skill_candidates = {
            i: self._candidate_skills(task, st.agent) for i, st in enumerate(subtasks)
        }
        plan = self._ask_lead(task, subtasks, skill_candidates)
        assignments: list[Assignment] = []
        for i, st in enumerate(subtasks):
            entry = plan.get(i, {}) if plan else {}
            tier = entry.get("tier") or _ROLE_TIER.get(st.agent, "standard")
            if tier not in _VALID_TIERS:
                tier = _ROLE_TIER.get(st.agent, "standard")
            valid_ids = {sid for sid, _ in skill_candidates[i]}
            skills = [s for s in entry.get("skills", []) if s in valid_ids]
            if not skills:
                skills = [sid for sid, _ in skill_candidates[i][:2]]
            model, provider = resolve_tier_model(tier, self.checker)
            assignments.append(Assignment(
                idx=i, role=st.agent, description=st.description,
                depends_on=list(getattr(st, "depends_on", [])),
                tier=tier, model=model, provider=provider, skills=skills,
            ))
        return assignments

    def _ask_lead(
        self, task: str, subtasks: list[Any], skill_candidates: dict[int, list[tuple[str, str]]]
    ) -> dict[int, dict[str, Any]]:
        """Call a strong model to assign tier + skills. Returns {idx: {tier, skills}}."""
        model, provider = (
            (self.lead_model, _provider_for_model(self.lead_model))
            if self.lead_model else resolve_tier_model("premium", self.checker)
        )
        roles_block = "\n".join(
            f"{i}. role={st.agent}; task={st.description[:160]}; "
            f"skills_available={[sid for sid, _ in skill_candidates[i]] or 'none'}"
            for i, st in enumerate(subtasks)
        )
        system = (
            "Ты lead-оркестратор. Для каждой суб-задачи назначь уровень модели (tier) и "
            "релевантные скилы. Критерии: сложное проектирование/ревью/безопасность → "
            "'premium'; обычная реализация → 'standard'; рутинные тесты/деплой/батч → 'cheap'. "
            "Скилы выбирай ТОЛЬКО из skills_available каждой роли (можно пусто). "
            "Ответь СТРОГО JSON-массивом без пояснений: "
            '[{"idx":0,"tier":"premium","skills":["id1"]}, ...]'
        )
        user = f"Задача: {task}\n\nСуб-задачи:\n{roles_block}"
        try:
            resp = self.gateway.chat(
                [{"role": "user", "content": user}],
                model=model, provider_name=provider, system=system,
                agent="lead", max_tokens=1024, temperature=0.0,
            )
            content = resp.get("content", "") or ""
            if resp.get("error"):
                _log.warning("lead orchestrator error, using deterministic fallback: %s", resp["error"])
                return {}
            return _parse_plan(content)
        except Exception as e:  # noqa: BLE001 — fall back to deterministic assignment
            _log.warning("lead orchestrator call failed (%s), deterministic fallback", e)
            return {}


def _parse_plan(content: str) -> dict[int, dict[str, Any]]:
    """Extract the JSON array from the lead response into {idx: {tier, skills}}."""
    start, end = content.find("["), content.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        arr = json.loads(content[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    plan: dict[int, dict[str, Any]] = {}
    for item in arr if isinstance(arr, list) else []:
        if isinstance(item, dict) and "idx" in item:
            try:
                plan[int(item["idx"])] = {
                    "tier": item.get("tier"),
                    "skills": item.get("skills", []) if isinstance(item.get("skills"), list) else [],
                }
            except (TypeError, ValueError):
                continue
    return plan


def _provider_for_model(model: str) -> str:
    for _model, provider in _PROVIDER_MODELS.values():
        if _model == model:
            return provider
    return "anthropic"


def _skills_block(skill_ids: list[str], skill_matcher: Callable[[str, str], list[Any]] | None,
                  task: str, role: str) -> str:
    """Build a system-prompt block with the content of assigned skills."""
    if not skill_ids or not skill_matcher:
        return ""
    by_id = {getattr(s, "id", ""): s for s in skill_matcher(task, role)}
    parts: list[str] = []
    for sid in skill_ids:
        s = by_id.get(sid)
        content = getattr(s, "content", "") if s else ""
        if content and content.strip():
            parts.append(f"### {getattr(s, 'name', sid)} ({sid})\n{content.strip()[:3000]}")
    return ("# Loaded skills\n\n" + "\n\n".join(parts)) if parts else ""


def _memory_block(memory: Any, query: str, limit: int = 3) -> tuple[str, int]:
    """Retrieve semantic-memory entries relevant to a sub-task. Returns (block, hits)."""
    if memory is None:
        return "", 0
    try:
        entries = memory.search(query, limit=limit)
    except Exception as e:  # noqa: BLE001
        _log.warning("memory search failed: %s", e)
        return "", 0
    parts = [f"- [{getattr(m, 'category', '?')}] {getattr(m, 'title', '')}: "
             f"{(getattr(m, 'content', '') or '')[:600]}" for m in entries]
    if not parts:
        return "", 0
    return "# Relevant prior context (memory)\n" + "\n".join(parts), len(parts)


def run_local(
    task: str,
    assignments: list[Assignment],
    gateway: Any,
    skill_matcher: Callable[[str, str], list[Any]] | None = None,
    max_tokens: int = 4096,
    *,
    memory: Any = None,
    headroom: Any = None,
    temperature: float = 0.0,
) -> list[Assignment]:
    """Execute each sub-agent in dependency order via AIGateway.chat().

    Cost/token savings on the multi-agent path:
      - **temperature=0.0** → deterministic chain → the gateway response cache hits
        on repeat runs of the same task (each sub-agent billed 0 new tokens).
      - **memory** (MemoryStore-like): relevant prior context injected per sub-agent
        and each result stored back → cross-task reuse.
      - **headroom** (optional, when the proxy runs): compresses the sub-agent prompt.

    Sub-tasks are processed in dependency order; each dependent agent receives prior
    agents' outputs. Mutates and returns the assignments with usage/cost/savings.
    """
    from codeops.a2a.decomposer import TaskDecomposer
    from codeops.telemetry import _estimate_cost

    done: dict[int, Assignment] = {}
    for a in assignments:
        prior = [(done[d].role, done[d].content) for d in a.depends_on if d in done and done[d].ok]
        user = TaskDecomposer.inject_prior_context(a.description, prior)

        mem_block, a.mem_hits = _memory_block(memory, f"{a.role}: {a.description}")
        if mem_block:
            user = f"{mem_block}\n\n{user}"

        persona = _ROLE_PROMPT.get(a.role, _DEFAULT_PERSONA)
        skills = _skills_block(a.skills, skill_matcher, task, a.role)
        system = f"{persona}\n\n{skills}".strip() if skills else persona

        messages = [{"role": "user", "content": user}]
        if headroom is not None:
            try:
                if headroom.is_running():
                    res = headroom.compress(messages, model=a.model)
                    messages = res.get("messages", messages)
                    a.saved_tokens = res.get("tokens_saved", 0)
            except Exception as e:  # noqa: BLE001
                _log.debug("headroom compress skipped: %s", e)

        _log.info("multiagent[%d] %s → %s/%s (tier=%s, skills=%s, mem=%d)",
                  a.idx, a.role, a.provider, a.model, a.tier, a.skills, a.mem_hits)
        try:
            resp = gateway.chat(
                messages,
                model=a.model, provider_name=a.provider, system=system,
                agent=a.role, max_tokens=max_tokens, temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            a.error = str(e)
            a.content = f"(failed: {e})"
            done[a.idx] = a
            continue

        if resp.get("error"):
            a.error = str(resp["error"])
            a.content = f"(failed: {a.error})"
        else:
            a.content = resp.get("content", "") or ""
            usage = resp.get("usage", {}) or {}
            a.input_tokens = usage.get("input_tokens", 0)
            a.output_tokens = usage.get("output_tokens", 0)
            a.cache_hit = bool(resp.get("cache_hit"))
            # Cache hit = 0 new tokens billed → no cost this run.
            a.cost_usd = 0.0 if a.cache_hit else _estimate_cost(
                resp.get("model", a.model), a.input_tokens, a.output_tokens)
            a.ok = bool(a.content.strip())
            if a.ok and memory is not None and not a.cache_hit:
                try:
                    memory.add(
                        title=f"[{a.role}] {a.description[:80]}",
                        content=a.content[:2000], category="history",
                        metadata={"role": a.role, "model": a.model, "provider": a.provider,
                                  "task": task[:200]},
                        importance=0.5, tags=[a.role, "a2a"],
                    )
                except Exception as e:  # noqa: BLE001
                    _log.debug("memory store skipped for %s: %s", a.role, e)
        done[a.idx] = a
    return assignments


def merge_report(task: str, assignments: list[Assignment]) -> str:
    """Human-readable merged report: what each agent (model/tier) produced."""
    lines = [f"# Multi-agent result: {task[:120]}", ""]
    for a in assignments:
        status = "✓" if a.ok else "✗"
        skills = ", ".join(a.skills) if a.skills else "—"
        lines.append(
            f"## [{a.role}] {status}  ·  {a.provider}/{a.model} (tier={a.tier})  ·  skills: {skills}"
        )
        lines.append("")
        lines.append(a.content.strip() or "(no output)")
        lines.append("\n---\n")
    return "\n".join(lines).strip()
