# Commit-Aware Router

**A routing layer for organizations that want AI traffic decisions to reflect the commitments they have already made.**

Most AI routers choose between eligible models using price, quality, latency, reliability, and availability. Commit-Aware Router adds another input: the organization's commercial commitments across model providers and cloud platforms.

It is an early open-source proof of concept for enterprises that manage multiple AI and cloud agreements and want routing to support the financial goal of meeting those commitments—without transmitting sensitive contract amounts or forecasts to the routing layer.

## Why it exists

An organization can make a sensible decision for an individual request and still make an expensive decision for the business.

For example, a team may route to the lowest list-price model while the company is forecast to leave prepaid capacity or a minimum-spend commitment unused elsewhere. Conversely, a company may want to reduce traffic through a channel approaching a commercial ceiling or an unfavorable threshold.

Those are Finance and FinOps questions, but they are shaped by thousands or millions of product-level routing decisions. This project connects the two.

Commit-Aware Router is designed for teams spanning:

- CFO, Finance, and Strategic Finance;
- Cloud Finance, FinOps, and Procurement;
- AI Platform and Infrastructure;
- Security and Data Governance.

## What it does

The project turns finance-owned commitment guidance into a bounded routing signal. The signal can influence the ordering of otherwise eligible routes, while application requirements remain non-negotiable.

Quality, capability, latency, reliability, residency, and policy constraints should always be enforced before commercial preference is considered.

At a high level:

```text
customer finance data + spend forecast
                ↓
     customer-controlled policy signal
                ↓
     model routing decision and audit trail
```

The result is not “always use the committed vendor.” It is a controlled way to make routing aware of the economic context around each eligible request.

## Privacy is a core requirement

Commit amounts, consumption, forecasts, and negotiated terms are sensitive commercial information. A customer should not need to send them to a router to receive commit-aware behavior.

The intended architecture keeps detailed commercial inputs inside the customer's environment. The router consumes a short-lived, authenticated policy signal rather than raw contract values.

That policy can express a bounded preference, applicable routes, and safety limits without exposing the underlying amount or forecast. Customers that require a stronger boundary can run the policy and routing components in their own environment.

Privacy is not treated as a binary claim: a numerical signal can still reveal something over time. The project is designed to support privacy-preserving controls such as coarse preference bands, short policy lifetimes, limited logging, and customer-controlled deployment.

## Multi-channel commitments

Model publisher, billing channel, and commercial commitment are not always the same thing.

A model may be purchased directly from its publisher or through a cloud platform. A commitment may apply to one channel, several channels, or an enterprise-wide pool. The router models these separately so eligibility is explicit rather than inferred from a model name.

```text
Route identity
├── model publisher
├── billing channel
└── customer-defined commitment scopes
```

For example, a model accessed through a cloud marketplace might count toward a cloud commitment, a provider-wide commitment, both, or neither—depending on the customer's actual agreement. The customer defines those rules.

## Current state

This is a proof of concept built to invite feedback from the people closest to the problem.

The repository currently includes:

- a Python routing implementation and LiteLLM integration example;
- customer-local policy compilation and signed policy verification;
- support for minimum-style and maximum-style commercial guidance;
- explicit commitment scopes for multi-provider and multi-channel routing;
- shadow mode for evaluating recommendations before routing production traffic;
- basic usage adapters and a transparent forecasting baseline.

It is not a billing system, legal interpretation engine, or replacement for a finance-owned forecast. Commitment eligibility and commercial terms must be validated by the customer.

## Getting started

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[gateway]'
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m unittest discover -s tests -v
```

The [LiteLLM example](examples/litellm_plugin.py) shows the gateway integration shape. The [sample configuration](examples/commitments.example.yaml) is intentionally fictional and should be treated as a local-only example.

## What we would value feedback on

- How do you manage AI, cloud, and marketplace commitments today?
- Who owns the organization-level forecast of eligible AI spend?
- How should a router represent commitments that overlap across channels?
- What privacy boundary would your Finance and Security teams require?
- Should this live primarily in a model gateway, a FinOps platform, or both?

## Status

Experimental. Do not use it to make contractual or accounting decisions without independent validation, appropriate controls, and review by the teams responsible for those commitments.
