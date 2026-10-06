from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class UsagePoint:
    provider: str
    day: date
    cost_usd: float
    model: str | None = None

