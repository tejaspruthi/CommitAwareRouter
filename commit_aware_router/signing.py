from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Collection, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .models import ShadowPolicy

MAX_TOKEN_BYTES = 16_384
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")


class PolicyVerificationError(ValueError):
    pass


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str, label: str) -> bytes:
    if not value or not _BASE64URL.fullmatch(value):
        raise PolicyVerificationError(f"Invalid signed policy {label} encoding.")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise PolicyVerificationError(f"Invalid signed policy {label} encoding.") from exc
    if _encode(decoded) != value:
        raise PolicyVerificationError(f"Non-canonical signed policy {label} encoding.")
    return decoded


def _json_part(value: object) -> str:
    return _encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())


def generate_keypair(private_path: Path, public_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    private_path.chmod(0o600)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Signing key must be an Ed25519 private key.")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Verification key must be an Ed25519 public key.")
    return key


def sign_shadow_policy(
    policy: ShadowPolicy,
    *,
    private_key: Ed25519PrivateKey,
    issuer: str,
    audience: str,
    key_id: str,
    policy_id: str | None = None,
    now: datetime | None = None,
) -> str:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    issued_at = int(now.timestamp())
    expires_at = int(policy.not_after.timestamp())
    if expires_at <= issued_at:
        raise ValueError("Policy expiration must be after its issue time.")
    if not all((issuer, audience, key_id)):
        raise ValueError("Signing requires issuer, audience, and key_id.")

    header = {"alg": "EdDSA", "kid": key_id, "typ": "CARP"}
    # This explicit allowlist is the non-disclosure boundary. Never replace it
    # with asdict(policy) or serialization of the commitment input.
    payload = {
        "aud": audience,
        "eligibleModels": list(policy.eligible_models),
        "exp": expires_at,
        "iat": issued_at,
        "iss": issuer,
        "jti": policy_id or str(uuid.uuid4()),
        "maxTrafficShare": policy.max_traffic_share,
        "nbf": issued_at,
        "policyVersion": policy.policy_version,
        "scopeId": policy.scope_id,
        "marginalValueUsdPerDollar": policy.marginal_value_usd_per_dollar,
        "blocked": policy.blocked,
    }
    encoded_header = _json_part(header)
    encoded_payload = _json_part(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    return f"{signing_input.decode()}.{_encode(private_key.sign(signing_input))}"


def verify_shadow_policy_token(
    token: str,
    *,
    expected_issuer: str,
    expected_audience: str,
    trusted_public_keys: Mapping[str, Ed25519PublicKey],
    now: datetime | None = None,
    revoked_policy_ids: Collection[str] = (),
    clock_skew_seconds: int = 30,
    max_ttl_seconds: int = 86_400,
) -> ShadowPolicy:
    if not isinstance(token, str) or len(token.encode()) > MAX_TOKEN_BYTES:
        raise PolicyVerificationError("Signed policy is missing or too large.")
    parts = token.split(".")
    if len(parts) != 3:
        raise PolicyVerificationError("Signed policy must have three compact JWS parts.")
    encoded_header, encoded_payload, encoded_signature = parts
    try:
        header = json.loads(_decode(encoded_header, "header"))
        payload = json.loads(_decode(encoded_payload, "payload"))
    except json.JSONDecodeError as exc:
        raise PolicyVerificationError("Signed policy contains invalid JSON.") from exc
    if header.get("alg") != "EdDSA" or header.get("typ") != "CARP":
        raise PolicyVerificationError("Signed policy uses an unsupported header.")
    key_id = header.get("kid")
    if not isinstance(key_id, str) or key_id not in trusted_public_keys:
        raise PolicyVerificationError("Signed policy key is not trusted.")
    try:
        trusted_public_keys[key_id].verify(
            _decode(encoded_signature, "signature"),
            f"{encoded_header}.{encoded_payload}".encode(),
        )
    except InvalidSignature as exc:
        raise PolicyVerificationError("Signed policy signature is invalid.") from exc

    now_seconds = int((now or datetime.now(UTC)).timestamp())
    if payload.get("iss") != expected_issuer:
        raise PolicyVerificationError("Signed policy issuer is invalid.")
    if payload.get("aud") != expected_audience:
        raise PolicyVerificationError("Signed policy audience is invalid.")
    policy_id = payload.get("jti")
    if not isinstance(policy_id, str) or not policy_id:
        raise PolicyVerificationError("Signed policy ID is missing.")
    timestamps = (payload.get("iat"), payload.get("nbf"), payload.get("exp"))
    if not all(isinstance(value, int) for value in timestamps):
        raise PolicyVerificationError("Signed policy timestamps are invalid.")
    issued_at, not_before, expires_at = timestamps
    if issued_at > now_seconds + clock_skew_seconds or not_before > now_seconds + clock_skew_seconds:
        raise PolicyVerificationError("Signed policy is not active yet.")
    if expires_at <= now_seconds - clock_skew_seconds:
        raise PolicyVerificationError("Signed policy has expired.")
    if expires_at <= not_before or expires_at - issued_at > max_ttl_seconds:
        raise PolicyVerificationError("Signed policy lifetime is invalid.")
    if policy_id in revoked_policy_ids:
        raise PolicyVerificationError("Signed policy has been revoked.")

    try:
        scope_id = payload["scopeId"]
        marginal_value = float(payload["marginalValueUsdPerDollar"])
        models = tuple(payload["eligibleModels"])
        max_share = float(payload["maxTrafficShare"])
        blocked = payload.get("blocked", False)
        if not isinstance(scope_id, str) or not scope_id or not isinstance(blocked, bool):
            raise TypeError
        if not -0.85 <= marginal_value <= 0.85 or not 0 <= max_share <= 1:
            raise TypeError
        if len(models) > 100 or any(not isinstance(model, str) or not model for model in models):
            raise TypeError
    except (KeyError, TypeError, ValueError) as exc:
        raise PolicyVerificationError("Signed policy fields are invalid.") from exc

    return ShadowPolicy(
        scope_id=scope_id,
        marginal_value_usd_per_dollar=marginal_value,
        eligible_models=models,
        max_traffic_share=max_share,
        not_after=datetime.fromtimestamp(expires_at, UTC),
        blocked=blocked,
        policy_version=str(payload.get("policyVersion", "v1")),
        verification={"issuer": expected_issuer, "key_id": key_id, "policy_id": policy_id},
    )
