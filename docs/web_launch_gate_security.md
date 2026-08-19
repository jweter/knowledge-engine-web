# Web Launch Gate: Dependency Security and Reproducibility

Status: implemented launch-hardening prerequisite. This milestone changes the
dependency and update boundary only; it does not make the alpha public and does
not implement the AI orchestrator route.

## Why this gate exists

The Render alpha previously resolved FastAPI 0.121.3 and Starlette 0.50.0.
GitHub's dependency review reported five Starlette advisories, including two
high-severity advisories. The old FastAPI constraint capped Starlette below
0.51.0, while the complete advisory set required Starlette 1.3.1 or newer.
Dependabot therefore could not produce a security update.

The web application also depended on the moving `main` branch of
`knowledge-engine-ai`. Although `poetry.lock` recorded one resolved commit, a
fresh dependency resolution was allowed to select later, unreviewed AI code.
That is not an acceptable deployment boundary.

## Decisions

- FastAPI is constrained to the compatible 0.141 release line.
- Starlette is a direct dependency on the 1.6 release line. The direct
  constraint makes the audited security floor visible in project metadata.
- `knowledge-engine-ai` is pinned to commit
  `6e5693c09a80768e7d4f47fca608b70c2f6664ec`, the merged AI launch-gate
  revision that removes its obsolete vulnerable Click dependency.
- Dependabot checks Python, GitHub Actions, and Docker dependencies weekly.
- CI audits the resolved Python environment with `pip-audit` on every pull
  request and push to `main`.
- CI continues to run formatting, linting, strict type checking, tests, a
  clean-diff check, a Docker build, and an authenticated container smoke test.

An AI update is now an intentional dependency change: advance the immutable
revision, regenerate `poetry.lock`, run the quality gate, and review the diff.

## What this proves

- The application can resolve and run on a Starlette version outside the known
  advisory ranges.
- A clean checkout installs the same AI revision used during review.
- Automated dependency updates have committed configuration and can report
  future drift across all deployed dependency surfaces.

Closing a GitHub alert remains GitHub's post-merge responsibility after it
rescans the default branch. This document records the dependency contract; it
does not claim an alert is closed before that rescan occurs.

## What remains before an open public alpha

This gate does not add multi-user authentication, rate limiting, abuse
protection, durable hosted research sessions, hosted inference, or a live core
service. The Render deployment remains a password-gated, snapshot-backed alpha.

The next product milestone is AI-O14: route `/ask` through
`knowledge_engine_ai.run_research_question` behind an explicit capability gate,
while retaining deterministic retrieval when the AI/core runtime is absent.
That milestone must first define how the deployed container obtains the `ke`
runtime and corpus metadata; this dependency-hardening change does not smuggle
that larger runtime into the image.

## 2026-08-18: AI pin advanced for WEB-FRD-3

`knowledge-engine-ai` is now pinned to commit
`9a214c3288107d0426000184a9fea364b529b01b` (was `62387aabba4b8621bea5621dcc7c88f40e91c6bb`),
following this document's own "intentional dependency change" procedure:
advance the immutable revision, regenerate `poetry.lock`, run the quality
gate, review the diff. The previous pin predates AI's
`FederatedCandidateSummary.canonical_id` and
`FederatedDiscoveryResult.provider_disagreements` fields (added by AI's
`59f75f0`/`26ac10e`, merged via PR #45); wiring
`knowledge_engine_web.discovery_presentation.build_discovery_presentation()`
into the live `/discover` route (WEB-FRD-3) requires both, and mypy's
structural-typing check against `DiscoveryResultSource` failed against the
old pin until this bump. No `knowledge-engine-ai` public API was removed or
renamed between the two revisions -- this is a backward-compatible superset,
not a breaking bump.

## 2026-08-19: AI pin advanced for WEB-FRD-4

`knowledge-engine-ai` is now pinned to commit
`f4715d32a62748ec1ff395ee57402d192362c1a5` (was
`9a214c3288107d0426000184a9fea364b529b01b`), following the same procedure as
the WEB-FRD-3 entry above. The previous pin predates AI's
`FederatedProviderObservationFlags` /
`FederatedCandidateSummary.observation_flags` fields (added by AI's
`f4715d3`, merged via AI PR #49); rendering per-provider retraction/preprint
observations (WEB-FRD-4) requires them, and mypy's structural-typing check
against the extended `CandidateSource` protocol failed against the old pin
until this bump. No `knowledge-engine-ai` public API was removed or renamed
between the two revisions -- this is a backward-compatible superset, not a
breaking bump. `poetry lock` was regenerated and the full quality gate
(`ruff format --check .`, `ruff check .`, `mypy .`, `pytest`) was run clean
against the new pin.
