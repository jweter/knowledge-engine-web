# Manual WCAG 2.2 AA verification checklist

Status: checklist infrastructure only. No manual pass has been recorded
against it yet -- do not read this document's existence as accessibility
conformance evidence. `docs/INDUSTRY_REALITY_CHECK.md` and
`docs/browser_e2e_testing.md` both call out that axe-core's automated
ruleset (`tests/test_accessibility_e2e.py`) and the real-keyboard regression
tests (`tests/test_keyboard_navigation_e2e.py`) together catch roughly
30-50% of WCAG 2.2 AA success criteria industry-wide, and that "a full
manual keyboard-navigation/screen-reader pass has still not been performed"
was the remaining P1 gap. This document is the reusable checklist that pass
should follow, and the place its results get recorded, so the gap has a
concrete next step instead of a standing narrative note.

## Why this exists instead of more automated tests

Some WCAG 2.2 AA success criteria are structurally unsuited to static DOM
analysis or scripted Tab-key sequences:

- whether a screen reader (VoiceOver, NVDA, JAWS) announces content the way
  a sighted user perceives it, including live-region updates;
- whether the *meaning* of focus order matches reading order, not just that
  focus moves somewhere reachable;
- whether reflow/zoom to 400% keeps content usable without two-dimensional
  scrolling;
- whether motion/animation can genuinely be disabled and gesture-driven
  interactions have a pointer/keyboard alternative;
- subjective clarity of error messages, instructions, and status
  communication.

These need a human operating real assistive technology. Do not attempt to
fake this with another axe-core run or another scripted Tab sequence --
that would misrepresent automated coverage as manual verification, which
`docs/agent-development-policy.md` section 6 (truthfulness) and this
repository's fail-closed posture both forbid.

## Scope

Cover every page/state `tests/test_accessibility_e2e.py` already covers
(see `docs/browser_e2e_testing.md` for the current list), plus, once real
Research capability is verifiable per `docs/project-status.yaml`'s
`product_decisions` and `mobile_product_reality_track`: the async-Research
progress/report views (Layer 1 and Layer 2 of Research Report v1) and the
mobile Product Reality review panel. Do not run the Research-dependent
rows against a faked or partially-configured backend; record them as
`NOT YET TESTABLE` with the reason until real capability exists.

## How to record a pass

1. Copy the results table below into a new dated entry under "Recorded
   passes."
2. Fill in: build/commit identity (`web_build_identity()`'s reported value
   -- the same identity Mobile Product Reality verdicts use), tester,
   assistive technology + browser + OS versions, and date.
3. For every criterion, record `PASS`, `FAIL` (with the concrete page and
   defect), or `NOT YET TESTABLE` (with why, e.g. "requires Research
   capability").
4. File a real issue for every `FAIL` before closing the pass out as done;
   do not silently note a defect and move on.
5. Update `docs/INDUSTRY_REALITY_CHECK.md`'s Accessibility row and
   `docs/project-status.yaml` to reference the pass once at least one full
   recorded pass exists with no open `FAIL` rows, per
   `docs/agent-development-policy.md` section 4's "update the design doc in
   the same PR" rule.

## Checklist (WCAG 2.2 AA, criteria automated coverage does not establish)

| # | WCAG 2.2 criterion | What to check | Pages/states |
|---|---|---|---|
| 1 | 1.3.1 Info and Relationships | Screen reader announces headings, lists, and table structure in a way that matches visual meaning, not just DOM validity | All covered pages |
| 2 | 1.3.2 Meaningful Sequence | Reading order announced by screen reader matches visual reading order, including after dynamic content loads (Ask's progressive states) | Homepage, Ask, Discover |
| 3 | 1.4.1 Use of Color | `tests/test_use_of_color_status_text_alternative.py` automates the objective part: source inspection of `knowledge_engine_web/static/style.css` confirms `discovery-status`/`publication-status-banner`/`trust-warning` are the only selectors that set color from the `--status-*` custom properties, the shared `PROVIDER_OUTCOME_LABELS`/`PROVIDER_STATUS_CSS_CLASSES` mapping (`discovery_presentation.py`) is checked directly for non-empty, pairwise-distinct label text across every provider outcome, and real rendered HTML for every conditionally-rendered banner this repository has today (retraction/correction/expression-of-concern/withdrawal/preprint/provider-metadata-disagreement on `/discover`, and Ask's partial-answer/provider-degraded/blocked/verification-findings/withheld-narrative trust warnings) confirms each color-classed element's own text is non-empty and, where two states share a css class, that their text still differs. Ask's certainty/conclusion rows and the mobile Product Reality review panel's PASS/FAIL/FLAG remain Research-only debt (see row 11) -- exercising them honestly requires real Research capability this repository cannot fake. What remains manual: whether the non-color cue is perceptually adequate (contrast/size) to a colorblind or low-vision visitor, and re-verifying this conclusion for any future status indicator this repository adds | `/discover` publication-status banners and provider badges, Ask's research-coverage/trust-warning banners (both Research-independent); Ask conclusion rows and the mobile review panel remain Research-only debt |
| 4 | 1.4.4 Resize Text / 1.4.10 Reflow | `tests/test_reflow_and_focus_indicators_e2e.py` automates the objective part -- no horizontal overflow at a 320px CSS width -- for every page/state `tests/test_accessibility_e2e.py` covers (17 pages/states), and found/fixed two real violations: a `<code>` element without `overflow-wrap` on claim detail, and the Roadmap concept preview's topbar overflowing 671px because its flex children could not shrink below their nowrap content width (see `docs/browser_e2e_testing.md`). What remains manual: whether reflowed content still reads in a sensible order/hierarchy, and 400% browser-zoom behavior specifically (only the equivalent 320px-viewport proxy is automated) | All 17 pages/states `test_accessibility_e2e.py` covers |
| 5 | 1.4.13 Content on Hover or Focus | `tests/test_hover_focus_disclosure_e2e.py` automates the objective part for the header "Inspect" menu: it is a native `<details>/<summary>` disclosure with no `:hover` CSS rule and no hover/focus JavaScript listener anywhere in this codebase, confirmed by a real Chromium check that hovering or focusing its `<summary>` alone never opens it, and that it remains click- and keyboard-operable (Enter toggles it open/closed) on both the homepage and a second page. Because it never appears merely from hover or focus, 1.4.13 does not currently apply to it. What remains manual: re-checking this conclusion if any future hover- or focus-triggered content (tooltips, previews) is added, since that content genuinely would need dismissible/hoverable/persistent verification | Header "Inspect" dropdown |
| 6 | 2.1.4 Character Key Shortcuts | `tests/test_character_key_shortcuts_e2e.py` automates the objective part: source inspection confirms no `keydown`/`keypress`/`keyup` listener exists anywhere in this repository's templates or static JavaScript, and a real Chromium check proves it behaviorally on every page/state `tests/test_accessibility_e2e.py` covers (18 pages/states) -- pressing a representative sample of bare single-character keys (letters commonly used as site shortcuts, `/`, `?`, digits) with focus on the neutral document body never navigates the page or moves focus. Because no bare-character shortcut exists at all, 2.1.4's turn-off/remap/focus-scoped requirement is currently satisfied trivially. What remains manual: re-verifying this conclusion whenever a future change adds an interaction-triggered keyboard handler, since that handler would need its own turn-off/remap/focus-scoped check | All 18 pages/states `test_accessibility_e2e.py` covers |
| 7 | 2.3.3 Animation from Interactions | `tests/test_reduced_motion_e2e.py` automates the objective part: with `prefers-reduced-motion: reduce` emulated in a real Chromium instance, the constellation canvas's rendered pixel output stays identical over time (the `requestAnimationFrame` loop never runs) and the headline aurora animation's computed duration collapses to effectively zero, on both the homepage and a second site-wide page (`/about`); a control case confirms the same comparison detects real motion under the default setting. What remains manual: whether a screen reader announces anything about the motion, and judgment for any other interaction-triggered animation this repository adds in the future | Homepage, all pages (site-wide constellation layer) |
| 7a | 2.2.2 Pause, Stop, Hide | A site-wide "Pause background motion" control (`#motion-toggle`, added this run) now stops the constellation canvas and the homepage headline's aurora animation without requiring `prefers-reduced-motion`; `tests/test_keyboard_navigation_e2e.py` verifies it is keyboard-operable (Tab + Enter) and actually halts the animation, and that the preference persists across reload/navigation. What automated coverage does not establish: whether a screen reader announces the control's role/state (`aria-pressed`) clearly, and whether its label makes its purpose obvious without visual context | Every page (site-wide header control) |
| 8 | 2.4.3 Focus Order | `tests/test_focus_order_e2e.py` automates the objective part: no element has a positive `tabindex` (which would override natural document order), and a real full-page Tab traversal -- every visible focusable element, not just the first few stops `test_keyboard_navigation_e2e.py` asserts -- visits elements in exactly the same sequence `querySelectorAll` returns for the page, for every page/state `tests/test_accessibility_e2e.py` covers (17 pages/states), including correctly walking past the Roadmap concept-preview iframe boundary rather than misreading it as a broken order. What remains manual: whether that resulting order is actually a *sensible* reading/interaction order, not just mechanically consistent with document order | All 17 pages/states `test_accessibility_e2e.py` covers, full traversal |
| 9 | 2.4.6 Headings and Labels | Screen reader users can navigate by heading/landmark and understand each one out of context | All covered pages |
| 10 | 2.4.7 Focus Visible | `tests/test_reflow_and_focus_indicators_e2e.py` automates the objective part -- every visible focusable element on every page/state `tests/test_accessibility_e2e.py` covers (17 pages/states) shows *some* computed-style change on focus, not only the first text input `test_keyboard_navigation_e2e.py` checks. What remains manual: whether the change is actually *perceivable* (sufficient contrast/size) | All 17 pages/states `test_accessibility_e2e.py` covers |
| 11 | 2.5.7 Dragging Movements / 2.5.8 Target Size | `tests/test_target_size_e2e.py` automates the objective 2.5.8 geometry check in real Chromium at both desktop (1280x720) and narrow/mobile (375x812) viewports: visible pointer targets must meet the 24x24 CSS-pixel minimum or a mechanically verified Inline/Spacing exception. Context-dependent Equivalent/Essential exceptions and Dragging Movements remain manual, as does any Research-only control until that state is exercised by browser evidence. This automated gate is regression evidence, not a WCAG conformance claim. | All browser-E2E pages/states currently reachable without Research; Research-only controls remain explicit debt |
| 12 | 3.1.2 Language of Parts | Screen reader pronunciation is correct for any non-English terms/citations present in evidence text | Claim detail, Ask evidence panels |
| 13 | 3.2.1/3.2.2 On Focus / On Input | `tests/test_focus_and_input_e2e.py` automates the objective part: focusing or typing into the Ask/Discover query input never navigates or submits the form on its own, in a real Chromium instance, for both pages. What remains manual: any other form control this repository adds in the future that could introduce an on-focus/on-input context change | Ask query input, Discover query input |
| 14 | 3.3.1/3.3.3 Error Identification and Suggestion | Submitting Ask or Discover with a blank/whitespace-only question now shows a `role="alert"` error naming the problem ("the search box was empty") instead of silently re-rendering the same blank form, verified by a real Chromium click-submit in `tests/test_browser_e2e.py`. What remains manual: whether a screen reader actually announces the `alert` role correctly across AT/browser combinations, and any other form validation this repository adds in the future | Ask/Discover query submission |
| 15 | 4.1.3 Status Messages | Dynamic status changes (research progress states, degraded-provider notices) are announced via `aria-live`/role="status" without moving focus | Ask progressive research states (once Research capability is testable) |

This list is deliberately scoped to criteria this repository's existing
automated suites (axe-core + scripted keyboard tests) do not establish --
it is not the full WCAG 2.2 AA success-criteria list, and passing every row
here still does not by itself constitute a conformance claim; treat it as
the concrete remainder after automated coverage, consistent with
`docs/INDUSTRY_REALITY_CHECK.md`'s standing caveat.

## Recorded passes

None yet. The first entry should follow the format:

```
### 2026-MM-DD -- <build/commit identity> -- <tester>

Assistive technology: <e.g. VoiceOver on iOS 18, Safari>

| # | Result | Notes |
|---|---|---|
| 1 | PASS/FAIL/NOT YET TESTABLE | ... |
...
```
