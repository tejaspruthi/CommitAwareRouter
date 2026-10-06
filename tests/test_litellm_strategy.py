from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime, timedelta

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from litellm import Router

from commit_aware_router.litellm_strategy import CommitAwareRoutingStrategy
from commit_aware_router.models import RequestConstraints, ShadowPolicy


class StaticStore:
    def __init__(self, policies):
        self.policies = policies

    def get_policies(self, *, now=None):
        return self.policies


def deployment(candidate_id, provider, cost, quality=0.9, scopes=()):
    litellm_model = "bedrock/anthropic.claude-v2" if provider == "aws" else f"{provider}/test"
    return {
        "model_name": "smart-model",
        "litellm_params": {"model": litellm_model, "api_key": "fake"},
        "model_info": {
            "id": candidate_id,
            "commit_aware": {
                "provider": provider,
                "publisher": "anthropic" if provider == "aws" else provider,
                "billing_channel": "aws-bedrock" if provider == "aws" else f"{provider}-direct",
                "commitment_scopes": list(scopes),
                "cost_per_million_tokens_usd": cost,
                "quality": quality,
                "p95_latency_ms": 100,
                "failure_rate": 0,
                "capabilities": ["json"],
            },
        },
    }


class LiteLLMStrategyTests(unittest.TestCase):
    def setUp(self):
        self.models = [
            deployment("cheap", "openai", 5),
            deployment("committed", "aws", 5.4, scopes=("aws-enterprise",)),
        ]
        self.policy = ShadowPolicy(
            scope_id="aws-enterprise",
            marginal_value_usd_per_dollar=0.85,
            eligible_models=("committed",),
            max_traffic_share=1,
            not_after=datetime.now(UTC) + timedelta(hours=1),
        )

    def test_litellm_router_uses_strategy(self):
        strategy = CommitAwareRoutingStrategy(
            self.models,
            StaticStore({"aws-enterprise": self.policy}),
            constraints=RequestConstraints(min_quality=0.8, required_capabilities=frozenset({"json"})),
            shadow_mode=False,
        )
        router = Router(model_list=self.models)
        router.set_custom_routing_strategy(strategy)
        selected = router.get_available_deployment("smart-model")
        self.assertEqual(selected["model_info"]["id"], "committed")

    def test_shadow_mode_observes_but_does_not_change_route(self):
        strategy = CommitAwareRoutingStrategy(
            self.models,
            StaticStore({"aws-enterprise": self.policy}),
            constraints=RequestConstraints(min_quality=0.8),
            shadow_mode=True,
        )
        selected = strategy.get_available_deployment("smart-model")
        self.assertEqual(selected["model_info"]["id"], "cheap")
        self.assertEqual(strategy.last_decision["recommended_target"], "committed")

    def test_invalid_policy_fails_closed_to_normal_routing(self):
        class BrokenStore:
            def get_policies(self, *, now=None):
                raise ValueError("bad signature")

        strategy = CommitAwareRoutingStrategy(
            self.models,
            BrokenStore(),
            constraints=RequestConstraints(min_quality=0.8),
            shadow_mode=False,
        )
        selected = strategy.get_available_deployment("smart-model")
        self.assertEqual(selected["model_info"]["id"], "cheap")
        self.assertEqual(strategy.last_policy_error, "ValueError")


if __name__ == "__main__":
    unittest.main()
