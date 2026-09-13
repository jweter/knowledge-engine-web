# Unattended Verification Policy

Routine engineering verification is machine-owned. Jeremy is not a recurring test executor and must not be placed inside ordinary implementation, regression, environment, Product Reality, or promotion loops when objective evidence can be automated or collected by an unattended worker.

## Default verification path

`change -> FAST_GATE -> exact-head preflight -> CI -> unattended environment-specific verification -> structured evidence -> automated diagnosis/repair -> re-verification -> promotion -> optional Jeremy milestone acceptance`

Environment dependence is not automatically human dependence. Tests requiring browser/service integration, local APIs, Ollama/Core connectivity, packaged desktop execution, or another non-CI environment should first be scheduled to an approved unattended worker.

## Evidence classification

Use this order:

1. Repository-native deterministic test.
2. Unattended environment test.
3. Automatable Product Reality probe using logs, metrics, traces, screenshots, artifacts, timing, accessibility checks, or machine-readable observations.
4. Human judgment only when genuinely subjective, ambiguous, irreversible, safety-sensitive, or product-direction dependent.

`Jeremy must run this manually` is a workflow deficiency unless category 4 actually applies.

## Worker contract

An unattended worker must identify repository, branch, exact SHA, request, environment, and timestamp; record bounded commands/actions and evidence; return `PASS`, `FAIL`, `REVIEW_REQUIRED`, `PRODUCT_REALITY_REQUIRED`, or `ENVIRONMENT_FAILURE`; write permitted results back to the issue/PR/evidence ledger; fail closed on missing evidence; preserve secrets/privacy; and leave the machine safe. It must not require Jeremy to watch, click ordinary steps, copy logs, or manually relay completion.

Pending worker verification blocks only the dependent lane. Parallel-safe work continues.

## Knowledge Engine Web application

Browser/API integration, grounded-answer rendering, accessibility checks, service-connectivity verification, screenshot/DOM evidence, local Core/Ollama-backed research flows, and other objective environment-specific acceptance should be automated through CI or an unattended worker. Exact commit and environment/configuration identity must travel with the evidence.

Jeremy may test milestones whenever useful, but routine launch checks, repeated browser walkthroughs, log copying, regression verification, and service-connectivity checks should be engineered out of his workflow.

Every recurring manual test is therefore a candidate automation defect: prefer a deterministic assertion, browser automation, fixture/simulator, CI job, unattended worker task, machine-readable result, and durable regression guard over another manual request.
