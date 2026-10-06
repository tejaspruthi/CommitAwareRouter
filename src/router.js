/**
 * Commitment-aware model selection.
 *
 * This intentionally selects a provider/model rather than proxying requests.
 * Put LiteLLM, OpenRouter, or a provider SDK behind the returned `target`.
 */
function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

/**
 * Read a privacy-preserving policy produced inside the customer's boundary.
 * The router never needs the commitment, actual usage, expiry, or forecast.
 */
export function commitmentSignal(policy, candidateId, now = new Date()) {
  if (!policy) return { benefitRate: 0, active: false };
  if (new Date(policy.notAfter).getTime() <= now.getTime()) {
    return { benefitRate: 0, active: false };
  }
  if (!(policy.eligibleModels ?? []).includes(candidateId)) {
    return { benefitRate: 0, active: false };
  }
  return {
    benefitRate: clamp(policy.shadowPriceUsdPerDollar ?? 0, 0, 0.85),
    active: true,
    maxTrafficShare: clamp(policy.maxTrafficShare ?? 0, 0, 1),
    policyVersion: policy.policyVersion
  };
}

function eligible(candidate, request) {
  if (candidate.quality < request.minQuality) return false;
  if (candidate.p95LatencyMs > request.maxP95LatencyMs) return false;
  return (request.requiredCapabilities ?? []).every((capability) =>
    candidate.capabilities.includes(capability)
  );
}

/**
 * Returns the highest-scoring model and an auditable explanation.
 * Scores are USD-equivalent cost per 1M blended tokens; lower is better.
 */
export function route(request, candidates, shadowPolicies = {}, now = new Date()) {
  const evaluated = candidates
    .filter((candidate) => eligible(candidate, request))
    .map((candidate) => {
      const policySignal = commitmentSignal(shadowPolicies[candidate.provider], candidate.id, now);
      const currentTrafficShare = request.providerTrafficShares?.[candidate.provider] ?? 0;
      const signal = policySignal.active && currentTrafficShare >= policySignal.maxTrafficShare
        ? { ...policySignal, active: false, benefitRate: 0, trafficCapReached: true }
        : policySignal;
      const rawCost = candidate.costPerMillionTokensUsd;
      const effectiveCost = rawCost * (1 - signal.benefitRate);
      const score = effectiveCost
        + candidate.failureRate * request.failurePenaltyUsd
        + (candidate.p95LatencyMs / 1000) * request.latencyPenaltyUsdPerSecond;
      return { candidate, rawCost, effectiveCost, score, signal };
    })
    .sort((a, b) => a.score - b.score);

  if (!evaluated.length) {
    throw new Error("No route meets the request's quality, latency, and capability constraints.");
  }

  const winner = evaluated[0];
  return {
    target: winner.candidate.id,
    provider: winner.candidate.provider,
    reason: winner.signal.active && winner.signal.benefitRate > 0
      ? `Eligible route; an active ${winner.candidate.provider} shadow-price policy changed its effective cost.`
      : "Eligible route with the best cost, reliability, and latency score.",
    decision: {
      rawCostPerMillionTokensUsd: winner.rawCost,
      commitmentAdjustedCostPerMillionTokensUsd: winner.effectiveCost,
      commitmentBenefitRate: winner.signal.benefitRate,
      score: winner.score
    },
    alternatives: evaluated.slice(1).map(({ candidate, score }) => ({ id: candidate.id, score }))
  };
}
