# Browser end-to-end testing

Status: initial infrastructure, Ask critical path; now includes automated
accessibility checks.

`docs/INDUSTRY_REALITY_CHECK.md` identified "no Playwright/Selenium-style
browser workflow evidence was found" and "no automated accessibility tooling
was found" as P1 production gaps. `tests/test_browser_e2e.py` and
`tests/test_accessibility_e2e.py` are the first committed, reusable answers
to those gaps. Both import their real-server/real-Chromium fixtures from
`tests/_browser_e2e_support.py` -- extend that shared module, or add another
sibling test module that imports its fixtures, rather than re-deriving the
live-server/fixture-data setup.

## What it does

Each test starts the real `knowledge_engine_web` FastAPI application as a
real HTTP server (`uvicorn` in a subprocess) against a real SQLite fixture
database and a real Evidence Records JSONL file -- the same fixture shapes
`tests/_fixtures.py` and `tests/test_ask_question_contract.py` already use
for Python-level tests. It then drives that real server with a real headless
Chromium instance (Playwright's Python sync API). No mocked backend
authority: Research/AI capability is left genuinely unconfigured, so the
suite also exercises the honest, fail-closed "Broader Research is
unavailable on this deployment" path rather than a faked research result --
consistent with `docs/agent-development-policy.md` section 1's read-only,
fail-closed posture.

Covered so far:

- the homepage loads the real application;
- Ask renders a real, source-linked "Direct match" citation from indexed
  evidence, alongside the honest Research-unavailable notice;
- clicking a citation link navigates to the real `/claims/{evidence_record_id}`
  detail page and shows the real stored claim text;
- an unmatched question does not fabricate an answer (`No relevant papers
  found in the indexed corpus.`);
- the Ask page renders without horizontal overflow at a 390px mobile
  viewport;
- reloading the Ask page for the same indexed-only question reproduces the
  identical citation rather than losing or changing it (refresh/resume for
  the synchronous indexed path only -- durable async Research session
  resume across a refresh still needs real Research capability and is not
  exercised here);
- `tests/test_browser_e2e_auth.py` drives the real, unlisted-alpha HTTP
  Basic Auth gate (`AlphaBasicAuthMiddleware`) with a real Chromium network
  stack against a real server started with `KE_WEB_ALPHA_USERNAME`/
  `KE_WEB_ALPHA_PASSWORD` configured: a real browser refuses to render the
  gated page with no credentials or the wrong password, and loads it
  normally with the correct ones. `tests/test_alpha_auth.py` already covered
  this middleware at the `TestClient`/ASGI level; this closes the separate,
  previously-uncovered real-browser-authentication gap. A real Chromium
  network stack has been observed to reject the challenge two different
  ways depending on Chromium build/version -- either `page.goto` completes
  with a 401 response, or the navigation itself raises `net::
  ERR_INVALID_AUTH_CREDENTIALS`/`net::ERR_HTTP_RESPONSE_CODE_FAILURE` before
  any response exists -- so the assertion accepts either outcome as proof
  the app was never rendered, rather than hard-coding one exact error
  string.
- `tests/test_keyboard_navigation_e2e.py` drives real Tab/Shift+Tab/Enter
  keyboard input (not axe-core's static DOM analysis) against the homepage
  and Ask page: a "Skip to main content" link is the first tab stop and
  activating it moves focus into `<main>`; the Ask page's autofocused
  question field receives focus immediately on load; a focused form control
  has a visible focus indicator (outline or box-shadow). This run added the
  skip link itself (`knowledge_engine_web/templates/base.html`,
  `knowledge_engine_web/static/style.css`): previously a keyboard user had
  no way to bypass the header's eight nav links plus an "Inspect" dropdown
  before reaching page content on every single page load, a real WCAG 2.4.1
  (Bypass Blocks) gap. axe-core's static analysis does not check this (a
  missing skip link is not itself an axe rule violation), which is why the
  seven-page axe suite above reported zero violations while this gap still
  existed -- real keyboard-driven navigation testing found what static
  analysis could not.

This first pass already caught and fixed two real rendering bugs, not test
artifacts: `.snapshot-line` (the footer's snapshot metadata line, which can
contain a long comma/underscore-separated `corpus_id` with no wrap
opportunity) and `.inspect-menu > div` (the header's "Inspect" dropdown,
whose closed-state hiding relied only on native `<details>` semantics and
could still occupy real off-canvas layout geometry in at least one real
browser engine). Both now wrap/hide explicitly rather than relying on
implicit browser behavior. See `knowledge_engine_web/static/style.css`.

Not yet covered: `docs/INDUSTRY_REALITY_CHECK.md`'s remaining critical-path
scenarios that require real, durable async Research capability to exercise
honestly -- indexed miss -> research-required state, partial-answer updates,
degraded-provider state, and durable Research-session refresh/resume. This
repository will not fake that backend authority merely to gain browser
coverage (see `docs/agent-development-policy.md` section 1). Real-browser
authentication and indexed-path refresh/resume are now covered (above).
Extend this module -- or add sibling modules following the same pattern --
rather than re-deriving the live-server/fixture-data approach.

## Accessibility (axe-core)

`tests/test_accessibility_e2e.py` runs [axe-core](https://github.com/dequelabs/axe-core)
(via `axe-playwright-python`, which vendors `axe.min.js` -- no network access
needed at test time) against seven real, real-Chromium-rendered pages: the
homepage; the Ask page in both its indexed-hit and no-match states; the claim
detail page; the graph summary page (`/graph`); the Evidence Intelligence
dashboard (`/dashboard`); and the claims list (`/claims`). Each test fails on
any "critical", "serious", "moderate", or "minor" impact violation axe-core
reports -- every impact level axe-core distinguishes is now enforced, not
just critical/serious.

As of the run that widened this suite, all seven real pages had **zero**
axe-core violations at any impact level -- a genuine, verified result, not an
assumed pass. This closes real automated-accessibility-evidence gap
`docs/INDUSTRY_REALITY_CHECK.md` identified, but it is still only what
axe-core's automated ruleset can catch (roughly 30-50% of WCAG 2.2 AA success
criteria industry-wide). It does not replace a manual keyboard-navigation/
screen-reader pass, and still does not cover the async-Research progress/
report views or the mobile Product Reality review panel -- both require real
Research capability to exercise honestly, same as the browser-E2E gap noted
above, which this repository will not fake in a test fixture merely to gain
coverage.

## Running it

```
poetry run pytest tests/test_browser_e2e.py -v
```

Chromium is optional at test time: if no usable executable is found, every
test in the module skips (not fails) with a message explaining how to
provide one. Locally, either run `poetry run playwright install chromium`
once, or point `KE_WEB_TEST_CHROMIUM_PATH` at an existing Chromium binary.

## CI

`.github/workflows/browser-e2e.yml` installs Playwright's Chromium and runs
this module for real on every PR and push to `main`. It is deliberately
**not** part of the required `Quality`/`Docker build` checks yet (see
`docs/agent-development-policy.md` section 3 and
`docs/project-status.yaml`'s `automation_contract.required_pr_workflows`):
this is new infrastructure with a heavier, slower job than the rest of the
Quality gate, so it runs and reports on every PR without blocking merge
until it has proven itself stable. Promote it to required once it has run
green across several PRs.
