# AI-O16 Public Research Copilot Guardrails

## Status

Implementation plan and operator contract for the compute-bearing `/ask`
Research Copilot path. Deterministic retrieval remains independently available.

## Objective

Bound the latency and resource use of one Research Copilot request before the
optional workflow can be enabled on a publicly reachable deployment. A visitor
must never see a hung page, an unlabeled partial answer, or a scientific-looking
result whose orchestration failed invisibly.

## Preconditions

- AI-O14 capability-gates the composed `run_research_question` workflow.
- AI-O15 requires hosted sessions to live inside a verified persistent mount.
- `knowledge-engine-ai` provides one shared execution budget that bounds the
  concrete `ke` subprocess and Ollama boundaries.

These controls do not provide the missing hosted core runtime, corpus files,
persistent disk, or authenticated inference service. Render remains
retrieval-only until an operator supplies and verifies those separately.

## Request Contract

An admitted Research Copilot request:

1. has one positive wall-clock budget;
2. holds one global concurrency slot for the complete composed run;
3. counts once against a per-client fixed-window allowance;
4. passes the same deadline to `run_research_question`;
5. preserves its durable session and workflow events; and
6. releases its concurrency slot in a `finally` block.

The default single-instance alpha policy is:

```text
KE_WEB_AI_REQUEST_TIMEOUT_SECONDS=180
KE_WEB_AI_MAX_CONCURRENT_REQUESTS=1
KE_WEB_AI_RATE_LIMIT_REQUESTS=3
KE_WEB_AI_RATE_LIMIT_WINDOW_SECONDS=600
```

The values are operator-configurable positive numbers. They are deployment
controls, not scientific parameters.

## Admission Policy

The limiter keys requests by Starlette's normalized `request.client.host`. It
does not trust a caller-supplied forwarding header inside application code.
The hosting stack remains responsible for providing the correct client address
through its trusted proxy configuration.

Only admitted Research Copilot requests consume the fixed-window allowance.
Busy rejections do not. Expired buckets are removed during subsequent
admissions so the in-memory map does not retain inactive clients indefinitely.

The concurrency ceiling is process-local. The rate limit is also in-memory and
process-local. That is sufficient for the current single-instance,
password-gated alpha and deliberately avoids Redis, a queue, or distributed
coordination before the project has multi-instance traffic.

## Failure UX

- The Ask form displays a running state immediately when Research Copilot is
  selected, disables duplicate submission, and keeps ordinary retrieval as the
  promised fallback.
- A busy request receives a neutral "already processing" message.
- A rate-limited request receives a neutral "wait and try again" message.
- A deadline failure states that the execution limit was reached.
- Raw exceptions, paths, prompts, model output, client identifiers, and
  operator settings are never rendered.
- No failed or rejected AI request hides the deterministic retrieval results.

HTTP remains `200` for these optional-AI outcomes because the requested Ask page
and deterministic retrieval completed successfully. The inline status describes
the optional Research Copilot outcome.

## Security Boundary

This is a fairness and resource-safety layer for authenticated alpha users, not
a denial-of-service defense. Basic authentication remains required. Public
enablement also requires a non-public authenticated inference endpoint; a
laptop Ollama listener must not be exposed to the internet.

## Tests

Tests must cover:

- valid and invalid configuration;
- admitted, busy, and rate-limited requests;
- fixed-window expiry;
- slot release after success and failure;
- propagation of the execution deadline;
- sanitized timeout output;
- immediate browser running state;
- preservation of deterministic retrieval; and
- unchanged retrieval-only behavior when capability is unavailable.

## Non-Goals

AI-O16 does not add:

- hosted inference;
- a Render persistent disk;
- multi-instance rate limiting;
- a task queue, cancellation API, or background job dashboard;
- user accounts beyond the existing alpha gate;
- session-history or resume UI;
- new retrieval, evidence, verification, or synthesis behavior; or
- scientific review, consensus, or truth determination.

## Completion Gate

AI-O16 is complete when local tests, container smoke tests, dependency audit,
and GitHub CI pass; a deliberately busy request and a deliberately rejected
request fail honestly; and the Render deployment remains fail closed until all
hosted prerequisites exist.

## Next Handoff

AI-O17 completed the end-to-end verification on a fully configured local
deployment; see `docs/ai_o17_live_verification.md`. The same rehearsal remains
required on Render only after an operator supplies a durable session disk,
core runtime and corpus inputs, and a secured hosted inference service. The
local result does not silently satisfy those deployment decisions.
