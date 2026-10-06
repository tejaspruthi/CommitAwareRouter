from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ShadowPolicy:
    scope_id: str
    marginal_value_usd_per_dollar: float
    eligible_models: tuple[str, ...]
    max_traffic_share: float
    not_after: datetime
    blocked: bool = False
    policy_version: str = "v1"
    verification: dict[str, str] | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Candidate:
    id: str
    provider: str
    cost_per_million_tokens_usd: float
    quality: float
    p95_latency_ms: float
    failure_rate: float
    capabilities: frozenset[str] = frozenset()
    publisher: str | None = None
    billing_channel: str | None = None
    commitment_scopes: frozenset[str] = frozenset()
    deployment: Any = field(default=None, compare=False)


@dataclass(frozen=True)
class RequestConstraints:
    min_quality: float = 0
    max_p95_latency_ms: float = float("inf")
    required_capabilities: frozenset[str] = frozenset()
    failure_penalty_usd: float = 0
    latency_penalty_usd_per_second: float = 0
    scope_traffic_shares: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    raw_cost: float
    effective_cost: float
    score: float
    commitment_adjustment_rate: float
    active_scopes: tuple[str, ...]
    capped_scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteDecision:
    target: str
    provider: str
    reason: str
    raw_cost_per_million_tokens_usd: float
    commitment_adjusted_cost_per_million_tokens_usd: float
    commitment_adjustment_rate: float
    score: float
    alternatives: tuple[tuple[str, float], ...]
    applied_commitment_scopes: tuple[str, ...] = ()
    deployment: Any = field(default=None, compare=False)
