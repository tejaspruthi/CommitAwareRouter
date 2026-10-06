from __future__ import annotations

import json
import unittest
from datetime import date

import httpx

from commit_aware_router.adapters import AnthropicModelPrice, AnthropicUsageAdapter, OpenAIUsageAdapter
from commit_aware_router.forecast import forecast_remaining_spend


class AdapterTests(unittest.TestCase):
    def test_openai_cost_adapter(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["Authorization"], "Bearer secret")
            return httpx.Response(200, json={
                "data": [{
                    "start_time": 1791244800,
                    "results": [{"amount": {"value": 3.25, "currency": "usd"}}],
                }],
                "has_more": False,
                "next_page": None,
            })

        client = httpx.Client(transport=httpx.MockTransport(handler))
        points = OpenAIUsageAdapter("secret", client=client).fetch_daily_costs(
            date(2026, 10, 6), date(2026, 10, 7)
        )
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].cost_usd, 3.25)

    def test_anthropic_usage_is_valued_locally(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["x-api-key"], "secret")
            return httpx.Response(200, json={
                "data": [{
                    "starting_at": "2026-10-06T00:00:00Z",
                    "results": [{
                        "model": "claude-test",
                        "uncached_input_tokens": 1_000_000,
                        "cache_read_input_tokens": 0,
                        "cache_creation": {},
                        "output_tokens": 100_000,
                    }],
                }],
                "has_more": False,
                "next_page": None,
            })

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = AnthropicUsageAdapter(
            "secret",
            {"claude-test": AnthropicModelPrice(input=3, output=15)},
            client=client,
        )
        points = adapter.fetch_daily_costs(date(2026, 10, 6), date(2026, 10, 7))
        self.assertEqual(points[0].cost_usd, 4.5)

    def test_forecast_is_local_and_auditable(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
        # Reuse the public value type without making a network request.
        from commit_aware_router.adapters.types import UsagePoint

        usage = [UsagePoint("openai", date(2026, 10, day), 10) for day in range(1, 7)]
        forecast = forecast_remaining_spend(
            "openai", usage, as_of=date(2026, 10, 6), ends_at=date(2026, 10, 10), lookback_days=6
        )
        self.assertAlmostEqual(forecast.daily_spend_usd, 10)
        self.assertAlmostEqual(forecast.remaining_spend_usd, 40)
        client.close()


if __name__ == "__main__":
    unittest.main()

