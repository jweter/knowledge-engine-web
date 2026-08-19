# Agent Development Policy

This document governs scheduled and autonomous engineering work on
`knowledge-engine-web`. It exists so a fresh, isolated agent run — with no
memory of any prior conversation — can pick this repository up cold and work
it correctly.

`knowledge-engine-core`'s `docs/agent-development-policy.md` defines the
shared foundation for the whole Knowledge Engine family (project isolation,
source-of-truth order, the PR state machine, priority order, trust
boundaries, human escalation boundaries, and truthfulness rules). Read it
first. This document only states what is specific to this repository —
required checks, this repository's own architecture boundary, and its
current milestone.

## 1. This repository's place in the family

`knowledge-engine-web` is a **read-only** presentation layer over Core's
already-validated data, plus one deliberate opt-in exception. Two consumption
paths exist and must not be blurred:

- **Direct SQLite reflection** (`sqlalchemy.create_engine` +
  `Table(..., autoload_with=engine)`) against Core's database. This is the
  primary path for graph/evidence rendering and is never a `knowledge_engine`
  Python import (Core's interface contract forbids that; the CLI is the only
  supported interface).
- **`knowledge_engine_ai.ke_client`** — the one supported subprocess boundary
  for invoking Core's `ke` CLI. Every feature that needs to call `ke` at
  request time (Research Copilot synthesis via `/ask`, federated discovery
  via `/discover`) goes through this module, never a raw `subprocess.run`
  inside this repository. `knowledge_engine_web/ai_orchestration.py` and
  `discovery_orchestration.py` are the established pattern: a capability-gate
  function that fails closed without touching the network, and a guarded
  execution function using this repository's own `AIRequestGuard` instance
  per feature (each optional feature gets its **own** guard instance and its
  own `KE_WEB_*` timeout/concurrency/rate-limit settings, so one feature
  cannot starve another — see `ai_guardrails.py`).

Before changing anything Core exposes that this repository reads (database
schema, a `ke` CLI flag, a `--output` JSON shape), check
`knowledge-engine-core`'s cross-repository coordination rule (section 1a of
its policy document) — Core is expected to identify Web as a consumer before
merging a breaking change, but this repository should also notice if a Core
change silently broke something here.

## 2. Cost-consciousness for optional AI/network features

Every feature that calls `ke` at request time has a real cost/latency/rate-
limit profile (local LLM inference, or real external provider HTTP calls).
Do not wire a new such call into an always-on request path (notably `/ask`'s
existing behavior) without treating it as a real cost-profile change. New
optional network-touching capability belongs in its own new, separate,
opt-in route with its own guard and its own settings — the pattern
`/discover` (WEB-FRD-1) established alongside the pre-existing `/ask`
Research Copilot path — not folded into an existing route's default
behavior.

## 3. Required CI

For the exact current head SHA to count as GREEN:

- `Quality` (`.github/workflows/quality.yml`, job `checks`) —
  `ruff format --check .`, `ruff check .`, `mypy .`, `pytest`;
- `Docker build` (same workflow, job `docker`) — the deployable image
  actually builds.

Both are required for every PR in this repository (no path filtering).
Merge with squash. Never opt for a draft PR — this repository's convention,
inherited from the whole Knowledge Engine family, is a PR is either not yet
opened or opened ready for review.

## 4. Development workflow specifics

- Run the full local gate before opening a PR:
  `poetry run python scripts/quality_preflight.py` runs `ruff format --check .`,
  `ruff check .`, `mypy knowledge_engine_web tests`, `pytest`, `pip-audit`, and
  `git diff --check` in the same order as CI's `checks` job and stops at the
  first failure -- see `docs/quality_preflight.md`. This is this repository's
  implementation of the cross-repository prevention rule in
  `knowledge-engine-core` issue #371.
- New features that reach `knowledge-engine-ai`/`knowledge-engine-core`
  through a subprocess call should be live-verified against the real `ke`
  binary and, where applicable, real external provider APIs before the PR is
  opened — not just fake-transport unit tests. This project's established
  discipline distrusts a fake-only pass; see `/discover`'s and `/ask`'s own
  PR history for the pattern (start a real local server, hit the real route,
  confirm the rendered output against the actual on-disk artifact Core
  produced).
- For a UI-visible change, actually load the page in a browser (or via a
  local `uvicorn` + `curl`) before calling the change done — a passing test
  suite verifies code correctness, not that the feature is visibly correct.
- Update `docs/web_design.md`'s relevant section and
  `docs/federated_discovery_transparency_roadmap.md`'s relevant WEB-FRD-#
  Status paragraph in the same PR when a milestone's status changes.

## 5. Continuity record

`docs/project-status.yaml` is this repository's continuity cache — same
contract as Core's: verify it against real repository state at the start of
every scheduled run, update it whenever durable project reality changes, and
do not let it silently drift from what is actually true.

## 6. Truthfulness and safety

Never fabricate repository access, files, tests, CI results, PR numbers,
merge results, or project progress. Never expose or commit secrets — this
includes never letting a `KE_WEB_*` credential or API key enter a log line,
commit, or PR body. Never merge red, pending, missing-required-check,
conflicted, or materially uncertain code. Prefer small, reversible, testable
changes.
