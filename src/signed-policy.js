import { randomUUID, sign, verify } from "node:crypto";

const MAX_TOKEN_BYTES = 16_384;

function encodeJson(value) {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function decodeJson(value, label) {
  try {
    return JSON.parse(Buffer.from(value, "base64url").toString("utf8"));
  } catch {
    throw new Error(`Invalid signed policy ${label}.`);
  }
}

function assertPolicyShape(policy) {
  if (typeof policy.provider !== "string" || !policy.provider) {
    throw new Error("Policy provider must be a non-empty string.");
  }
  if (!Number.isFinite(policy.shadowPriceUsdPerDollar)
      || policy.shadowPriceUsdPerDollar < 0
      || policy.shadowPriceUsdPerDollar > 0.85) {
    throw new Error("Policy shadow price must be between 0 and 0.85.");
  }
  if (!Number.isFinite(policy.maxTrafficShare)
      || policy.maxTrafficShare < 0
      || policy.maxTrafficShare > 1) {
    throw new Error("Policy traffic share must be between 0 and 1.");
  }
  if (!Array.isArray(policy.eligibleModels)
      || policy.eligibleModels.length > 100
      || policy.eligibleModels.some((model) => typeof model !== "string" || !model)) {
    throw new Error("Policy must contain at most 100 non-empty eligible model IDs.");
  }
}

/**
 * Creates a compact JWS using Ed25519 (the JWS `EdDSA` algorithm).
 * This runs inside the customer's boundary; the private key never leaves it.
 */
export function signShadowPolicy(policy, options) {
  assertPolicyShape(policy);
  const now = options.now ?? new Date();
  const issuedAt = Math.floor(now.getTime() / 1000);
  const expiresAt = Math.floor(new Date(policy.notAfter).getTime() / 1000);
  if (!Number.isFinite(expiresAt) || expiresAt <= issuedAt) {
    throw new Error("Policy expiration must be after its issue time.");
  }
  if (!options.privateKey || !options.issuer || !options.audience || !options.keyId) {
    throw new Error("Signing requires privateKey, issuer, audience, and keyId.");
  }

  const header = { alg: "EdDSA", typ: "CARP", kid: options.keyId };
  const payload = {
    iss: options.issuer,
    aud: options.audience,
    jti: options.policyId ?? randomUUID(),
    iat: issuedAt,
    nbf: issuedAt,
    exp: expiresAt,
    provider: policy.provider,
    shadowPriceUsdPerDollar: policy.shadowPriceUsdPerDollar,
    eligibleModels: policy.eligibleModels,
    maxTrafficShare: policy.maxTrafficShare,
    policyVersion: policy.policyVersion
  };
  const encodedHeader = encodeJson(header);
  const encodedPayload = encodeJson(payload);
  const signingInput = `${encodedHeader}.${encodedPayload}`;
  const signature = sign(null, Buffer.from(signingInput), options.privateKey).toString("base64url");
  return `${signingInput}.${signature}`;
}

/**
 * Verifies origin, integrity, intended recipient, lifetime, and revocation.
 * `trustedPublicKeys` is scoped to `expectedIssuer` and indexed by key ID.
 */
export function verifyShadowPolicyToken(token, options) {
  if (typeof token !== "string" || Buffer.byteLength(token) > MAX_TOKEN_BYTES) {
    throw new Error("Signed policy is missing or too large.");
  }
  const parts = token.split(".");
  if (parts.length !== 3 || parts.some((part) => !part)) {
    throw new Error("Signed policy must have three compact JWS parts.");
  }

  const [encodedHeader, encodedPayload, encodedSignature] = parts;
  const header = decodeJson(encodedHeader, "header");
  const payload = decodeJson(encodedPayload, "payload");
  if (header.alg !== "EdDSA" || header.typ !== "CARP" || typeof header.kid !== "string") {
    throw new Error("Signed policy uses an unsupported header.");
  }

  const keyRegistry = options.trustedPublicKeys;
  const publicKey = keyRegistry && Object.hasOwn(keyRegistry, header.kid)
    ? keyRegistry[header.kid]
    : undefined;
  if (!publicKey) throw new Error("Signed policy key is not trusted.");
  const validSignature = verify(
    null,
    Buffer.from(`${encodedHeader}.${encodedPayload}`),
    publicKey,
    Buffer.from(encodedSignature, "base64url")
  );
  if (!validSignature) throw new Error("Signed policy signature is invalid.");

  const nowSeconds = Math.floor((options.now ?? new Date()).getTime() / 1000);
  const clockSkewSeconds = options.clockSkewSeconds ?? 30;
  const maxTtlSeconds = options.maxTtlSeconds ?? 86_400;
  if (payload.iss !== options.expectedIssuer) throw new Error("Signed policy issuer is invalid.");
  if (payload.aud !== options.expectedAudience) throw new Error("Signed policy audience is invalid.");
  if (typeof payload.jti !== "string" || !payload.jti) throw new Error("Signed policy ID is missing.");
  if (![payload.iat, payload.nbf, payload.exp].every(Number.isFinite)) {
    throw new Error("Signed policy timestamps are invalid.");
  }
  if (payload.iat > nowSeconds + clockSkewSeconds || payload.nbf > nowSeconds + clockSkewSeconds) {
    throw new Error("Signed policy is not active yet.");
  }
  if (payload.exp <= nowSeconds - clockSkewSeconds) throw new Error("Signed policy has expired.");
  if (payload.exp <= payload.nbf || payload.exp - payload.iat > maxTtlSeconds) {
    throw new Error("Signed policy lifetime is invalid.");
  }
  if (options.revokedPolicyIds?.has(payload.jti)) throw new Error("Signed policy has been revoked.");

  const policy = {
    provider: payload.provider,
    shadowPriceUsdPerDollar: payload.shadowPriceUsdPerDollar,
    eligibleModels: payload.eligibleModels,
    maxTrafficShare: payload.maxTrafficShare,
    notAfter: new Date(payload.exp * 1000).toISOString(),
    policyVersion: payload.policyVersion,
    verification: {
      issuer: payload.iss,
      keyId: header.kid,
      policyId: payload.jti
    }
  };
  assertPolicyShape(policy);
  return policy;
}
