"""Executor matcher — CF Worker remote match with local fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from voly.capability.registry import CapabilityRegistry
from voly.capability.schema import CapabilityMatchResult, ExecutorCapabilityProfile
from voly.capability.scorer import hard_exclude, routing_score

_log = logging.getLogger("voly.capability.matcher")


@dataclass
class MatchRequest:
    dimension: str
    available_executors: list[str] | None
    project_features: list[str] | None
    kind: str = ""
    requires_file_tools: bool = True
    requires_browser_tools: bool = False
    worker_url: str = ""
    worker_timeout_s: float = 5.0


class ExecutorMatcher:
    def __init__(self, registry: CapabilityRegistry, worker_url: str = "") -> None:
        self._registry = registry
        self._worker_url = worker_url.rstrip("/")

    def find_executors(self, req: MatchRequest) -> CapabilityMatchResult:
        """
        1. Try CF Worker POST /match (if worker_url set).
           On success, assemble CapabilityMatchResult from response.
           On any error / timeout → fall through to local.
        2. Local fallback: load profiles, hard_exclude, routing_score, rank.
        """
        worker_url = (req.worker_url or self._worker_url).rstrip("/")
        if worker_url:
            remote = self._remote_match(req, worker_url)
            if remote is not None:
                remote = self._filter_result_by_kind(remote, req.kind)
                if remote is not None:
                    return remote
        return self._local_match(req)

    @staticmethod
    def _filter_result_by_kind(
        result: CapabilityMatchResult, kind: str
    ) -> CapabilityMatchResult | None:
        """Drop model_provider hits when the caller asked for executors (and vice versa).

        The hosted /match endpoint ranks all profiles; without this filter a
        vision model_provider can be recommended for developer/tester roles.
        """
        kind = (kind or "").strip()
        if not kind:
            return result

        def _ok(profile: ExecutorCapabilityProfile | None) -> bool:
            return profile is not None and (profile.kind or "executor") == kind

        recommended = result.recommended if _ok(result.recommended) else None
        fallbacks = [(p, s) for p, s in result.fallbacks if _ok(p)]
        if recommended is None and fallbacks:
            recommended, score = fallbacks[0]
            fallbacks = fallbacks[1:]
            return CapabilityMatchResult(
                recommended=recommended,
                score=score,
                fallbacks=fallbacks,
                excluded=result.excluded,
                degraded=result.degraded,
            )
        if recommended is None:
            return None
        return CapabilityMatchResult(
            recommended=recommended,
            score=result.score,
            fallbacks=fallbacks,
            excluded=result.excluded,
            degraded=result.degraded,
        )

    def _remote_match(
        self, req: MatchRequest, worker_url: str
    ) -> CapabilityMatchResult | None:
        """POST to CF Worker. Returns None on any failure."""
        import httpx

        try:
            payload = {
                "dimension": req.dimension,
                "available_executors": req.available_executors,
                "kind": req.kind or None,
            }
            resp = httpx.post(
                f"{worker_url}/match",
                json=payload,
                timeout=req.worker_timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return None

            recommended_raw = data.get("recommended")
            excluded = _parse_excluded(data.get("excluded"))

            if not recommended_raw:
                return CapabilityMatchResult(
                    recommended=None,
                    score=0.0,
                    fallbacks=[],
                    excluded=excluded,
                    degraded=False,
                )

            executor_id = str(recommended_raw["executor_id"])
            top_score = float(
                recommended_raw.get("routing_score", recommended_raw.get("score", 0.0))
            )
            recommended = self._registry.load(executor_id)
            fallbacks = _parse_fallbacks(self._registry, data.get("fallbacks"))

            return CapabilityMatchResult(
                recommended=recommended,
                score=top_score,
                fallbacks=fallbacks,
                excluded=excluded,
                degraded=False,
            )
        except Exception as exc:
            _log.debug("capability worker unreachable: %s", exc)
            return None

    def _local_match(self, req: MatchRequest) -> CapabilityMatchResult:
        """Local scorer using registry profiles."""
        ids = self._registry.list_ids()
        if req.available_executors is not None:
            allowed = set(req.available_executors)
            ids = [i for i in ids if i in allowed]
        if req.kind:
            ids = [i for i in ids if self._registry.load(i).kind == req.kind]

        included: list[tuple[ExecutorCapabilityProfile, float]] = []
        excluded: list[tuple[str, str]] = []

        for executor_id in ids:
            profile = self._registry.load(executor_id)
            reason = hard_exclude(
                profile,
                req.requires_file_tools,
                req.requires_browser_tools,
            )
            if reason:
                excluded.append((executor_id, reason))
                continue
            score = routing_score(profile, req.dimension, req.project_features)
            included.append((profile, score))

        included.sort(key=lambda x: -x[1])
        if not included:
            return CapabilityMatchResult(
                recommended=None,
                score=0.0,
                fallbacks=[],
                excluded=excluded,
                degraded=True,
            )

        recommended_profile, top_score = included[0]
        fallbacks = included[1:]
        return CapabilityMatchResult(
            recommended=recommended_profile,
            score=top_score,
            fallbacks=fallbacks,
            excluded=excluded,
            degraded=False,
        )


def _parse_excluded(raw: object) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        return []
    excluded: list[tuple[str, str]] = []
    for entry in raw:
        if isinstance(entry, dict) and "executor_id" in entry:
            excluded.append((str(entry["executor_id"]), str(entry.get("reason", ""))))
    return excluded


def _parse_fallbacks(
    registry: CapabilityRegistry, raw: object
) -> list[tuple[ExecutorCapabilityProfile, float]]:
    if not isinstance(raw, list):
        return []
    fallbacks: list[tuple[ExecutorCapabilityProfile, float]] = []
    for entry in raw:
        if not isinstance(entry, dict) or "executor_id" not in entry:
            continue
        profile = registry.load(str(entry["executor_id"]))
        score = float(entry.get("routing_score", entry.get("score", 0.0)))
        fallbacks.append((profile, score))
    return fallbacks
