"""Minimal programmatic LiteLLM integration; provider credentials omitted."""

from pathlib import Path

from litellm import Router

from commit_aware_router.litellm_strategy import CommitAwareRoutingStrategy
from commit_aware_router.models import RequestConstraints
from commit_aware_router.policy_store import SignedPolicyFileStore
from commit_aware_router.signing import load_public_key

model_list = [
    {
        "model_name": "smart-model",
        "litellm_params": {"model": "openai/gpt-4.1", "api_key": "os.environ/OPENAI_API_KEY"},
        "model_info": {
            "id": "openai-gpt",
            "commit_aware": {
                "provider": "openai",
                "publisher": "openai",
                "billing_channel": "openai-direct",
                "commitment_scopes": ["openai-direct"],
                "cost_per_million_tokens_usd": 6,
                "quality": 0.90,
                "p95_latency_ms": 1800,
                "failure_rate": 0.003,
                "capabilities": ["json", "tools"],
            },
        },
    },
    {
        "model_name": "smart-model",
        "litellm_params": {"model": "bedrock/converse/anthropic.claude-sonnet", "aws_region_name": "us-east-1"},
        "model_info": {
            "id": "bedrock-sonnet",
            "commit_aware": {
                "provider": "aws",
                "publisher": "anthropic",
                "billing_channel": "aws-bedrock",
                "commitment_scopes": ["aws-enterprise", "aws-bedrock"],
                "cost_per_million_tokens_usd": 5.4,
                "quality": 0.91,
                "p95_latency_ms": 2400,
                "failure_rate": 0.006,
                "capabilities": ["json", "tools"],
            },
        },
    },
]

store = SignedPolicyFileStore(
    Path("policies.json"),
    expected_issuer="customer-acme",
    expected_audience="commit-aware-router",
    trusted_public_keys={"acme-2026-01": load_public_key(Path("router-public.pem"))},
)
strategy = CommitAwareRoutingStrategy(
    model_list,
    store,
    constraints=RequestConstraints(
        min_quality=0.89,
        max_p95_latency_ms=3000,
        required_capabilities=frozenset({"json", "tools"}),
        failure_penalty_usd=200,
        latency_penalty_usd_per_second=0.05,
    ),
    shadow_mode=True,
)
router = Router(model_list=model_list)
router.set_custom_routing_strategy(strategy)
