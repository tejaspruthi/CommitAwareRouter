# Commit-Aware Router

A routing layer for organizations that want AI traffic decisions to reflect the commitments they've already made.

Most AI routers choose between eligible models based on price, quality, latency, reliability, and availability. Commit-Aware Router also considers the organization's commercial commitments across model providers and cloud platforms.

It's an early open-source proof of concept for enterprises managing multiple AI and cloud agreements. The goal is to help their routing decisions support those commitments without sending sensitive contract amounts or forecasts to the routing layer.

## Why it exists

A sensible choice for one request can still be an expensive choice for the business.

For example, a team might choose the model with the lowest list price while the company's forecast shows prepaid capacity or a minimum-spend commitment going unused elsewhere. A company might also want to reduce traffic through a channel that's approaching a commercial ceiling or an unfavorable threshold.

Finance and FinOps teams care about those outcomes. Thousands or millions of product-level routing decisions shape them. This project connects the two.

Commit-Aware Router is designed for people across these teams:

- CFO, Finance, and Strategic Finance;
- Cloud Finance, FinOps, and Procurement;
- AI Platform and Infrastructure;
- Security and Data Governance.

## What it does

The project turns guidance from Finance into a routing signal with limits on its influence. That signal can change how the router ranks eligible routes. Application requirements still come first.

The router should always enforce quality, capability, latency, reliability, residency, and policy constraints before considering commercial preferences.

Here's how the pieces fit together:

```text
customer finance data + spend forecast
                ↓
     customer-controlled policy signal
                ↓
     model routing decision and audit trail
```

Having a commitment doesn't mean “always use that vendor.” It gives the router financial context to consider for each eligible request, within defined limits.

## Privacy is a core requirement

Commit amounts, consumption, forecasts, and negotiated terms are sensitive commercial information. Customers shouldn't have to send them to a router to get commit-aware behavior.

The intended architecture keeps detailed commercial inputs inside the customer's environment. The router receives a short-lived, authenticated policy signal instead of raw contract values.

That policy can express a preference with limits, identify applicable routes, and set safety limits without exposing the underlying amount or forecast. Customers who need a stronger privacy boundary can run the policy and routing components in their own environment.

A numerical signal can still reveal something over time. The project is designed to support privacy controls such as coarse preference bands, short policy lifetimes, limited logging, and deployment under the customer's control.

## Multi-channel commitments

The model publisher, billing channel, and commercial commitment aren't always the same thing.

You might buy access to a model directly from its publisher or through a cloud platform. A commitment might cover one channel, several channels, or an enterprise-wide pool. The router keeps these separate so the customer can define eligibility explicitly. It doesn't infer coverage from a model name.

```text
Route identity
├── model publisher
├── billing channel
└── customer-defined commitment scopes
```

For example, a model accessed through a cloud marketplace might count toward a cloud commitment, a provider-wide commitment, both, or neither. It depends on the customer's actual agreement. The customer defines those rules.

## Current state

This is a proof of concept. We'd like feedback from the people who deal with this problem.

The repository currently includes:

- a Python routing implementation and LiteLLM integration example;
- customer-local policy compilation and signed policy verification;
- support for minimum-style and maximum-style commercial guidance;
- explicit commitment scopes for multi-provider and multi-channel routing;
- shadow mode for evaluating recommendations before routing production traffic;
- basic usage adapters and a transparent forecasting baseline.

It isn't a billing system, a legal interpretation engine, or a replacement for a forecast owned by Finance. The customer must validate commitment eligibility and commercial terms.

## Getting started

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[gateway]'
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m unittest discover -s tests -v
```

The [LiteLLM example](examples/litellm_plugin.py) shows how the gateway integration fits together. The [sample configuration](examples/commitments.example.yaml) is intentionally fictional. Treat it as a local-only example.

## We'd like your feedback

- How do you manage AI, cloud, and marketplace commitments today?
- Who owns the organization-level forecast of eligible AI spend?
- How should a router represent commitments that overlap across channels?
- What privacy boundary would your Finance and Security teams require?
- Should this live primarily in a model gateway, a FinOps platform, or both?

## Status

It's experimental. Don't use it to make contractual or accounting decisions without independent validation, appropriate controls, and review by the teams responsible for those commitments.
