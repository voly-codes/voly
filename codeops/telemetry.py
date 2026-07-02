"""
Task telemetry — замеры на задачу.

Каждый вызов pipeline.run() / runner эмитирует TaskEvent:
  1. Локальный JSON в `.codeops/events/<task_id>.json` (fallback + savings CLI)
  2. CF Pipelines HTTP ingest (если `CF_PIPELINE_TELEMETRY_ENDPOINT` задан)
  3. Прямой upload в R2 (legacy, пока pipeline не владеет хранилищем)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENT = "CodeOps/0.1 (+https://github.com/codeops)"

# Оценка стоимости по провайдеру/модели: (input_usd_per_1k, output_usd_per_1k)
_COST_RATES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4": (0.015, 0.075),
    "claude-opus-4-8": (0.015, 0.075),
    "claude-sonnet-4": (0.003, 0.015),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4": (0.00025, 0.00125),
    "claude-haiku-4-5": (0.00025, 0.00125),
    "claude-3-5-sonnet": (0.003, 0.015),
    "claude-3-opus": (0.015, 0.075),
    # OpenAI
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.010, 0.030),
    "o1": (0.015, 0.060),
    "o3-mini": (0.0011, 0.0044),
    # DeepSeek
    "deepseek-v4-flash": (0.00027, 0.0011),
    "deepseek-v4-pro": (0.00054, 0.0022),
    "deepseek-chat": (0.00027, 0.0011),
    "deepseek-coder": (0.00027, 0.0011),
    # Google
    "gemini-1.5-pro": (0.00125, 0.005),
    "gemini-1.5-flash": (0.000075, 0.0003),
    "gemini-2.0-flash": (0.000075, 0.0003),
    # MiMo
    "mimo-v2.5-pro": (0.001, 0.003),
    "mimo-v2.5": (0.0005, 0.0015),
    # OpenCode Go (subscription; approximate per-token equivalents)
    "kimi-k2.6": (0.0005, 0.002),
    "kimi-k2.7-code": (0.0007, 0.003),
    "qwen3.7-plus": (0.0003, 0.0012),
    "qwen3.7-max": (0.0008, 0.0032),
    "minimax-m3": (0.0006, 0.0024),
    "glm-5.2": (0.0004, 0.0016),
    # OpenCode Zen (real pay-per-use pricing from opencode.ai/docs/zen/)
    "gpt-5.5": (0.005, 0.030),
    "gpt-5.4": (0.0025, 0.015),
    "gpt-5.4-mini": (0.00075, 0.0045),
    "gemini-3.5-flash": (0.0015, 0.009),
    "grok-build-0.1": (0.001, 0.002),
    # Cloudflare Workers AI (https://developers.cloudflare.com/workers-ai/platform/pricing/)
    # ~$0.011–0.028 per million tokens; many models free within daily neuron quota
    "@cf/meta/llama-4": (0.000028, 0.000028),
    "@cf/meta/llama-3": (0.000022, 0.000022),
    "@cf/mistral/mistral": (0.000011, 0.000011),
    "@cf/google/gemma": (0.000015, 0.000015),
    "@cf/qwen/qwen": (0.000015, 0.000015),
    "@cf/deepseek-ai/deepseek": (0.000018, 0.000018),
}

_DEFAULT_RATE = (0.001, 0.003)  # fallback если модель неизвестна

# Бесплатные модели OpenCode Zen — всегда $0.00 независимо от токенов
_FREE_MODELS: frozenset[str] = frozenset({
    # OpenCode Zen free tier
    "big-pickle",
    "deepseek-v4-flash-free",
    "mimo-v2.5-free",
    "north-mini-code-free",
    "nemotron-3-ultra-free",
    # CF Workers AI — free within 10k neurons/day quota
    "@cf/meta/llama-3.2-1b-instruct",
    "@cf/meta/llama-3.2-3b-instruct",
    "@cf/meta/llama-3.1-8b-instruct-fp8",
    "@cf/ibm-granite/granite-4.0-h-micro",
})


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Оценивает стоимость запроса в USD."""
    if any(key in model for key in _FREE_MODELS):
        return 0.0
    rate_in, rate_out = _DEFAULT_RATE
    for key, rates in _COST_RATES.items():
        if model.startswith(key) or key in model:
            rate_in, rate_out = rates
            break
    return round(input_tokens / 1000 * rate_in + output_tokens / 1000 * rate_out, 6)


@dataclass
class TokenMetrics:
    input: int = 0
    output: int = 0
    saved_rtk: int = 0
    saved_headroom: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output

    @property
    def total_saved(self) -> int:
        return self.saved_rtk + self.saved_headroom


@dataclass
class GatewayMetrics:
    cache_hit: bool = False
    fallback_used: bool = False
    fallback_model: str = ""
    fallback_provider: str = ""
    fallback_reason: str = ""
    dlp_blocked: bool = False


@dataclass
class TaskEvent:
    task_id: str
    agent: str
    status: str  # completed | failed | budget_exceeded | dlp_blocked | rate_limited | spend_limited
    tokens: TokenMetrics = field(default_factory=TokenMetrics)
    gateway: GatewayMetrics = field(default_factory=GatewayMetrics)
    skill_ids: list[str] = field(default_factory=list)
    memory_hits: int = 0  # semantic-memory entries retrieved & injected for this task
    workflow: str | None = None
    routing_score: float = 0.0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    model: str = ""
    provider: str = ""
    executor: str = ""
    task_type: str | None = None
    automation_score: float = 0.0
    manual_steps_removed: int = 0
    error: str | None = None
    # DSPy optimizer fields
    dspy_enabled: bool = False
    dspy_used: bool = False       # True = DSPy executed and produced output (shadow: not returned to user)
    dspy_mode: str | None = None
    dspy_program_id: str | None = None
    dspy_program_version: int | None = None
    dspy_program_tag: str | None = None
    dspy_optimizer: str | None = None
    dspy_dataset: str | None = None
    dspy_compile_id: str | None = None
    dspy_score: float | None = None
    dspy_shadow_delta: float | None = None
    # Task content
    task_prompt: str | None = None      # original user task text (capped at 2000 chars)
    result: str | None = None           # LLM output text (capped at 8000 chars)
    stage_log: list[dict] = field(default_factory=list)  # [{stage, elapsed_ms}]
    report: dict | None = None          # WorkReport.to_dict() — mini work summary
    # Billing fallback chain log: present only when fallback was triggered.
    # Each entry: {executor, model, status, duration_ms, error}
    # status: "success" | "billing_error" | "not_available" | "skipped" | "failed"
    chain_timelog: list[dict] = field(default_factory=list)
    # A2A auto-dispatch fields
    a2a_dispatched: bool = False
    a2a_subtask_count: int = 0
    a2a_agents_used: list[str] = field(default_factory=list)
    # Per-sub-agent assignment plan from the lead orchestrator:
    # [{role, tier, model, provider, skills:[...], input_tokens, output_tokens, cost_usd, ok}]
    a2a_assignments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Flatten tokens/gateway для читаемости
        d["tokens"] = asdict(self.tokens)
        d["gateway"] = asdict(self.gateway)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def new_task_id() -> str:
    return str(uuid.uuid4())


class TelemetryDeliveryError(Exception):
    """Ошибка доставки события во внешнее хранилище (Pipeline / R2)."""


def _is_unresolved(s: str) -> bool:
    return "${" in s


def resolve_pipeline_endpoint(config_url: str = "") -> str:
    """URL ingest endpoint CF Pipelines из config или env."""
    url = os.path.expandvars((config_url or "").strip())
    if url and not _is_unresolved(url):
        return url.rstrip("/")
    for key in ("CF_PIPELINE_TELEMETRY_ENDPOINT", "PIPELINE_TELEMETRY_ENDPOINT"):
        env_url = os.environ.get(key, "").strip()
        if env_url:
            return env_url.rstrip("/")
    return ""


def resolve_pipeline_token() -> str:
    for key in ("CF_PIPELINE_TELEMETRY_TOKEN", "CLOUDFLARE_API_TOKEN"):
        token = os.environ.get(key, "").strip()
        if token:
            return token
    return ""


def event_to_pipeline_record(event: TaskEvent) -> dict[str, Any]:
    """Плоская запись для CF Pipelines SQL-трансформации."""
    record = event.to_dict()
    record["ts_us"] = int(time.time() * 1_000_000)
    record["tokens_input"] = event.tokens.input
    record["tokens_output"] = event.tokens.output
    record["tokens_saved_rtk"] = event.tokens.saved_rtk
    record["tokens_saved_headroom"] = event.tokens.saved_headroom
    record["cache_hit"] = event.gateway.cache_hit
    record["fallback_used"] = event.gateway.fallback_used
    record["dlp_blocked"] = event.gateway.dlp_blocked
    return record


def send_to_pipeline(
    endpoint: str,
    event: TaskEvent,
    *,
    timeout: float = 5.0,
    token: str | None = None,
) -> None:
    """POST TaskEvent в CF Pipelines ingest (JSON array batch of one)."""
    body = json.dumps([event_to_pipeline_record(event)], ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    auth = token if token is not None else resolve_pipeline_token()
    if auth:
        headers["Authorization"] = f"Bearer {auth}"

    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TelemetryDeliveryError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TelemetryDeliveryError(str(exc.reason)) from exc


def _write_local_event(event: TaskEvent, events_dir: str | Path) -> Path | None:
    try:
        target = Path(events_dir)
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{event.task_id}.json"
        path.write_text(event.to_json(), encoding="utf-8")
        return path
    except Exception as exc:
        logger.debug("telemetry: failed to write local event: %s", exc)
        return None


def emit_event(
    event: TaskEvent,
    events_dir: str | Path | None = None,
    *,
    pipeline_url: str | None = None,
    pipeline_enabled: bool = True,
    pipeline_timeout: float | None = None,
    r2_enabled: bool = True,
) -> Path | None:
    """Записывает TaskEvent локально и доставляет в Pipeline / R2 при наличии конфига."""
    if events_dir is None:
        events_dir = Path(".codeops") / "events"

    path = _write_local_event(event, events_dir)

    endpoint = resolve_pipeline_endpoint(pipeline_url or "")
    if pipeline_enabled and endpoint:
        timeout = pipeline_timeout if pipeline_timeout is not None else 5.0
        try:
            send_to_pipeline(endpoint, event, timeout=timeout)
        except TelemetryDeliveryError as exc:
            logger.debug("telemetry: pipeline upload failed: %s", exc)

    if r2_enabled:
        r2_endpoint = os.environ.get("CF_R2_ENDPOINT")
        r2_bucket = os.environ.get("CF_R2_BUCKET_TELEMETRY", "codeops-telemetry")
        r2_key_id = os.environ.get("CF_R2_ACCESS_KEY_ID")
        r2_secret = os.environ.get("CF_R2_SECRET_ACCESS_KEY")
        if r2_endpoint and r2_key_id and r2_secret:
            try:
                _emit_to_r2(event, r2_endpoint, r2_bucket, r2_key_id, r2_secret)
            except Exception as exc:
                logger.debug("telemetry: r2 upload failed: %s", exc)

    return path


def emit_event_from_config(event: TaskEvent, config: Any | None = None) -> Path | None:
    """emit_event с настройками из CodeOpsConfig.telemetry."""
    if config is None:
        return emit_event(event)

    telemetry = getattr(config, "telemetry", None)
    if telemetry is None:
        return emit_event(event)

    path = emit_event(
        event,
        events_dir=telemetry.events_dir,
        pipeline_url=telemetry.pipeline_url,
        pipeline_enabled=telemetry.pipeline_enabled,
        pipeline_timeout=telemetry.pipeline_timeout_seconds,
        r2_enabled=telemetry.r2_enabled,
    )
    try:
        from codeops.spend import record_task_spend

        record_task_spend(event, config)
    except Exception:
        pass
    return path


def _emit_to_r2(
    event: TaskEvent,
    endpoint: str,
    bucket: str,
    access_key: str,
    secret_key: str,
) -> None:
    """PUT события в R2 через R2Client (правильный SigV4)."""
    from codeops.cloudflare.r2 import R2Client
    r2 = R2Client(endpoint, access_key, secret_key, timeout=5.0)
    r2.put(bucket, f"events/{event.task_id}.json", event.to_json().encode(), "application/json")


def load_events(events_dir: str | Path | None = None) -> list[TaskEvent]:
    """Загружает все события из .codeops/events/."""
    if events_dir is None:
        events_dir = Path(".codeops") / "events"

    events: list[TaskEvent] = []
    target = Path(events_dir)
    if not target.exists():
        return events

    for path in sorted(target.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            tok = data.get("tokens", {})
            gw = data.get("gateway", {})
            events.append(TaskEvent(
                task_id=data["task_id"],
                agent=data.get("agent", ""),
                status=data.get("status", ""),
                tokens=TokenMetrics(**tok) if tok else TokenMetrics(),
                gateway=GatewayMetrics(**gw) if gw else GatewayMetrics(),
                skill_ids=data.get("skill_ids", []),
                workflow=data.get("workflow"),
                routing_score=data.get("routing_score", 0.0),
                cost_usd=data.get("cost_usd", 0.0),
                duration_ms=data.get("duration_ms", 0.0),
                model=data.get("model", ""),
                provider=data.get("provider", ""),
                executor=data.get("executor", ""),
                task_type=data.get("task_type"),
                automation_score=float(data.get("automation_score") or 0.0),
                manual_steps_removed=int(data.get("manual_steps_removed") or 0),
                error=data.get("error"),
                dspy_enabled=bool(data.get("dspy_enabled", False)),
                dspy_mode=data.get("dspy_mode"),
                dspy_program_id=data.get("dspy_program_id") or data.get("dspy_program"),
                dspy_program_version=
                    int(data.get("dspy_program_version"))
                    if str(data.get("dspy_program_version")).isdigit()
                    else None,
                dspy_program_tag=data.get("dspy_program_tag"),
                dspy_optimizer=data.get("dspy_optimizer"),
                dspy_dataset=data.get("dspy_dataset"),
                dspy_compile_id=data.get("dspy_compile_id") or data.get("dspy_compiled_version"),
                dspy_score=
                    float(data["dspy_score"]) if data.get("dspy_score") is not None else None,
                dspy_shadow_delta=
                    float(data["dspy_shadow_delta"]) if data.get("dspy_shadow_delta") is not None else None,
            ))
        except Exception as exc:
            logger.debug("telemetry: failed to load %s: %s", path, exc)

    return events
