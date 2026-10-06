from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .policy import CommitmentSecret, compile_shadow_policy
from .signing import generate_keypair, load_private_key, sign_shadow_policy


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Datetime values must include a timezone.")
    return parsed.astimezone(UTC)


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, separators=(",", ":"))
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _keys(args: argparse.Namespace) -> None:
    private_path = Path(args.private_key)
    public_path = Path(args.public_key)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    generate_keypair(private_path, public_path)
    print(f"Created customer signing key and router public key at {private_path} and {public_path}.")


def _compile(args: argparse.Namespace) -> None:
    config = yaml.safe_load(Path(args.config).read_text())
    now = _datetime(args.as_of) if args.as_of else datetime.now(UTC)
    private_key = load_private_key(Path(args.private_key))
    tokens: list[str] = []
    for item in config.get("commitments", []):
        secret = CommitmentSecret(
            scope_id=str(item["scope_id"]),
            amount_usd=float(item["amount_usd"]),
            used_usd=float(item["used_usd"]),
            forecast_remaining_usd=float(item["forecast_remaining_usd"]),
            ends_at=_datetime(str(item["ends_at"])),
            eligible_models=tuple(item["eligible_models"]),
            commitment_type=str(item.get("commitment_type", "minimum")),
            prepaid=bool(item.get("prepaid", True)),
            hard_limit=bool(item.get("hard_limit", False)),
            max_traffic_share=float(item.get("max_traffic_share", 0.25)),
            policy_ttl_minutes=int(item.get("policy_ttl_minutes", 60)),
            policy_version=str(item.get("policy_version", "v1")),
        )
        policy = compile_shadow_policy(secret, now=now)
        tokens.append(
            sign_shadow_policy(
                policy,
                private_key=private_key,
                issuer=args.issuer,
                audience=args.audience,
                key_id=args.key_id,
                now=now,
            )
        )
    output = Path(args.output)
    _atomic_json(output, {"tokens": tokens, "generated_at": now.isoformat()})
    print(f"Wrote {len(tokens)} signed policies to {output}; no commitment amounts were serialized.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="commit-aware")
    subparsers = parser.add_subparsers(dest="command", required=True)

    keys = subparsers.add_parser("generate-keys", help="Generate a customer-local Ed25519 key pair.")
    keys.add_argument("--private-key", required=True)
    keys.add_argument("--public-key", required=True)
    keys.set_defaults(func=_keys)

    compile_command = subparsers.add_parser("compile", help="Compile and sign local commitments.")
    compile_command.add_argument("--config", required=True)
    compile_command.add_argument("--private-key", required=True)
    compile_command.add_argument("--output", required=True)
    compile_command.add_argument("--issuer", required=True)
    compile_command.add_argument("--audience", default="commit-aware-router")
    compile_command.add_argument("--key-id", required=True)
    compile_command.add_argument("--as-of", help="RFC 3339 time for deterministic demos.")
    compile_command.set_defaults(func=_compile)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
