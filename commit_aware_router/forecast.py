from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from .adapters.types import UsagePoint


@dataclass(frozen=True)
class SpendForecast:
    provider: str
    daily_spend_usd: float
    remaining_spend_usd: float
    horizon_days: int


def forecast_remaining_spend(
    provider: str,
    usage: Iterable[UsagePoint],
    *,
    as_of: date,
    ends_at: date,
    lookback_days: int = 30,
    ewma_alpha: float = 0.35,
) -> SpendForecast:
    """Small, auditable baseline forecast. Customers may replace this adapter."""

    if not 0 < ewma_alpha <= 1:
        raise ValueError("ewma_alpha must be in (0, 1].")
    start = as_of - timedelta(days=lookback_days - 1)
    totals: dict[date, float] = {}
    for point in usage:
        if point.provider == provider and start <= point.day <= as_of:
            totals[point.day] = totals.get(point.day, 0) + point.cost_usd
    daily_values = [totals.get(start + timedelta(days=offset), 0) for offset in range(lookback_days)]
    ewma = daily_values[0]
    for value in daily_values[1:]:
        ewma = ewma_alpha * value + (1 - ewma_alpha) * ewma
    horizon_days = max(0, (ends_at - as_of).days)
    return SpendForecast(
        provider=provider,
        daily_spend_usd=ewma,
        remaining_spend_usd=ewma * horizon_days,
        horizon_days=horizon_days,
    )

