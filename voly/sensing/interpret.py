"""Strict Signal-to-Option interpretation through the existing DSPyRunner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from voly.router import RouteDecision
from voly.sensing.schema import Option, Signal, SensingValidationError
from voly.sensing.store import SignalStore

MAX_OPTIONS_PER_SIGNAL = 5
MAX_SIGNAL_JSON_CHARS = 20_000


@dataclass(frozen=True)
class InterpretationResult:
    signal_id: str
    options: list[Option]
    dspy_used: bool
    error: str = ""
    plan_ids: tuple[str, ...] = ()


def _parse_options(signal: Signal, raw: Any) -> list[Option]:
    if not isinstance(raw, str):
        raise SensingValidationError("analyst options_json must be a string")
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
            if text.startswith("json"):
                text = text[4:].lstrip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SensingValidationError("analyst returned invalid options JSON") from exc
    if not isinstance(payload, list) or not 1 <= len(payload) <= MAX_OPTIONS_PER_SIGNAL:
        raise SensingValidationError("analyst must return between 1 and 5 options")

    options: list[Option] = []
    seen: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise SensingValidationError("each analyst option must be an object")
        option_id = str(item.get("option_id") or f"{signal.signal_id}-opt-{index}")
        if option_id in seen:
            raise SensingValidationError(f"duplicate option_id: {option_id!r}")
        seen.add(option_id)
        options.append(Option(
            option_id=option_id,
            signal_id=signal.signal_id,
            title=str(item.get("title") or "").strip(),
            rationale=str(item.get("rationale") or "").strip(),
            urgency=str(item.get("urgency") or "").strip().lower(),
            estimated_impact=str(item.get("estimated_impact") or "").strip(),
            action_kind=str(item.get("action_kind") or "").strip().lower(),
            action_spec=dict(item.get("action_spec") or {}),
        ))
        if not options[-1].title:
            raise SensingValidationError("analyst option title is required")
    return options


class SignalInterpreter:
    """Run the registered analyst program without bypassing AIGateway."""

    def __init__(self, config: Any, *, gateway: Any = None, runner: Any = None) -> None:
        self.config = config
        self._gateway = gateway
        self._runner = runner

    def _build_gateway(self) -> Any:
        from voly.ai_gateway import AIGateway

        cfg = self.config.ai_gateway
        gateway = AIGateway(
            account_id=cfg.account_id,
            gateway_id=cfg.gateway_id,
            api_token=cfg.api_token,
        )
        gateway._enabled = cfg.enabled
        gateway.cache.enabled = cfg.cache_enabled
        gateway.cache.ttl_seconds = cfg.cache_ttl_seconds
        gateway.cache.max_entries = cfg.cache_max_entries
        gateway.cache.persist_dir = cfg.cache_persist_dir
        gateway.rate_limit.enabled = cfg.rate_limits_enabled
        gateway.rate_limit.requests_per_minute = cfg.rate_requests_per_minute
        gateway.spend_limit.enabled = cfg.spend_limits_enabled
        gateway.spend_limit.daily_budget_usd = cfg.spend_daily_budget_usd
        gateway.spend_limit.per_agent_budget = cfg.spend_per_agent_budget
        gateway.fallback.enabled = cfg.fallback_enabled
        gateway.fallback.chain = cfg.fallback_chain
        gateway.fallback.retries = cfg.fallback_retries
        gateway.dlp.enabled = cfg.dlp_enabled
        gateway.dlp.block_secrets = cfg.dlp_block_secrets
        gateway.dlp.block_pii = cfg.dlp_block_pii
        gateway.upstream = cfg.upstream
        gateway.upstream_model = cfg.upstream_model
        gateway.upstream_fallback_direct = cfg.upstream_fallback_direct
        gateway.byok_enabled = cfg.byok_enabled
        gateway.byok_providers = list(cfg.byok_providers)
        gateway.request_timeout_seconds = cfg.request_timeout_seconds
        gateway.request_total_timeout_seconds = cfg.request_total_timeout_seconds
        return gateway

    def interpret(self, signal: Signal, *, store: SignalStore | None = None) -> InterpretationResult:
        if not self.config.sensing.enabled or self.config.sensing.mode not in {"shadow", "active"}:
            return InterpretationResult(signal.signal_id, [], False, "sensing is not enabled")
        if not self.config.dspy.enabled or self.config.dspy.mode == "off":
            return InterpretationResult(signal.signal_id, [], False, "DSPy is not enabled")

        if self._runner is None:
            from voly.dspy.runner import DSPyRunner

            gateway = self._gateway or self._build_gateway()
            self._runner = DSPyRunner(self.config, gateway)

        model_name = self.config.dspy.model or self.config.default_model
        model_config = self.config.get_model_config(model_name)
        route = RouteDecision(
            agent="analyst",
            model=model_config.model or model_name,
            provider=self.config.dspy.provider or model_config.provider,
        )
        signal_json = json.dumps(signal.to_dict(), ensure_ascii=False, sort_keys=True)
        if len(signal_json) > MAX_SIGNAL_JSON_CHARS:
            return InterpretationResult(signal.signal_id, [], False, "Signal exceeds analyst input limit")
        result = self._runner.run(signal_json, [], route, route.model)
        if result is None or not result.dspy_used:
            return InterpretationResult(
                signal.signal_id,
                [],
                False,
                str(getattr(result, "error", None) or "analyst DSPy run did not complete"),
            )
        try:
            options = _parse_options(signal, result.structured.get("options_json"))
        except (SensingValidationError, ValueError) as exc:
            return InterpretationResult(signal.signal_id, [], True, str(exc))
        (store or SignalStore(self.config.sensing.store_dir)).save_options(signal, options)
        plan_ids: list[str] = []
        if self.config.sensing.mode == "active":
            from voly.decisions import DecisionService
            from voly.plan.store import PlanStore

            rank = {"low": 0, "medium": 1, "high": 2}
            threshold = rank[self.config.sensing.min_urgency_for_decision]
            service = DecisionService(PlanStore(self.config.plan.store_dir))
            for option in options:
                if option.action_kind != "ignore" and rank[option.urgency] >= threshold:
                    plan_ids.append(service.create(signal, option).plan_id)
        return InterpretationResult(signal.signal_id, options, True, plan_ids=tuple(plan_ids))
