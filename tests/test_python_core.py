from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from commit_aware_router.models import Candidate, RequestConstraints
from commit_aware_router.policy import CommitmentSecret, compile_shadow_policy
from commit_aware_router.routing import route
from commit_aware_router.signing import PolicyVerificationError, sign_shadow_policy, verify_shadow_policy_token


NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


def secret(**overrides):
    values = {
        "scope_id": "aws-enterprise",
        "amount_usd": 100,
        "used_usd": 10,
        "forecast_remaining_usd": 10,
        "ends_at": NOW + timedelta(days=4),
        "prepaid": True,
        "eligible_models": ("committed",),
    }
    values.update(overrides)
    return CommitmentSecret(**values)


class CoreTests(unittest.TestCase):
    def test_signed_payload_never_contains_commitment_fields(self):
        private_key = Ed25519PrivateKey.generate()
        token = sign_shadow_policy(
            compile_shadow_policy(secret(), now=NOW),
            private_key=private_key,
            issuer="customer-acme",
            audience="router",
            key_id="key-1",
            now=NOW,
        )
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        for forbidden in ("amount_usd", "used_usd", "forecast_remaining_usd", "ends_at", "prepaid"):
            self.assertNotIn(forbidden, payload)

    def test_tampering_is_rejected(self):
        private_key = Ed25519PrivateKey.generate()
        token = sign_shadow_policy(
            compile_shadow_policy(secret(), now=NOW),
            private_key=private_key,
            issuer="customer-acme",
            audience="router",
            key_id="key-1",
            now=NOW,
        )
        parts = token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload["marginalValueUsdPerDollar"] = 0.1
        parts[1] = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        with self.assertRaisesRegex(PolicyVerificationError, "signature is invalid"):
            verify_shadow_policy_token(
                ".".join(parts),
                expected_issuer="customer-acme",
                expected_audience="router",
                trusted_public_keys={"key-1": private_key.public_key()},
                now=NOW,
            )

    def test_commitment_can_break_cost_tie_but_not_quality_gate(self):
        policy = compile_shadow_policy(secret(), now=NOW)
        candidates = [
            Candidate("cheap", "direct", 5, 0.9, 100, 0),
            Candidate(
                "committed", "aws", 5.4, 0.9, 100, 0,
                commitment_scopes=frozenset({"aws-enterprise"}),
            ),
        ]
        decision = route(
            RequestConstraints(min_quality=0.8),
            candidates,
            {"aws-enterprise": policy},
            now=NOW,
        )
        self.assertEqual(decision.target, "committed")

        strict = RequestConstraints(min_quality=0.95)
        qualified = Candidate("qualified", "direct", 8, 0.96, 100, 0)
        decision = route(
            strict,
            [candidates[1], qualified],
            {"aws-enterprise": policy},
            now=NOW,
        )
        self.assertEqual(decision.target, "qualified")

    def test_nested_scopes_stack_but_direct_publisher_commit_does_not_leak(self):
        aws_enterprise = compile_shadow_policy(
            secret(scope_id="aws-enterprise", eligible_models=("bedrock-claude",)), now=NOW
        )
        aws_bedrock = compile_shadow_policy(
            secret(scope_id="aws-bedrock", eligible_models=("bedrock-claude",)), now=NOW
        )
        anthropic_direct = compile_shadow_policy(
            secret(scope_id="anthropic-direct", eligible_models=("bedrock-claude",)), now=NOW
        )
        candidates = [
            Candidate("openai-direct", "openai", 5, 0.9, 100, 0),
            Candidate(
                "bedrock-claude", "aws", 8, 0.9, 100, 0,
                publisher="anthropic",
                billing_channel="aws-bedrock",
                commitment_scopes=frozenset({"aws-enterprise", "aws-bedrock"}),
            ),
        ]
        policies = {
            policy.scope_id: policy
            for policy in (aws_enterprise, aws_bedrock, anthropic_direct)
        }
        decision = route(RequestConstraints(), candidates, policies, now=NOW)
        self.assertEqual(decision.target, "bedrock-claude")
        self.assertEqual(
            decision.applied_commitment_scopes,
            ("aws-bedrock", "aws-enterprise"),
        )
        self.assertNotIn("anthropic-direct", decision.applied_commitment_scopes)

    def test_maximum_commitment_penalizes_projected_overage(self):
        maximum = compile_shadow_policy(
            secret(
                scope_id="anthropic-direct-ceiling",
                commitment_type="maximum",
                amount_usd=100,
                used_usd=90,
                forecast_remaining_usd=30,
                eligible_models=("anthropic-direct",),
            ),
            now=NOW,
        )
        decision = route(
            RequestConstraints(),
            [
                Candidate(
                    "anthropic-direct", "anthropic", 4, 0.9, 100, 0,
                    commitment_scopes=frozenset({"anthropic-direct-ceiling"}),
                ),
                Candidate("openai-direct", "openai", 5, 0.9, 100, 0),
            ],
            {maximum.scope_id: maximum},
            now=NOW,
        )
        self.assertEqual(decision.target, "openai-direct")


if __name__ == "__main__":
    unittest.main()
