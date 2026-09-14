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
| 3 | 1.4.1 Use of Color | Every place status/meaning is conveyed by color alone (certainty levels, degraded-provider badges, PASS/FAIL/FLAG) also has a text/icon cue | Ask conclusion rows, mobile review panel |
| 4 | 1.4.4 Resize Text / 1.4.10 Reflow | `tests/test_reflow_and_focus_indicators_e2e.py` automates the objective part -- no horizontal overflow at a 320px CSS width -- for every page/state `tests/test_accessibility_e2e.py` covers (17 pages/states), and found/fixed two real violations: a `<code>` element without `overflow-wrap` on claim detail, and the Roadmap concept preview's topbar overflowing 671px because its flex children could not shrink below their nowrap content width (see `docs/browser_e2e_testing.md`). What remains manual: whether reflowed content still reads in a sensible order/hierarchy, and 400% browser-zoom behavior specifically (only the equivalent 320px-viewport proxy is automated) | All 17 pages/states `test_accessibility_e2e.py` covers |
| 5 | 1.4.13 Content on Hover or Focus | Any hover/focus-triggered content (tooltips, the "Inspect" dropdown) is dismissible, hoverable, and persistent | Header "Inspect" dropdown |
| 6 | 2.1.4 Character Key Shortcuts | No single-character keyboard shortcut fires unexpectedly while a screen reader is active | All pages |
| 7 | 2.3.3 Animation from Interactions | `tests/test_reduced_motion_e2e.py` automates the objective part: with `prefers-reduced-motion: reduce` emulated in a real Chromium instance, the constellation canvas's rendered pixel output stays identical over time (the `requestAnimationFrame` loop never runs) and the headline aurora animation's computed duration collapses to effectively zero, on both the homepage and a second site-wide page (`/about`); a control case confirms the same comparison detects real motion under the default setting. What remains manual: whether a screen reader announces anything about the motion, and judgment for any other interaction-triggered animation this repository adds in the future | Homepage, all pages (site-wide constellation layer) |
| 7a | 2.2.2 Pause, Stop, Hide | A site-wide "Pause background motion" control (`#motion-toggle`, added this run) now stops the constellation canvas and the homepage headline's aurora animation without requiring `prefers-reduced-motion`; `tests/test_keyboard_navigation_e2e.py` verifies it is keyboard-operable (Tab + Enter) and actually halts the animation, and that the preference persists across reload/navigation. What automated coverage does not establish: whether a screen reader announces the control's role/state (`aria-pressed`) clearly, and whether its label makes its purpose obvious without visual context | Every page (site-wide header control) |
| 8 | 2.4.3 Focus Order | `tests/test_focus_order_e2e.py` automates the objective part: no element has a positive `tabindex` (which would override natural document order), and a real full-page Tab traversal -- every visible focusable element, not just the first few stops `test_keyboard_navigation_e2e.py` asserts -- visits elements in exactly the same sequence `querySelectorAll` returns for the page, for every page/state `tests/test_accessibility_e2e.py` covers (17 pages/states), including correctly walking past the Roadmap concept-preview iframe boundary rather than misreading it as a broken order. What remains manual: whether that resulting order is actually a *sensible* reading/interaction order, not just mechanically consistent with document order | All 17 pages/states `test_accessibility_e2e.py` covers, full traversal |
| 9 | 2.4.6 Headings and Labels | Screen reader users can navigate by heading/landmark and understand each one out of context | All covered pages |
| 10 | 2.4.7 Focus Visible | `tests/test_reflow_and_focus_indicators_e2e.py` automates the objective part -- every visible focusable element on every page/state `tests/test_accessibility_e2e.py` covers (17 pages/states) shows *some* computed-style change on focus, not only the first text input `test_keyboard_navigation_e2e.py` checks. What remains manual: whether the change is actually *perceivable* (sufficient contrast/size) | All 17 pages/states `test_accessibility_e2e.py` covers |
| 11 | 2.5.7 Dragging Movements / 2.5.8 Target Size | `tests/test_target_size_e2e.py` automates part of 2.5.8: every non-inline pointer target (buttons, nav/footer links, form controls -- excluding plain text-flow links and checkbox/radio inputs, which WCAG's "Inline" and "User agent control" exceptions cover) is at least 24x24 CSS px, on every page/state `tests/test_accessibility_e2e.py` covers. What remains manual: the "Equivalent," "Essential," and "Spacing" exceptions (whether an undersized target has adequate spacing from its neighbors or a same-purpose larger alternative elsewhere), and 2.5.7 Dragging Movements entirely (this codebase has no drag-style interaction today, but that has not been verified against every future addition) | All 18 pages/states `test_accessibility_e2e.py` covers |
| 12 | 3.1.2 Language of Parts | Screen reader pronunciation is correct for any non-English terms/citations present in evidence text | Claim detail, Ask evidence panels |
| 13 | 3.2.1/3.2.2 On Focus / On Input | No unexpected context change (navigation, form submission) merely from focusing or typing into a field | Ask query input, Discover query input |
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
