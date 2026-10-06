from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import ShadowPolicy


@dataclass(frozen=True)
class CommitmentSecret:
    """Sensitive input. Instances must remain inside the customer boundary."""

    scope_id: str
    amount_usd: float
    used_usd: float
    forecast_remaining_usd: float
    ends_at: datetime
    eligible_models: tuple[str, ...]
    commitment_type: str = "minimum"
    prepaid: bool = True
    hard_limit: bool = False
    max_traffic_share: float = 0.25
    policy_ttl_minutes: int = 60
    policy_version: str = "v1"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _quantize(value: float, step: float) -> float:
    return round(value / step) * step


def compile_shadow_policy(
    secret: CommitmentSecret,
    *,
    now: datetime | None = None,
) -> ShadowPolicy:
    """Convert sensitive commitment state into a deliberately lossy policy."""

    now = (now or datetime.now(UTC)).astimezone(UTC)
    ends_at = secret.ends_at.astimezone(UTC)
    days_remaining = max(1, (ends_at.date() - now.date()).days)
    forecast_remaining = max(0.0, secret.forecast_remaining_usd)

    if secret.commitment_type == "minimum":
        remaining_commit = max(0.0, secret.amount_usd - secret.used_usd)
        stranded_dollars = max(0.0, remaining_commit - forecast_remaining)
        urgency = _clamp(
            (stranded_dollars / max(1.0, remaining_commit)) * (30 / days_remaining),
            0,
            1,
        )
        raw_marginal_value = (0.85 if secret.prepaid else 0.25) * urgency
        marginal_value = _clamp(_quantize(raw_marginal_value, 0.05), 0, 0.85)
        blocked = False
    elif secret.commitment_type == "maximum":
        projected_overage = max(0.0, secret.used_usd + forecast_remaining - secret.amount_usd)
        overage_risk = projected_overage / max(1.0, forecast_remaining)
        urgency = _clamp(overage_risk * (30 / days_remaining), 0, 1)
        marginal_value = _clamp(_quantize(-0.85 * urgency, 0.05), -0.85, 0)
        blocked = secret.hard_limit and secret.used_usd >= secret.amount_usd
    else:
        raise ValueError("commitment_type must be 'minimum' or 'maximum'.")

    ttl_minutes = min(max(1, secret.policy_ttl_minutes), 24 * 60)

    return ShadowPolicy(
        scope_id=secret.scope_id,
        marginal_value_usd_per_dollar=marginal_value,
        eligible_models=tuple(secret.eligible_models),
        max_traffic_share=_clamp(secret.max_traffic_share, 0, 1),
        not_after=now + timedelta(minutes=ttl_minutes),
        blocked=blocked,
        policy_version=secret.policy_version,
    )
