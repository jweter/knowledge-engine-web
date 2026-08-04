# Ask Synthesis Availability Plan

## Status

Approved implementation plan for making `/ask` capability-aware on deployments
that do not run an LLM backend.

## Problem

The hosted Render alpha intentionally does not run Ollama, but the `/ask` form
still presents an enabled synthesis checkbox. A visitor can request synthesis
and receive an implementation-facing message that `KE_WEB_LLM_MODEL` must be
set.

Retrieval continues to work correctly, but the page invites a request the
deployment cannot fulfill. That is a public-interface defect, not a retrieval
or model failure.

## Decision

Treat a non-empty `Settings.llm_model` as the deployment's declared synthesis
capability.

- When configured, retain the existing opt-in checkbox and synthesis behavior.
- When unconfigured, render a disabled checkbox labeled as unavailable on this
  deployment and state that Ask remains retrieval-only.
- If a caller manually supplies `synthesize=1` while unconfigured, do not
  instantiate an LLM and do not expose environment-variable instructions.
  Render normal retrieval results with a neutral retrieval-only notice.
- If a configured Ollama service later fails at runtime, retain the existing
  inline `LocalLLMError` behavior so retrieval results still survive.

This is configuration capability, not a live Ollama health check. Performing a
network request on every form render would add latency and couple ordinary
retrieval to inference health.

## Template Context

Every `/ask` response will provide:

- `synthesis_available`: whether an LLM model is configured;
- `synthesize_requested`: true only when synthesis was requested and available;
- `synthesis_unavailable_notice`: a neutral message only when an unavailable
  deployment receives a forged or stale `synthesize=1` query;
- `synthesis`: generated narrative when successful; and
- `synthesis_error`: configured-backend runtime failure when applicable.

The initial empty form and result pages use the same complete context shape.

## User Interface

Configured deployment:

```text
[ ] Also generate an AI synthesis (local model, real inference -- not free)
```

Unconfigured deployment:

```text
[disabled] AI synthesis unavailable on this deployment; Ask is retrieval-only.
```

The disabled state remains visible because it truthfully communicates the
alpha's current capability without suggesting that retrieval itself is broken.
It must not mention environment-variable names or operator setup instructions.

## Defensive Request Behavior

For `GET /ask?q=...&synthesize=1` on an unconfigured deployment:

1. trim and validate the question as usual;
2. run retrieval as usual;
3. do not construct `OllamaLLM`;
4. do not call `synthesize_answer`;
5. normalize `synthesize_requested` to false;
6. show a short retrieval-only notice; and
7. return HTTP 200 with the normal ranked results.

This is a safe capability downgrade rather than a request error because the
primary `/ask` operation is retrieval and remains available.

## Tests

Add or update tests proving:

- the empty unconfigured form renders a disabled control and retrieval-only
  label;
- environment-variable names are absent from visitor-facing HTML;
- a configured deployment renders an enabled unchecked control;
- an unconfigured forged request performs retrieval, shows the neutral notice,
  and never instantiates or calls the LLM;
- a configured synthesis request still renders a grounded narrative;
- a configured but unreachable Ollama backend still renders its sanitized
  runtime error inline;
- an ordinary retrieval request renders no synthesis result panel;
- synthesis remains opt-in and never becomes evidence or scientific review;
  and
- existing retrieval ranking and evidence display remain unchanged.

## Documentation

Update:

- `README.md`;
- `docs/deployment.md`;
- `docs/web_design.md`; and
- this plan.

The repository currently has no changelog file, so no changelog will be
invented solely for this small correction.

## Non-Goals

This change does not:

- install or launch Ollama;
- set Render environment variables;
- make a laptop serve the public deployment;
- add a hosted model provider or API key;
- perform inference availability probes during page rendering;
- add authentication, quotas, billing, or model routing;
- change retrieval ranking or Evidence Intelligence;
- make AI narration evidence or scientific review; or
- implement the persistent-host migration.

## Hosted Inference Trigger

Real public synthesis remains a later architecture decision. Revisit it only
when the project has chosen and documented:

- a durable inference host reachable by the web deployment;
- authentication and authorization;
- request limits and resource/cost controls;
- privacy and logging behavior;
- model/version provenance;
- timeout and outage behavior; and
- a parity-tested consumer boundary.

Until then, Render is intentionally retrieval-only and must say so cleanly.

## Success Criteria

The milestone succeeds when:

- the live-alpha configuration no longer presents an actionable synthesis
  control;
- ordinary visitors never see `KE_WEB_LLM_MODEL` setup errors;
- forged synthesis queries cannot invoke an unconfigured backend;
- configured local/LAN synthesis remains unchanged;
- all repository tests and quality checks pass;
- PR and post-merge `main` CI pass; and
- no hosted-inference architecture is added by implication.

## Next Handoff

After this public-interface correction, return to the core roadmap's next
bounded analytical task: design one source-audited binary-outcome verification
contract using explicit event counts, denominators, estimand, confidence
method, and correction policy. Hosted LLM narration remains deferred until its
trigger conditions are met.
