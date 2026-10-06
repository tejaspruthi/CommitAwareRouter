from __future__ import annotations

from datetime import UTC, date, datetime

import httpx

from .types import UsagePoint


class OpenAIUsageAdapter:
    """Read organization costs without exposing credentials to the router."""

    def __init__(
        self,
        admin_api_key: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=30)
        self._api_key = admin_api_key
        self._base_url = base_url.rstrip("/")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_daily_costs(self, start: date, end: date) -> list[UsagePoint]:
        """Fetch [start, end) costs. OpenAI currently returns daily buckets."""

        params: dict[str, str | int] = {
            "start_time": int(datetime.combine(start, datetime.min.time(), UTC).timestamp()),
            "end_time": int(datetime.combine(end, datetime.min.time(), UTC).timestamp()),
            "bucket_width": "1d",
            "limit": 180,
        }
        points: list[UsagePoint] = []
        while True:
            response = self._client.get(
                f"{self._base_url}/organization/costs",
                params=params,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            body = response.json()
            for bucket in body.get("data", []):
                day = datetime.fromtimestamp(bucket["start_time"], UTC).date()
                cost = sum(float(item["amount"]["value"]) for item in bucket.get("results", []))
                points.append(UsagePoint(provider="openai", day=day, cost_usd=cost))
            next_page = body.get("next_page")
            if not body.get("has_more") or not next_page:
                break
            params["page"] = next_page
        return points

