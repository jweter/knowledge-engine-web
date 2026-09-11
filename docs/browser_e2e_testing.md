# Browser end-to-end testing

Status: initial infrastructure, Ask critical path only.

`docs/INDUSTRY_REALITY_CHECK.md` identified "no Playwright/Selenium-style
browser workflow evidence was found" as a P1 production gap. `tests/test_browser_e2e.py`
is the first committed, reusable answer to that gap.

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
  viewport.

This first pass already caught and fixed two real rendering bugs, not test
artifacts: `.snapshot-line` (the footer's snapshot metadata line, which can
contain a long comma/underscore-separated `corpus_id` with no wrap
opportunity) and `.inspect-menu > div` (the header's "Inspect" dropdown,
whose closed-state hiding relied only on native `<details>` semantics and
could still occupy real off-canvas layout geometry in at least one real
browser engine). Both now wrap/hide explicitly rather than relying on
implicit browser behavior. See `knowledge_engine_web/static/style.css`.

Not yet covered: the remaining critical-path scenarios
`docs/INDUSTRY_REALITY_CHECK.md` lists (indexed miss -> research-required
state, partial-answer updates, degraded-provider state, authentication/session
expiration, refresh/resume behavior) and any accessibility (axe/WCAG)
automation. Extend this module -- or add sibling modules following the same
pattern -- rather than re-deriving the live-server/fixture-data approach.

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
