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
| Accessibility | 5.5 | `tests/test_accessibility_e2e.py` now runs real axe-core checks against seventeen real pages/states -- the homepage, both Ask states, the claim detail page, the graph summary, the Evidence Intelligence dashboard, the claims list, `/discover` in its empty-form and unavailable-capability states, and (this run) every remaining page reachable without Research capability: About, Roadmap (including its embedded concept-preview iframe), the Demo page's honest empty state, the Reports index and a rendered report view, Unconfirmed Claims, Relationship Candidates, and a paper detail page -- enforced on every impact level axe-core reports (critical/serious/moderate/minor, not just critical/serious), wired into the same advisory `browser-e2e.yml` CI job. All seventeen pages/states verified at zero violations at any impact level. `tests/test_keyboard_navigation_e2e.py` adds real Tab/Shift+Tab/Enter keyboard-driven evidence axe-core's static DOM analysis cannot provide, now covering the homepage, Ask, and `/discover`'s query form and submit button; a prior run found and fixed a real WCAG 2.4.1 (Bypass Blocks) gap this way -- no skip-to-main-content link existed, so every page load required tabbing through eight header nav links plus an "Inspect" dropdown before reaching content. That link now exists and is verified as the first tab stop. `tests/test_reflow_and_focus_indicators_e2e.py` automates the objective part of two more manual-checklist rows across all seventeen `test_accessibility_e2e.py` pages/states (extended from five/two this run): no horizontal overflow at a 320px CSS width (1.4.10 Reflow), and every visible focusable element showing some focus-state style change (2.4.7 Focus Visible), not only the first input already checked. The reflow check has now found and fixed two real violations: a `<code>` element without `overflow-wrap` pushed the claim detail page 13px past a 320px viewport on a long unbroken file-path token, and (this run) the Roadmap concept preview's topbar overflowed 671px because its flex children (a nowrap wordmark, a max-width-only search bar, an Ask button) had no way to shrink below their combined content width -- fixed with a narrow-viewport media query that wraps the row and lets the search bar shrink. `tests/test_reduced_motion_e2e.py` closes the objective half of row 7 (2.3.3 Animation from Interactions): the only prior evidence was a static string-search test that could not catch a real logic bug, since the constellation canvas's motion is driven entirely by a JavaScript `requestAnimationFrame` loop invisible to axe-core and CSS-only checks. That test emulates `prefers-reduced-motion: reduce` in a real Chromium instance and confirms the canvas's rendered pixel output stays identical over time (with a control case proving the same comparison detects real motion under the default setting), on both the homepage and a second site-wide page. `tests/test_focus_order_e2e.py` (this run) closes the objective half of row 8 (2.4.3 Focus Order): no page has a positive `tabindex` overriding natural document order, and a real full-page Tab traversal visits every visible focusable element in exactly its document order, on every page/state `test_accessibility_e2e.py` covers (correctly handling the Roadmap concept-preview iframe boundary rather than misreading it as a broken order). No behavioral bug was found -- every page's Tab order already matched its document order -- but building the check did find and fix a real test-methodology flaw: resetting focus via `document.activeElement.blur()` does not reset the browser's sequential focus navigation starting point, so on autofocusing pages (Ask, Discover) it silently tested only the tail of the order; the fix explicitly focuses the first element instead. This is real automated evidence, not an assumed pass -- but axe-core's automated ruleset only catches roughly 30-50% of WCAG 2.2 AA success criteria industry-wide, a full manual keyboard/screen-reader pass has still not been performed (the reflow/focus-visible/reduced-motion/focus-order checks establish the objective "does it overflow / does something change / does it actually stop / does it match document order" half of their criteria, not the subjective "does it read sensibly / is it perceivable / is it announced" half), and the async-Research progress/report views and the mobile review panel remain unchecked (both require real Research capability to exercise honestly). Do not treat this as WCAG 2.2 AA conformance evidence. |
| Browser end-to-end testing | 6.0 | `tests/test_browser_e2e.py` (added 2026-09-11) drives the real app with real headless Chromium for the Ask critical path -- homepage load, indexed direct match, citation navigation, no-fabrication miss state, mobile viewport, and (added same day) indexed-path refresh/resume. `tests/test_browser_e2e_auth.py` (added same day) closes real-browser authentication coverage: a real Chromium network stack refuses to render the alpha-gated page with no or wrong credentials and loads it normally with correct ones, complementing the existing `TestClient`-level `tests/test_alpha_auth.py`. Both are wired into `.github/workflows/browser-e2e.yml` on every PR. This pass already caught and fixed two real rendering bugs (see `docs/browser_e2e_testing.md`). Still narrow: research-required/partial-answer/degraded-provider states and durable async-Research-session resume remain unaddressed because exercising them honestly requires real Research capability, which this repository will not fake for coverage; `tests/test_accessibility_e2e.py` and `tests/test_keyboard_navigation_e2e.py` now extend Playwright coverage to `/discover` as well as Ask (see the Accessibility row above), and the CI job is advisory, not yet a required check. |
| CI / release hygiene | 8.0 | Ruff, mypy, pytest, pip-audit, Docker build and container smoke test are strong. |
| Security posture | 7.5 | Read-only architecture, password-gated alpha and secret scanning are solid for alpha. Production identity/access control is not yet demonstrated. |
| Observability / performance | 5.5 | `RequestObservabilityMiddleware` (`knowledge_engine_web/observability.py`, added 2026-09-14) now logs method/path/status/duration and stamps every response with an `X-Request-ID`/`X-Response-Time-Ms` pair, independent of Research/AI capability -- previously a plain indexed Ask, Discover, or any other route got zero timing or correlation ID at all, since the only existing latency/funnel reporting (BT-2/BT-6 in `research_jobs.py`/`ask.html`) is gated entirely on an active Research session. Still missing: aggregated first-grounded-evidence/synthesis-ready/provider-degradation timing outside the Research path, and joining this generic request ID with a Research session's own `research_session_id` when both exist on the same request. |
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

`tests/test_accessibility_e2e.py` now runs real axe-core checks against seventeen real pages/states -- the homepage, both Ask states, the claim detail page, the graph summary, the Evidence Intelligence dashboard, the claims list, `/discover`'s empty-form and unavailable-capability states, and every remaining page reachable without Research capability (About, Roadmap, Demo's empty state, the Reports index and a report view, Unconfirmed Claims, Relationship Candidates, and a paper detail page) -- on every PR, enforced on every impact level (critical/serious/moderate/minor), and all seventeen currently pass with zero violations at any impact level: this is now every page reachable without Research/AI capability configured. `tests/test_keyboard_navigation_e2e.py` adds real keyboard-driven (Tab/Shift+Tab/Enter) evidence beyond axe-core's static analysis across the homepage, Ask, and `/discover`, and previously found/fixed a real skip-link gap (see scorecard above). That is real, verified automated evidence where none existed before -- but it is still not WCAG 2.2 AA conformance evidence: axe-core's automated ruleset only catches roughly 30-50% of success criteria industry-wide, a full manual keyboard-navigation/screen-reader pass covering every interactive component has still not been performed, and the async-Research progress/report views and mobile review panel remain unchecked because exercising them honestly requires real Research capability. Perform an actual manual keyboard/screen-reader pass, and extend axe and keyboard coverage to those two remaining surfaces once Research capability is verifiable, before calling this gap fully closed.

### 6. Alpha authentication is not production identity/security

A password gate is appropriate for a controlled demo. A public research service will eventually need a real decision on anonymous/public access versus authenticated accounts, rate limits, abuse prevention, session security, CSRF/cookie posture where applicable, audit logging, and administrative boundaries.

Do not overbuild this before the product flow is ready, but do not confuse alpha gating with production auth.

### 7. Observability is too weak for a long-running research UI

The Web layer should expose client-visible and operator-visible timing for:

- request intake (now closed generically -- see below);
- first rendered progress state;
- first grounded evidence;
- synthesis ready;
- final report;
- provider degradation;
- retries/timeouts;
- session resume/reuse.

`RequestObservabilityMiddleware` (added 2026-09-14) closes the "request
intake" item for every request, not only Research ones: a correlation ID
(`X-Request-ID`, reusing one the caller supplied or minting a fresh one)
and a duration (`X-Response-Time-Ms` plus a server log line with
method/path/status/duration) now exist independent of Research/AI
capability. `research_jobs.py` (updated 2026-09-15) now carries that same
correlation ID into an async Research job: the `/ask` route that starts a
job passes its own `request.state.request_id` through to
`submit_research_job`, which persists it on `web_research_jobs.request_id`
and logs it (via `RequestObservabilityMiddleware`'s own logger/stream) on
job creation and again on the job's terminal outcome
(`completed`/`failed`) -- so an operator can now trace "which inbound
request started this Research session, and how did it end" from the
generic request log alone. The remaining items -- first grounded evidence,
synthesis ready, provider degradation, retries/timeouts, session
resume/reuse, and every intermediate progress poll in between creation and
the terminal outcome -- stay Research-path-specific and already have
partial coverage via BT-2/BT-6 (`research_jobs.py`, rendered in
`ask.html`) once a Research session exists, but are not yet themselves
logged with the correlated request ID; only the two durable milestones
(job start, job end) are joined so far.

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

Automated axe checks now exist for seventeen real pages/states (`tests/test_accessibility_e2e.py`) -- every page reachable without Research/AI capability -- enforced on every axe-core impact level (critical/serious/moderate/minor), currently all zero-violation. `docs/manual_accessibility_checklist.md` is the documented manual WCAG 2.2 AA verification checklist this item called for -- a reusable, criterion-level list scoped to what automated coverage cannot establish (screen reader announcement quality, reflow/zoom, focus order across a full page traversal, status-message live regions, and more), plus a place to record dated results against an exact build identity. It is checklist infrastructure only: no manual pass has been recorded against it yet, so this remains open until at least one full pass is recorded with no open FAIL rows. A prior run closed one real, concrete gap that checklist surfaced: a site-wide "Pause background motion" control (`#motion-toggle`) now lets a visitor stop the constellation canvas and headline aurora animation, which previously ran indefinitely on every page with no way to disable them short of an OS-level `prefers-reduced-motion` setting -- a genuine WCAG 2.2.2 (Pause, Stop, Hide) violation, not a documentation gap. `tests/test_keyboard_navigation_e2e.py` verifies it is keyboard-operable and actually halts the animation (real computed-style assertion, not a class-presence check) and that the preference persists. A prior run narrowed two more checklist rows (4 and 10) by automating their objective half in `tests/test_reflow_and_focus_indicators_e2e.py` -- no horizontal overflow at 320px CSS width, and a visible focus-state style change on every focusable element -- initially on five/two pages. A prior run extended both checks to every page/state `tests/test_accessibility_e2e.py` covers (seventeen total) and found a second real 1.4.10 Reflow violation: the Roadmap concept preview's topbar overflowed 671px at 320px width because its flex children (nowrap wordmark, max-width-only search bar, Ask button) had no way to shrink below their combined nowrap content width; fixed with a narrow-viewport media query that wraps the row. A prior run narrowed a fourth checklist row (7, 2.3.3 Animation from Interactions) the same way: `tests/test_reduced_motion_e2e.py` replaces a static string-search test (which could not have caught a real logic bug) with a real Chromium check that emulates `prefers-reduced-motion: reduce` and confirms the constellation canvas's `requestAnimationFrame`-driven motion actually stops, on both the homepage and a second site-wide page, with a control case proving the technique detects real motion when the preference is not set. This run narrowed a fifth checklist row (8, 2.4.3 Focus Order) the same way: `tests/test_focus_order_e2e.py` verifies no page has a positive `tabindex` overriding natural document order and that a real full-page Tab traversal matches document order on every page/state `test_accessibility_e2e.py` covers, correctly handling the Roadmap concept-preview iframe boundary. No behavioral bug was found, but the work found and fixed a real flaw in the test's own methodology: resetting focus via `blur()` does not reset the browser's sequential focus navigation starting point, so on autofocusing pages (Ask, Discover) it initially tested only the tail of the order (see the Accessibility scorecard row above and `docs/browser_e2e_testing.md`). Still remaining: extend automated coverage to the async-Research progress/report views and mobile review panel once Research capability is verifiable, and the manual/screen-reader pass itself.

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