from __future__ import annotations

import threading
from collections import Counter, deque
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from litellm.types.router import CustomRoutingStrategyBase

from .models import Candidate, RequestConstraints, ShadowPolicy
from .routing import route


class PolicyStore(Protocol):
    def get_policies(self, *, now: datetime | None = None) -> dict[str, ShadowPolicy]: ...


class RollingTrafficShares:
    def __init__(self, window_size: int = 1000) -> None:
        if window_size < 1:
            raise ValueError("Traffic window must be positive.")
        self._scopes: deque[frozenset[str]] = deque(maxlen=window_size)
        self._lock = threading.Lock()

    def shares(self) -> dict[str, float]:
        with self._lock:
            if not self._scopes:
                return {}
            counts = Counter(scope for scopes in self._scopes for scope in scopes)
            total = len(self._scopes)
            return {scope: count / total for scope, count in counts.items()}

    def record(self, scopes: frozenset[str]) -> None:
        with self._lock:
            self._scopes.append(scopes)


class CommitAwareRoutingStrategy(CustomRoutingStrategyBase):
    """LiteLLM routing strategy driven by verified shadow-price policies."""

    def __init__(
        self,
        model_list: list[dict[str, Any]],
        policy_store: PolicyStore,
        *,
        constraints: RequestConstraints,
        shadow_mode: bool = True,
        traffic_window_size: int = 1000,
    ) -> None:
        self.model_list = model_list
        self.policy_store = policy_store
        self.constraints = constraints
        self.shadow_mode = shadow_mode
        self.traffic = RollingTrafficShares(traffic_window_size)
        self.last_decision: dict[str, Any] | None = None
        self.last_policy_error: str | None = None

    @staticmethod
    def _candidate(deployment: dict[str, Any]) -> Candidate:
        info = deployment.get("model_info") or {}
        metadata = info.get("commit_aware") or {}
        required = (
            "provider",
            "cost_per_million_tokens_usd",
            "quality",
            "p95_latency_ms",
            "failure_rate",
        )
        missing = [field for field in required if field not in metadata]
        if missing:
            raise ValueError(f"LiteLLM deployment is missing commit_aware fields: {', '.join(missing)}")
        candidate_id = info.get("id") or metadata.get("routing_id")
        if not candidate_id:
            raise ValueError("LiteLLM deployment requires model_info.id for commitment eligibility.")
        return Candidate(
            id=str(candidate_id),
            provider=str(metadata["provider"]),
            cost_per_million_tokens_usd=float(metadata["cost_per_million_tokens_usd"]),
            quality=float(metadata["quality"]),
            p95_latency_ms=float(metadata["p95_latency_ms"]),
            failure_rate=float(metadata["failure_rate"]),
            capabilities=frozenset(metadata.get("capabilities", [])),
            publisher=str(metadata.get("publisher", metadata["provider"])),
            billing_channel=str(metadata.get("billing_channel", metadata["provider"])),
            commitment_scopes=frozenset(metadata.get("commitment_scopes", [])),
            deployment=deployment,
        )

    def _request_constraints(self, request_kwargs: dict[str, Any] | None) -> RequestConstraints:
        # Callers may tighten hard constraints, never weaken configured policy.
        request_kwargs = request_kwargs or {}
        metadata = request_kwargs.get("metadata") or request_kwargs.get("litellm_metadata") or {}
        requested = metadata.get("commit_aware") or {}
        requested_min_quality = float(requested.get("min_quality", self.constraints.min_quality))
        requested_max_latency = float(
            requested.get("max_p95_latency_ms", self.constraints.max_p95_latency_ms)
        )
        requested_capabilities = frozenset(requested.get("required_capabilities", []))
        return RequestConstraints(
            min_quality=max(self.constraints.min_quality, requested_min_quality),
            max_p95_latency_ms=min(self.constraints.max_p95_latency_ms, requested_max_latency),
            required_capabilities=self.constraints.required_capabilities | requested_capabilities,
            failure_penalty_usd=self.constraints.failure_penalty_usd,
            latency_penalty_usd_per_second=self.constraints.latency_penalty_usd_per_second,
            scope_traffic_shares=self.traffic.shares(),
        )

    def _select(self, model: str, request_kwargs: dict[str, Any] | None) -> dict[str, Any]:
        now = datetime.now(UTC)
        candidates = [
            self._candidate(deployment)
            for deployment in self.model_list
            if deployment.get("model_name") == model
        ]
        if not candidates:
            raise ValueError(f"No commit-aware LiteLLM deployments configured for model group {model!r}.")
        constraints = self._request_constraints(request_kwargs)
        try:
            policies = self.policy_store.get_policies(now=now)
            self.last_policy_error = None
        except Exception as exc:
            # Fail closed for financial influence, not for inference availability.
            policies = {}
            self.last_policy_error = type(exc).__name__
        baseline = route(constraints, candidates, {}, now=now)
        recommended = route(constraints, candidates, policies, now=now)
        selected = baseline if self.shadow_mode else recommended
        selected_candidate = next(candidate for candidate in candidates if candidate.id == selected.target)
        self.traffic.record(selected_candidate.commitment_scopes)
        self.last_decision = {
            "selected_target": selected.target,
            "recommended_target": recommended.target,
            "baseline_target": baseline.target,
            "shadow_mode": self.shadow_mode,
            "reason": recommended.reason,
        }
        return selected.deployment

    def get_available_deployment(
        self,
        model: str,
        messages: list[dict[str, str]] | None = None,
        input: str | list | None = None,
        specific_deployment: bool | None = False,
        request_kwargs: dict | None = None,
    ) -> dict[str, Any]:
        return self._select(model, request_kwargs)

    async def async_get_available_deployment(
        self,
        model: str,
        messages: list[dict[str, str]] | None = None,
        input: str | list | None = None,
        specific_deployment: bool | None = False,
        request_kwargs: dict | None = None,
    ) -> dict[str, Any]:
        return self._select(model, request_kwargs)
