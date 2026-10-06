import test from "node:test";
import assert from "node:assert/strict";
import { route } from "../src/router.js";
import { compileShadowPolicy } from "../src/policy.js";

test("compiled policy does not contain commitment, usage, or forecast amounts", () => {
  const policy = compileShadowPolicy({ provider: "aws", amountUsd: 100, usedUsd: 30, forecastRemainingUsd: 80, endsAt: "2026-12-01", prepaid: true, eligibleModels: ["model"] }, new Date("2026-10-01"));
  assert.equal(policy.shadowPriceUsdPerDollar, 0);
  const serialized = JSON.stringify(policy);
  for (const forbidden of ["amountUsd", "usedUsd", "forecastRemainingUsd", "endsAt", "prepaid"]) {
    assert.equal(serialized.includes(forbidden), false);
  }
});

test("a genuine stranded prepaid commitment can break a small cost tie", () => {
  const result = route(
    { minQuality: 0.8, maxP95LatencyMs: 3000, failurePenaltyUsd: 0, latencyPenaltyUsdPerSecond: 0, requiredCapabilities: [] },
    [
      { id: "cheap", provider: "direct", costPerMillionTokensUsd: 5, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] },
      { id: "committed", provider: "aws", costPerMillionTokensUsd: 5.4, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] }
    ],
    { aws: { provider: "aws", shadowPriceUsdPerDollar: 0.85, eligibleModels: ["committed"], maxTrafficShare: 0.25, notAfter: "2026-10-07T00:00:00Z", policyVersion: "v1" } },
    new Date("2026-10-06")
  );
  assert.equal(result.target, "committed");
});

test("quality constraints outrank a commitment", () => {
  const result = route(
    { minQuality: 0.95, maxP95LatencyMs: 3000, failurePenaltyUsd: 0, latencyPenaltyUsdPerSecond: 0, requiredCapabilities: [] },
    [
      { id: "committed", provider: "aws", costPerMillionTokensUsd: 1, quality: 0.8, p95LatencyMs: 100, failureRate: 0, capabilities: [] },
      { id: "qualified", provider: "direct", costPerMillionTokensUsd: 8, quality: 0.96, p95LatencyMs: 100, failureRate: 0, capabilities: [] }
    ],
    { aws: { provider: "aws", shadowPriceUsdPerDollar: 0.85, eligibleModels: ["committed"], maxTrafficShare: 0.25, notAfter: "2026-10-07T00:00:00Z", policyVersion: "v1" } },
    new Date("2026-10-06")
  );
  assert.equal(result.target, "qualified");
});

test("expired shadow policies have no routing effect", () => {
  const result = route(
    { minQuality: 0.8, maxP95LatencyMs: 3000, failurePenaltyUsd: 0, latencyPenaltyUsdPerSecond: 0, requiredCapabilities: [] },
    [
      { id: "cheap", provider: "direct", costPerMillionTokensUsd: 5, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] },
      { id: "committed", provider: "aws", costPerMillionTokensUsd: 8, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] }
    ],
    { aws: { provider: "aws", shadowPriceUsdPerDollar: 0.85, eligibleModels: ["committed"], maxTrafficShare: 0.25, notAfter: "2026-10-05T00:00:00Z", policyVersion: "v1" } },
    new Date("2026-10-06")
  );
  assert.equal(result.target, "cheap");
});

test("traffic caps stop a shadow price from shifting more requests", () => {
  const result = route(
    { minQuality: 0.8, maxP95LatencyMs: 3000, failurePenaltyUsd: 0, latencyPenaltyUsdPerSecond: 0, requiredCapabilities: [], providerTrafficShares: { aws: 0.25 } },
    [
      { id: "cheap", provider: "direct", costPerMillionTokensUsd: 5, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] },
      { id: "committed", provider: "aws", costPerMillionTokensUsd: 8, quality: 0.9, p95LatencyMs: 100, failureRate: 0, capabilities: [] }
    ],
    { aws: { provider: "aws", shadowPriceUsdPerDollar: 0.85, eligibleModels: ["committed"], maxTrafficShare: 0.25, notAfter: "2026-10-07T00:00:00Z", policyVersion: "v1" } },
    new Date("2026-10-06")
  );
  assert.equal(result.target, "cheap");
});
