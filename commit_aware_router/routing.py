from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, Mapping

from .models import Candidate, RequestConstraints, RouteDecision, ScoredCandidate, ShadowPolicy


def _eligible(candidate: Candidate, request: RequestConstraints) -> bool:
    return (
        candidate.quality >= request.min_quality
        and candidate.p95_latency_ms <= request.max_p95_latency_ms
        and request.required_capabilities.issubset(candidate.capabilities)
    )


def _score_candidate(
    candidate: Candidate,
    request: RequestConstraints,
    policies: Mapping[str, ShadowPolicy],
    now: datetime,
) -> ScoredCandidate | None:
    active: list[ShadowPolicy] = []
    capped: list[str] = []
    for scope_id in sorted(candidate.commitment_scopes):
        policy = policies.get(scope_id)
        if not policy or policy.not_after <= now or candidate.id not in policy.eligible_models:
            continue
        if policy.blocked:
            return None
        if request.scope_traffic_shares.get(scope_id, 0) >= policy.max_traffic_share:
            capped.append(scope_id)
            continue
        active.append(policy)

    # A route can consume nested commitments (for example AWS enterprise +
    # Bedrock). Combine only explicitly declared scopes and cap the aggregate
    # so financial policy can never create a zero or negative effective cost.
    adjustment_rate = min(0.95, max(-2.0, sum(p.marginal_value_usd_per_dollar for p in active)))
    raw_cost = candidate.cost_per_million_tokens_usd
    effective_cost = raw_cost * (1 - adjustment_rate)
    score = (
        effective_cost
        + candidate.failure_rate * request.failure_penalty_usd
        + (candidate.p95_latency_ms / 1000) * request.latency_penalty_usd_per_second
    )
    return ScoredCandidate(
        candidate=candidate,
        raw_cost=raw_cost,
        effective_cost=effective_cost,
        score=score,
        commitment_adjustment_rate=adjustment_rate,
        active_scopes=tuple(policy.scope_id for policy in active),
        capped_scopes=tuple(capped),
    )


def route(
    request: RequestConstraints,
    candidates: Iterable[Candidate],
    policies: Mapping[str, ShadowPolicy] | None = None,
    *,
    now: datetime | None = None,
) -> RouteDecision:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    policies = policies or {}
    scored = (
        _score_candidate(candidate, request, policies, now)
        for candidate in candidates
        if _eligible(candidate, request)
    )
    evaluated = sorted((item for item in scored if item is not None), key=lambda item: item.score)
    if not evaluated:
        raise ValueError("No route meets the request's quality, latency, and capability constraints.")

    winner = evaluated[0]
    reason = (
        f"Eligible route; active commitment scopes {', '.join(winner.active_scopes)} changed its effective cost."
        if winner.active_scopes
        else "Eligible route with the best cost, reliability, and latency score."
    )
    return RouteDecision(
        target=winner.candidate.id,
        provider=winner.candidate.provider,
        reason=reason,
        raw_cost_per_million_tokens_usd=winner.raw_cost,
        commitment_adjusted_cost_per_million_tokens_usd=winner.effective_cost,
        commitment_adjustment_rate=winner.commitment_adjustment_rate,
        score=winner.score,
        alternatives=tuple((item.candidate.id, item.score) for item in evaluated[1:]),
        applied_commitment_scopes=winner.active_scopes,
        deployment=winner.candidate.deployment,
    )
