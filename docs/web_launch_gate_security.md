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
  `1cdbeb8b64749605f67b57fbc801b2eab37ccfce`, the reviewed AI-O12 package
  revision already represented by the previous lockfile.
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
