import { generateKeyPairSync } from "node:crypto";
import { compileShadowPolicy } from "./policy.js";
import { routeWithSignedPolicies } from "./secure-router.js";
import { signShadowPolicy } from "./signed-policy.js";

const candidates = [
  { id: "openai/gpt-4.1", provider: "openai", costPerMillionTokensUsd: 6, quality: 0.90, p95LatencyMs: 1800, failureRate: 0.003, capabilities: ["json", "tools"] },
  { id: "anthropic/claude-sonnet", provider: "anthropic", costPerMillionTokensUsd: 5, quality: 0.91, p95LatencyMs: 2100, failureRate: 0.004, capabilities: ["json", "tools"] },
  { id: "bedrock/claude-sonnet", provider: "aws", costPerMillionTokensUsd: 5.4, quality: 0.91, p95LatencyMs: 2400, failureRate: 0.006, capabilities: ["json", "tools"] }
];

// Key generation is shown inline for the demo. A real customer keeps the private
// key in KMS/Vault/HSM and registers only its public key with the router.
const { privateKey, publicKey } = generateKeyPairSync("ed25519");

// Compilation and signing happen locally. Only the signed tokens cross the boundary.
const now = new Date("2026-10-06T12:00:00Z");
const localPolicies = [
  compileShadowPolicy({ provider: "aws", amountUsd: 120_000, usedUsd: 82_000, forecastRemainingUsd: 21_000, endsAt: "2026-10-20", prepaid: true, eligibleModels: ["bedrock/claude-sonnet"], maxTrafficShare: 0.25 }, now),
  compileShadowPolicy({ provider: "openai", amountUsd: 40_000, usedUsd: 35_000, forecastRemainingUsd: 7_000, endsAt: "2026-12-31", prepaid: true, eligibleModels: ["openai/gpt-4.1"], maxTrafficShare: 0.25 }, now)
];
const policyTokens = localPolicies.map((policy) => signShadowPolicy(policy, {
  issuer: "customer-acme",
  audience: "commit-aware-router",
  keyId: "acme-2026-01",
  privateKey,
  now
}));

const decision = routeWithSignedPolicies({
  minQuality: 0.89,
  maxP95LatencyMs: 3000,
  requiredCapabilities: ["json", "tools"],
  failurePenaltyUsd: 200,
  latencyPenaltyUsdPerSecond: 0.05,
  providerTrafficShares: { aws: 0.12, openai: 0.18, anthropic: 0.70 }
}, candidates, policyTokens, {
  expectedIssuer: "customer-acme",
  expectedAudience: "commit-aware-router",
  trustedPublicKeys: { "acme-2026-01": publicKey }
}, now);

console.log(`Verified ${policyTokens.length} signed policies.`);
console.log(JSON.stringify(decision, null, 2));
