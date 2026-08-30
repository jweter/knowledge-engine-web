# Industry Reality Check — Knowledge Engine Web

**Assessment date:** 2026-08-29  
**Assessment posture:** deliberately critical  
**Product category:** scientific research web application / evidence exploration UI

## Executive verdict

Knowledge Engine Web is a credible alpha application with unusually good trust-boundary discipline, a real deployed demo, deterministic retrieval benchmarking, Docker smoke testing, dependency auditing, and a clear separation between evidence display and AI narration.

It is **not yet a production research product**. The main gap is that the browser experience still reflects the architecture of an engineering alpha: point-in-time snapshots, optional local AI prerequisites, direct database/artifact consumption, incomplete progressive-research behavior, and a UX that is still proving the product flow rather than optimizing a complete researcher journey.

### Overall rating: **6.5 / 10**

This is above the level of a portfolio mockup and below the level of a polished, production web product. A professional reviewer would see real substance, but also immediately identify production UX, integration, observability, accessibility and end-to-end testing gaps.

## Scorecard

| Area | Score | Reality check |
|---|---:|---|
| Product concept / information architecture | 7.5 | Clear evidence-first direction and coherent trust model. |
| Backend/web architecture | 6.5 | Sensible read-only boundary, but direct Core schema/artifact consumption and duplicated retrieval behavior create coupling. |
| Retrieval UX foundation | 7.0 | Real Ask path and benchmarked ranking exist. General research continuation after a miss is not complete. |
| Visual/interaction UX maturity | 6.0 | Functional alpha, not yet a polished researcher workspace. |
| Accessibility | 4.5 | No automated accessibility/WCAG test evidence was found in the current repository search. |
| Browser end-to-end testing | 5.0 | Docker startup is tested, but no Playwright/Selenium-style browser workflow evidence was found. |
| CI / release hygiene | 8.0 | Ruff, mypy, pytest, pip-audit, Docker build and container smoke test are strong. |
| Security posture | 7.5 | Read-only architecture, password-gated alpha and secret scanning are solid for alpha. Production identity/access control is not yet demonstrated. |
| Observability / performance | 5.0 | Latency/bottleneck work is recognized but not yet productized. |
| Production readiness | 5.0 | Alpha-quality deployment, not a dependable public research service. |

## What is already professionally strong

### 1. The UI does not pretend generated prose is evidence

The strongest product decision is the explicit seam between deterministic evidence and optional AI narration. Claim detail pages, Evidence Intelligence, relationships and citations remain source-linked. This is exactly the right default for a scientific product.

### 2. Retrieval is benchmarked instead of hidden behind presentation

The repository has a deterministic retrieval benchmark spanning multiple domains and reports Recall@5 / reciprocal rank. That is far better than evaluating the experience by whether a few demo questions "look right."

### 3. CI includes a real container smoke test

The primary workflow does more than unit tests: it builds the Docker image and verifies the application starts and serves a request. That is a meaningful professional practice.

### 4. The alpha accurately labels its limitations

The README is explicit that the deployment is a snapshot, not a live Core connection, and that the project has not reached public-service maturity. This honesty matters.

## Where it falls below industry standard

### 1. The data/integration boundary is too fragile for a long-lived production web app

The Web repository reads Core's SQLite schema through reflection and separately reads Evidence/Relationship JSONL artifacts. It also ports retrieval behavior rather than consuming one stable service implementation.

That is workable while both repositories move quickly, but it creates several risks:

- behavior drift between Web and Core;
- schema-change surprises;
- duplicated ranking logic;
- deployment coupling to local file layouts;
- difficult horizontal scaling;
- complicated freshness semantics.

The eventual read-only Core service should become the web application's stable data plane. Web should consume versioned contracts, not database implementation details.

### 2. The primary researcher journey is incomplete

The expected industry UX is not "search a snapshot and maybe synthesize it." It is:

`ask -> immediate useful state -> retrieve -> broaden when necessary -> show progress -> partial grounded answer -> final evidence-backed answer`

Open issue #93 correctly identifies the missing behavior: an initial corpus miss must not terminate the product experience when bounded research is available.

Until this is implemented, the most important user promise is not satisfied.

### 3. Progressive long-running research UX needs to be designed as a first-class state machine

Research can take seconds to minutes. A production UI must show stable, resumable states rather than spinner-driven ambiguity.

Expected states should include:

- searching indexed evidence;
- broadening search;
- provider coverage/degradation;
- acquiring sources;
- validating/extracting evidence;
- re-retrieving;
- partial answer available;
- final answer;
- insufficient evidence after bounded research;
- failed/degraded but recoverable.

Each state should preserve the same durable research/session identity and survive refresh/reconnect where practical.

### 4. Browser-level UX testing is below what a production web application needs

The repository has solid Python and Docker tests, but no Playwright/Selenium-style browser workflow was found in the current search. A research application needs regression coverage for critical user journeys, not only server behavior.

At minimum automate:

- homepage/demo -> Ask;
- question submission;
- indexed hit;
- indexed miss -> research-required state;
- partial answer update;
- citation/source navigation;
- degraded provider state;
- authentication/session expiration;
- mobile/narrow viewport basics;
- refresh/resume behavior.

### 5. Accessibility needs explicit ownership

A scientific/research product should target WCAG 2.2 AA behavior for keyboard navigation, focus states, semantic headings, form labels, status announcements, contrast and non-color status communication.

No automated accessibility tooling was found in the current repository search. Add axe-based checks to browser tests and perform manual keyboard/screen-reader passes on the critical flows.

### 6. Alpha authentication is not production identity/security

A password gate is appropriate for a controlled demo. A public research service will eventually need a real decision on anonymous/public access versus authenticated accounts, rate limits, abuse prevention, session security, CSRF/cookie posture where applicable, audit logging, and administrative boundaries.

Do not overbuild this before the product flow is ready, but do not confuse alpha gating with production auth.

### 7. Observability is too weak for a long-running research UI

The Web layer should expose client-visible and operator-visible timing for:

- request intake;
- first rendered progress state;
- first grounded evidence;
- synthesis ready;
- final report;
- provider degradation;
- retries/timeouts;
- session resume/reuse.

Frontend and backend telemetry should share a research-session ID so a slow user experience can be traced end to end.

## User-experience standard to aim for

A first-time researcher should be able to answer these questions without reading documentation:

1. What am I searching?
2. Is this answer based on indexed evidence, newly researched evidence, or both?
3. Is the system still researching?
4. What sources support each factual statement?
5. What evidence is missing or contradictory?
6. Did any providers fail?
7. How current is this evidence snapshot/session?
8. Can I return to or refresh this research without restarting it?
9. What does a confidence/quality number actually mean?
10. What can I do next?

The current alpha solves some of these, but not the complete set.

## Highest-priority improvements

### P0 — Implement progressive research UX after an indexed miss

Issue #93 is the most important Web product item. The browser must stay useful while the broader research loop runs and must never present a local miss as a final global absence unless bounded research actually completed.

### P1 — Move toward one stable Core service contract

When the Core persistent-host trigger is satisfied, migrate retrieval/evidence reads behind versioned read-only APIs. Remove duplicated retrieval logic only after parity tests prove behavior.

### P1 — Add browser end-to-end tests

Use a real browser test suite for the researcher-critical paths. Include deterministic fixtures for hit, miss, degraded provider, partial result and final result states.

### P1 — Establish accessibility gates

Add automated axe checks and a documented manual WCAG 2.2 AA verification checklist for every major release.

### P1 — Add measurable UX performance targets

Track time to first UI response, first grounded information and final report. Long-running research should show stage duration and reason for waiting.

### P2 — Improve product polish only after state behavior is correct

Strengthen typography, hierarchy, source cards, citation interactions, responsive layout, empty/error states and onboarding, but do not let visual polish outrun research-state correctness.

### P2 — Add production security and abuse controls when public access approaches

Define authentication/public access, rate limits, session policy, headers/CSP, audit events and operational alerts as part of the production launch gate.

## What would move this above 8/10

- live, versioned integration with Core rather than snapshot/database coupling;
- progressive research state that survives long-running work and refreshes;
- browser end-to-end regression coverage;
- WCAG 2.2 AA accessibility evidence;
- production telemetry and user-visible latency/progress behavior;
- polished first-run onboarding and clear evidence provenance;
- production-grade auth/abuse posture appropriate to the launch model;
- validated multi-domain Ask behavior with partial/final grounded answers.

## Bottom line

Knowledge Engine Web is a **real alpha product**, not a static portfolio front end. That is significant. But its current maturity should be described as **functional research-lab UI**, not production researcher software.

The next major credibility gain is not another page. It is making the complete arbitrary-question research lifecycle understandable, resumable, testable and trustworthy from the browser.