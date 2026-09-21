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

## Implementation status (issue #160)

`knowledge_engine_web/unattended_worker.py` consumes the coordinated `WorkerRequest`/`WorkerResult`
contract anchored by `knowledge-engine-core` issue #493. Web vendors the contract in
`knowledge_engine_web/unattended_verification_contract.py` (field-for-field identical to Core's copy)
rather than importing Core as a library, so a request/result JSON document produced by either
repository's worker validates against the other's schema unchanged; keep both copies in sync.

Given a `WorkerRequest` naming `jweter/knowledge-engine-web`, an exact branch/SHA, and an
`environment_id`, the worker binds to that exact local checkout (refusing a wrong branch, a
mismatched SHA, or any dirty/untracked file before attesting identity), then executes the
requested checks:

- `preflight` — runs `engineering/preflight.py` (the same canonical gate this document's
  `FAST_GATE -> exact-head preflight` path already requires) and reports `PASS`/`FAIL` plus a
  sanitized log tail on failure.
- `ollama_health` — probes the loopback Ollama service Research capability depends on and reports
  `PASS`/`ENVIRONMENT_FAILURE`.
- `browser_ask` — runs the critical real-Chromium Ask-path tests already promoted to required CI
  (`BROWSER_ASK_TESTS` in `unattended_worker.py`, kept identical to the subset named in
  `.github/workflows/quality.yml`'s `checks` job): real browser launch, a real local server against
  an isolated fixture corpus, grounded "Direct match" answer rendering, citation navigation, an
  honest no-match response, mobile-viewport rendering, and an announced blank-submission error.
  Those tests self-skip rather than fail when no usable Chromium executable is present, so the
  worker parses the run's JUnit report rather than trusting the bare exit code: if every test
  skipped (no usable Chromium) or no report was produced at all, the check reports
  `ENVIRONMENT_FAILURE` rather than a false `PASS`; a real assertion failure reports `FAIL`.

A stale process lock is reclaimed automatically; secrets, absolute local paths, and the home
directory are stripped from every summary before it is written or published. A sanitized
`PASS`/`FAIL`/`REVIEW_REQUIRED`/`PRODUCT_REALITY_REQUIRED`/`ENVIRONMENT_FAILURE` result (exact
commit, status, failure class, completed-at timestamp, bounded summary — never the request ID,
environment ID, or raw logs) is posted to issue #160 as best-effort remote observability when a
Windows worker has `gh` available (`unattended_worker_publication.py`, mirroring Core's own
issue-#493 publisher).

`preflight` and `ollama_health` were a deliberately bounded first slice; `browser_ask` is the second,
matching Core issue #493's own precedent of adding checks incrementally rather than in one unbounded
slice. Remaining scope this issue still names but `browser_ask` does not cover: the broader
`browser_e2e` marker's accessibility/alpha-auth/keyboard-navigation coverage, screenshot evidence,
and exercising a live *deployed* target rather than an isolated local fixture server.
