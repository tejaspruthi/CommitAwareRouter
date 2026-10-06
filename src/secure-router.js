import { route } from "./router.js";
import { verifyShadowPolicyToken } from "./signed-policy.js";

/**
 * Hosted entry point: no policy reaches the scoring engine until it verifies.
 */
export function routeWithSignedPolicies(
  request,
  candidates,
  policyTokens,
  verificationOptions,
  now = new Date()
) {
  const policies = Object.create(null);
  for (const token of policyTokens) {
    const policy = verifyShadowPolicyToken(token, { ...verificationOptions, now });
    if (policies[policy.provider]) {
      throw new Error(`Multiple active policies supplied for provider ${policy.provider}.`);
    }
    policies[policy.provider] = policy;
  }
  return route(request, candidates, policies, now);
}
