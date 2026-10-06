from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from .types import UsagePoint


@dataclass(frozen=True)
class AnthropicModelPrice:
    """USD per million tokens. Keep negotiated prices customer-local."""

    input: float
    output: float
    cache_read: float | None = None
    cache_write: float | None = None


class AnthropicUsageAdapter:
    """Read token usage and value it with a customer-local price book."""

    def __init__(
        self,
        admin_api_key: str,
        model_prices: dict[str, AnthropicModelPrice],
        *,
        client: httpx.Client | None = None,
        base_url: str = "https://api.anthropic.com/v1",
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=30)
        self._api_key = admin_api_key
        self._model_prices = model_prices
        self._base_url = base_url.rstrip("/")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_daily_costs(self, start: date, end: date) -> list[UsagePoint]:
        params: list[tuple[str, str | int]] = [
            ("starting_at", datetime.combine(start, datetime.min.time(), UTC).isoformat().replace("+00:00", "Z")),
            ("ending_at", datetime.combine(end, datetime.min.time(), UTC).isoformat().replace("+00:00", "Z")),
            ("bucket_width", "1d"),
            ("group_by[]", "model"),
            ("limit", 31),
        ]
        points: list[UsagePoint] = []
        while True:
            response = self._client.get(
                f"{self._base_url}/organizations/usage_report/messages",
                params=params,
                headers={
                    "anthropic-version": "2023-06-01",
                    "x-api-key": self._api_key,
                },
            )
            response.raise_for_status()
            body = response.json()
            for bucket in body.get("data", []):
                day = datetime.fromisoformat(bucket["starting_at"].replace("Z", "+00:00")).date()
                for item in bucket.get("results", []):
                    model = item.get("model")
                    if model not in self._model_prices:
                        raise ValueError(f"No customer-local price configured for Anthropic model {model!r}.")
                    price = self._model_prices[model]
                    cache_creation = item.get("cache_creation") or {}
                    cache_write_tokens = sum(float(value) for value in cache_creation.values())
                    input_tokens = float(item.get("uncached_input_tokens", 0))
                    cache_read_tokens = float(item.get("cache_read_input_tokens", 0))
                    output_tokens = float(item.get("output_tokens", 0))
                    cost = (
                        input_tokens * price.input
                        + output_tokens * price.output
                        + cache_read_tokens * (price.cache_read if price.cache_read is not None else price.input)
                        + cache_write_tokens * (price.cache_write if price.cache_write is not None else price.input)
                    ) / 1_000_000
                    points.append(UsagePoint(provider="anthropic", day=day, cost_usd=cost, model=model))
            next_page = body.get("next_page")
            if not body.get("has_more") or not next_page:
                break
            params = [(key, value) for key, value in params if key != "page"] + [("page", next_page)]
        return points

