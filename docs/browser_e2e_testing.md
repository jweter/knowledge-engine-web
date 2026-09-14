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
  keyboard input (not axe-core's static DOM analysis) against the homepage,
  Ask page, and (this run) `/discover`: a "Skip to main content" link is the
  first tab stop and activating it moves focus into `<main>`; the Ask and
  Discover pages' autofocused query fields receive focus immediately on
  load; a focused form control has a visible focus indicator (outline or
  box-shadow); Discover's real submit button is the next tab stop after its
  query input, with the unavailable-capability notice's plain text correctly
  not intercepting focus. A prior run added the skip link itself
  (`knowledge_engine_web/templates/base.html`,
  `knowledge_engine_web/static/style.css`): previously a keyboard user had
  no way to bypass the header's eight nav links plus an "Inspect" dropdown
  before reaching page content on every single page load, a real WCAG 2.4.1
  (Bypass Blocks) gap. axe-core's static analysis does not check this (a
  missing skip link is not itself an axe rule violation), which is why the
  axe suite below reported zero violations while this gap still
  existed -- real keyboard-driven navigation testing found what static
  analysis could not.
- (this run) `test_motion_toggle_is_keyboard_operable_and_stops_animation`
  and `test_motion_toggle_preference_persists_across_reload` drive the new
  site-wide `#motion-toggle` header control
  (`knowledge_engine_web/static/knowledge_constellation.js`,
  `knowledge_engine_web/static/knowledge_constellation.css`,
  `knowledge_engine_web/templates/base.html`): WCAG 2.2.2 (Pause, Stop,
  Hide) requires that indefinite decorative motion -- the constellation
  canvas background and the homepage headline's `ke-title-aurora` animation,
  which ran continuously on every page with no way to stop them except an
  OS-level `prefers-reduced-motion` setting -- have an operable pause/stop
  mechanism independent of that OS setting. The tests confirm the control is
  reachable and activatable by keyboard alone (`Tab` then `Enter`), that
  activating it actually halts the animation (asserted via the real computed
  `animationDuration`, not just a CSS class being present), that a second
  activation resumes it, and that the preference persists (`localStorage`)
  across a reload and across navigation to a different real page. This is a
  real, previously-missing accessibility control this run added and
  verified -- not a stand-in for the manual pass `docs/
  manual_accessibility_checklist.md` row 7a still calls for (that row also
  requires confirming real screen-reader operability, which this scripted
  Tab/Enter sequence does not establish).

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
needed at test time) against seventeen real, real-Chromium-rendered
pages/states: the homepage; the Ask page in both its indexed-hit and no-match
states; the claim detail page; the graph summary page (`/graph`); the
Evidence Intelligence dashboard (`/dashboard`); the claims list (`/claims`);
`/discover` in both its empty-form and unavailable-capability-error states --
federated discovery is a separate capability gate from Ask's Research
capability (see `docs/agent-development-policy.md` section 1), but the
fixture server leaves both equally unconfigured, so this real form and its
fail-closed error state are reachable the same honest way Ask's no-match
state already was; and (this run) the remaining static/reference pages that
need no Research capability either: About (`/about`), Roadmap (`/roadmap`,
including its embedded, banner-labeled concept-preview iframe), the Demo page
in its honest "record unavailable" empty state (`/demo` -- the fixture data
does not include the stable SELECT-trial demo record), the Reports index
(`/reports`) and one rendered report view (`/reports/graph`), Unconfirmed
Claims (`/unconfirmed-claims`), Relationship Candidates
(`/relationship-candidates`), and one paper detail page (`/papers/1`). Each
test fails on any "critical", "serious", "moderate", or "minor" impact
violation axe-core reports -- every impact level axe-core distinguishes is
enforced, not just critical/serious.

As of this run, all seventeen real pages/states had **zero** axe-core
violations at any impact level -- a genuine, verified result, not an assumed
pass. This closes real automated-accessibility-evidence gap
`docs/INDUSTRY_REALITY_CHECK.md` identified, and now covers every page
reachable without Research/AI capability. It is still only what axe-core's
automated ruleset can catch (roughly 30-50% of WCAG 2.2 AA success criteria
industry-wide). It does not replace a manual keyboard-navigation/
screen-reader pass, and still does not cover the async-Research progress/
report views or the mobile Product Reality review panel -- both require real
Research capability to exercise honestly, same as the browser-E2E gap noted
above, which this repository will not fake in a test fixture merely to gain
coverage.

`docs/manual_accessibility_checklist.md` is the reusable checklist and
results log for the remaining manual keyboard-navigation/screen-reader pass
this section calls out. As of this run it contains checklist structure only
-- no manual pass has been recorded against it yet -- so it does not itself
close the gap; it gives the next real pass (human, or a future agent with
real assistive-technology access) a concrete, WCAG-2.2-AA-criterion-level
list scoped to what axe-core and the scripted keyboard tests above do not
already establish, plus a place to record dated PASS/FAIL/NOT YET TESTABLE
results per criterion against an exact build identity.

## Reflow and focus-visible (`tests/test_reflow_and_focus_indicators_e2e.py`)

`docs/manual_accessibility_checklist.md` rows 4 (1.4.10 Reflow) and 10
(2.4.7 Focus Visible) previously listed both criteria as needing a full
human pass. Part of each is a plain, objective measurement rather than a
judgment call, so this module automates that part:

- **Reflow**: at a 320px CSS viewport width (the standard proxy for a
  1280px layout zoomed to 400%), every page/state
  `tests/test_accessibility_e2e.py` covers -- homepage, both Ask states,
  claim detail, graph summary, the Evidence Intelligence dashboard, claims
  list, both Discover states, About, Roadmap, the Roadmap concept preview,
  Demo, Reports index/view, Unconfirmed Claims, Relationship Candidates,
  and paper detail -- must not overflow horizontally
  (`document.documentElement.scrollWidth` must not exceed `clientWidth`).
- **Focus visible**: on that same full page/state set, every visible
  native/ARIA-focusable element -- not only the first text input the
  keyboard-navigation suite already checks -- must show some computed-style
  change (outline, box-shadow, border, background, or text-decoration) when
  focused.

This run's first pass at the reflow check found a real WCAG 1.4.10
violation, not a test artifact: the generic `code` selector in
`knowledge_engine_web/static/style.css` had no `overflow-wrap`, so a long
unbroken token inside a `<code>` element (claim detail's
`docs/evidence_intelligence_design.md` reference) pushed the claim detail
page 13px wider than a 320px viewport. Fixed with `overflow-wrap: anywhere`
on the `code` rule, the same technique already used for `.snapshot-line`
(see above).

Extending the reflow check to the remaining `test_accessibility_e2e.py`
pages found a second real violation: the Roadmap concept preview's standalone
document (`knowledge_engine_web/static/concept-preview.html`) has a
`.topbar` flex row containing a `white-space: nowrap` wordmark, a
`max-width`-only search bar, and an "Ask" button. Flex children default to
`min-width: auto`, so their combined nowrap content width (well over 600px)
never shrank below that regardless of viewport width, overflowing a 320px
viewport by 671px. Fixed with a `@media (max-width: 480px)` rule that wraps
the topbar (`flex-wrap: wrap`), lets the wordmark text wrap instead of
forcing nowrap, and gives the search bar `min-width: 0` plus its own
wrapped row so it can actually shrink.

This does not close manual checklist rows 4 and 10 -- it narrows what still
needs a human to the genuinely subjective remainder: whether reflowed
content still *reads* sensibly (not just "does it overflow"), and whether a
focus indicator's *contrast* is actually perceivable (not just "does
something change").

## Reduced motion (`tests/test_reduced_motion_e2e.py`)

`docs/manual_accessibility_checklist.md` row 7 (2.3.3 Animation from
Interactions) asked whether the constellation/neural-web decorative motion
(`knowledge_engine_web/static/knowledge_constellation.js`) actually respects
the OS-level `prefers-reduced-motion: reduce` setting. The only prior
evidence for this was
`tests/test_knowledge_constellation_face.py::test_constellation_motion_is_accessibility_safe`,
which merely asserts that the right strings (`matchMedia(...)`, the CSS media
query) exist in the source files -- it cannot catch a logic bug that leaves
the canvas animating anyway, and the canvas motion is driven entirely by a
`requestAnimationFrame` loop in JavaScript, so axe-core and CSS-only checks
cannot see it either.

This module instead uses Playwright's `page.emulate_media(reduced_motion=...)`
against the real running app and compares the canvas's actual rendered pixel
output (`canvas.toDataURL()`) before and after a wait:

- under `reduce`, the canvas image is byte-identical before and after the
  wait (the animation loop never restarts itself) and the headline aurora
  animation's computed `animationDuration` collapses to the same
  effectively-zero value the existing `#motion-toggle` test already checks;
- under the default `no-preference` setting, the canvas image visibly
  changes over the same wait -- a control case proving the comparison
  technique is actually sensitive to real motion, so the reduced-motion
  assertion is not vacuously true;
- the same static-canvas check is repeated on a second, non-homepage page
  (`/about`) since the constellation layer runs site-wide via `base.html`'s
  body class, not only on the homepage.

(Note: this module deliberately does not use `page.add_init_script()` to
instrument `requestAnimationFrame` calls directly -- that approach was tried
first, but `add_init_script` was found to be a no-op against the Chromium
build available in this environment, silently leaving `window` unmodified
before navigation. The pixel-comparison approach above does not depend on it
and was verified stable across repeated runs.)

This closes the automatable half of checklist row 7: whether a screen reader
announces anything about the motion remains a human judgment call, as does
any future interaction-triggered animation this repository adds.

## Focus order (`tests/test_focus_order_e2e.py`)

`docs/manual_accessibility_checklist.md` row 8 (2.4.3 Focus Order) previously
listed the whole criterion as needing a full human pass. Whether a full-page
Tab traversal *reads* sensibly is a judgment call, but whether the browser's
actual Tab order matches the page's document order -- the precondition every
other focus-order judgment depends on -- is a plain, scriptable fact. This
module checks, on every page/state `tests/test_accessibility_e2e.py` covers:

- no element has a positive `tabindex` (which overrides natural document
  order, a common real-world 2.4.3 anti-pattern);
- a real, full-page Tab-key traversal (not just the first few stops
  `tests/test_keyboard_navigation_e2e.py` already checks) visits every
  visible focusable element in exactly the same sequence
  `document.querySelectorAll` returns for the page.

No behavioral bug was found in this repository's pages -- every page's Tab
order already matches its document order. Building this test did surface a
real methodology problem worth recording: the first implementation reset
focus to the top of the page with `document.activeElement.blur()` before
tabbing. That works for most pages, but per the HTML spec, `blur()` clears
`document.activeElement` without resetting the browser's *sequential focus
navigation starting point* -- so on a page that autofocuses an element on
load (Ask, Discover), a subsequent Tab silently resumed from that
autofocused element instead of the top of the page, only exercising the tail
of the order and failing with a misleading "order mismatch" for elements
that were never actually reachable in the test's traversal. The fix is to
explicitly `.focus()` the first tagged element directly rather than relying
on `blur()`, which deterministically starts the walk at position 0 regardless
of what the page autofocuses. The Roadmap page's embedded concept-preview
`<iframe>` posed a related wrinkle: Chrome reports the outer `<iframe>`
element as `document.activeElement` for every tab stop *inside* it, so the
traversal detects that case and keeps tabbing (without asserting on internal
order, which the standalone `/static/concept-preview.html` page already
covers in its own right) until focus re-emerges into the top-level document.

This closes the automatable half of checklist row 8: whether the resulting
order is a *sensible* reading/interaction order for a real user remains a
human judgment call.

## Target size (`tests/test_target_size_e2e.py`)

`docs/manual_accessibility_checklist.md` row 11 (2.5.8 Target Size Minimum)
previously listed the whole criterion as needing a human pass. WCAG's
24x24 CSS px minimum has several exceptions that genuinely need contextual
judgment (Equivalent, Essential, Spacing between undersized targets), but
one -- "Inline," a plain link inside a sentence or block of text whose size
is dictated by the surrounding text's line-height rather than deliberate
touch-target sizing -- is mechanically detectable: such a link's computed
`display` is `inline` (the browser default for an unstyled `<a>`), while
every button-styled or nav-styled control in this codebase is deliberately
given a block/inline-block/flex display. This module checks, on every
page/state `tests/test_accessibility_e2e.py` covers: every visible,
non-inline pointer target (buttons, nav/footer links, form controls --
excluding checkbox/radio inputs, which the "User agent control" exception
covers for an unrestyled native control) is at least 24x24 CSS px.

No real violation was found -- every button/nav/footer control in this
codebase already meets the minimum size, and the elements initially
flagged as undersized before the `display: inline` exclusion was added
were confirmed (by inspecting their computed style directly) to be exactly
the plain in-sentence links the "Inline" exception describes, not a real
gap. This closes the automatable half of checklist row 11: the "Equivalent,"
"Essential," and "Spacing" exceptions, and 2.5.7 Dragging Movements (this
codebase has no drag-style interaction today, but that has not been
verified against every future addition), remain human judgment calls.

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
