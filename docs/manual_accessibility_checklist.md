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
| 4 | 1.4.4 Resize Text / 1.4.10 Reflow | Page remains usable (no loss of content/function, no two-dimensional scrolling) at 400% zoom and at a 320px CSS width | Homepage, Ask, claim detail, dashboard, graph |
| 5 | 1.4.13 Content on Hover or Focus | Any hover/focus-triggered content (tooltips, the "Inspect" dropdown) is dismissible, hoverable, and persistent | Header "Inspect" dropdown |
| 6 | 2.1.4 Character Key Shortcuts | No single-character keyboard shortcut fires unexpectedly while a screen reader is active | All pages |
| 7 | 2.3.3 Animation from Interactions | Any animation triggered by interaction (constellation/neural web face, PR #146) respects `prefers-reduced-motion` | Homepage |
| 7a | 2.2.2 Pause, Stop, Hide | A site-wide "Pause background motion" control (`#motion-toggle`, added this run) now stops the constellation canvas and the homepage headline's aurora animation without requiring `prefers-reduced-motion`; `tests/test_keyboard_navigation_e2e.py` verifies it is keyboard-operable (Tab + Enter) and actually halts the animation, and that the preference persists across reload/navigation. What automated coverage does not establish: whether a screen reader announces the control's role/state (`aria-pressed`) clearly, and whether its label makes its purpose obvious without visual context | Every page (site-wide header control) |
| 8 | 2.4.3 Focus Order | Full-page Tab traversal (not just the first few stops `test_keyboard_navigation_e2e.py` asserts) matches a sensible reading/interaction order end to end | Every covered page, full traversal |
| 9 | 2.4.6 Headings and Labels | Screen reader users can navigate by heading/landmark and understand each one out of context | All covered pages |
| 10 | 2.4.7 Focus Visible | Every interactive element (not only the first text input `test_keyboard_navigation_e2e.py` checks) shows a visible focus indicator | All covered pages |
| 11 | 2.5.7 Dragging Movements / 2.5.8 Target Size | Any drag-style interaction has a non-drag alternative; touch targets are at least 24x24 CSS px or have adequate spacing | Mobile viewport, any interactive controls |
| 12 | 3.1.2 Language of Parts | Screen reader pronunciation is correct for any non-English terms/citations present in evidence text | Claim detail, Ask evidence panels |
| 13 | 3.2.1/3.2.2 On Focus / On Input | No unexpected context change (navigation, form submission) merely from focusing or typing into a field | Ask query input, Discover query input |
| 14 | 3.3.1/3.3.3 Error Identification and Suggestion | Form validation errors are announced to a screen reader, not just shown visually, and suggest a correction | Ask/Discover query submission |
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
