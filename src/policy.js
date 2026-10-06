const DAY_MS = 86_400_000;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function quantize(value, step) {
  return Math.round(value / step) * step;
}

/**
 * Runs inside the customer's finance/security boundary.
 *
 * The input is sensitive and must not be logged or sent to the routing service.
 * The returned policy deliberately loses information: it expresses marginal
 * routing value, not contract size, usage, or the underlying forecast.
 */
export function compileShadowPolicy(secret, now = new Date()) {
  const remainingCommit = Math.max(0, secret.amountUsd - secret.usedUsd);
  const strandedDollars = Math.max(
    0,
    remainingCommit - Math.max(0, secret.forecastRemainingUsd)
  );
  const daysRemaining = Math.max(
    1,
    Math.ceil((new Date(secret.endsAt).getTime() - now.getTime()) / DAY_MS)
  );
  const urgency = clamp(
    (strandedDollars / Math.max(1, remainingCommit)) * (30 / daysRemaining),
    0,
    1
  );
  const rawShadowPrice = (secret.prepaid ? 0.85 : 0.25) * urgency;

  // Coarse buckets reduce how much contract state can be inferred from a token.
  const shadowPriceUsdPerDollar = clamp(quantize(rawShadowPrice, 0.05), 0, 0.85);
  const ttlMinutes = Math.min(secret.policyTtlMinutes ?? 60, 24 * 60);

  return {
    provider: secret.provider,
    shadowPriceUsdPerDollar,
    eligibleModels: [...secret.eligibleModels],
    maxTrafficShare: clamp(secret.maxTrafficShare ?? 0.25, 0, 1),
    notAfter: new Date(now.getTime() + ttlMinutes * 60_000).toISOString(),
    policyVersion: secret.policyVersion ?? "v1"
  };
}
