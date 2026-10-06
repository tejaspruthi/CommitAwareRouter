import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { compileShadowPolicy } from "../src/policy.js";
import { signShadowPolicy, verifyShadowPolicyToken } from "../src/signed-policy.js";
import { routeWithSignedPolicies } from "../src/secure-router.js";

const now = new Date("2026-10-06T12:00:00Z");
const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const policy = compileShadowPolicy({
  provider: "aws",
  amountUsd: 100,
  usedUsd: 0,
  forecastRemainingUsd: 0,
  endsAt: "2026-10-10",
  prepaid: true,
  eligibleModels: ["committed"],
  maxTrafficShare: 0.25
}, now);

function signPolicy(overrides = {}) {
  return signShadowPolicy(policy, {
    issuer: "customer-acme",
    audience: "commit-aware-router",
    keyId: "key-1",
    policyId: "policy-1",
    privateKey,
    now,
    ...overrides
  });
}

function verificationOptions(overrides = {}) {
  return {
    expectedIssuer: "customer-acme",
    expectedAudience: "commit-aware-router",
    trustedPublicKeys: { "key-1": publicKey },
    now,
    ...overrides
  };
}

test("valid Ed25519 policy verifies without exposing commitment inputs", () => {
  const token = signPolicy();
  const verified = verifyShadowPolicyToken(token, verificationOptions());
  assert.equal(verified.provider, "aws");
  assert.equal(verified.verification.policyId, "policy-1");
  const decodedToken = Buffer.from(token.split(".")[1], "base64url").toString("utf8");
  for (const forbidden of ["amountUsd", "usedUsd", "forecastRemainingUsd", "endsAt", "prepaid"]) {
    assert.equal(decodedToken.includes(forbidden), false);
  }
});

test("tampering with a signed payload is rejected", () => {
  const parts = signPolicy().split(".");
  const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
  payload.shadowPriceUsdPerDollar = 0.10;
  parts[1] = Buffer.from(JSON.stringify(payload)).toString("base64url");
  assert.throws(
    () => verifyShadowPolicyToken(parts.join("."), verificationOptions()),
    /signature is invalid/
  );
});

test("wrong audience and revoked policy IDs are rejected", () => {
  const token = signPolicy();
  assert.throws(
    () => verifyShadowPolicyToken(token, verificationOptions({ expectedAudience: "someone-else" })),
    /audience is invalid/
  );
  assert.throws(
    () => verifyShadowPolicyToken(token, verificationOptions({ revokedPolicyIds: new Set(["policy-1"]) })),
    /has been revoked/
  );
});

test("secure router applies a verified policy", () => {
  const decision = routeWithSignedPolicies(
    { minQuality: 0.8, maxP95LatencyMs: 3000, failurePenaltyUsd: 0, latencyPenaltyUsdPerSecond: 0, requiredCapabilities: [] },
    [
      { id: "cheap", provider: "direct", costPerMillionTokensUsd: 5, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] },
      { id: "committed", provider: "aws", costPerMillionTokensUsd: 5.4, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] }
    ],
    [signPolicy()],
    verificationOptions(),
    now
  );
  assert.equal(decision.target, "committed");
});
