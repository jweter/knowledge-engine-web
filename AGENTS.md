# Knowledge Engine Web — Agent Entry Point

All coding, Codex, scheduled, and autonomous agents working in this repository must load current repository evidence before making changes.

## Required reading

Before selecting or implementing substantial work, read:

1. `docs/agent-development-policy.md` — repository-specific autonomous development rules and the shared Knowledge Engine family policy it references.
2. `docs/project-status.yaml` — continuity snapshot; reconcile it with live PR, CI, issue, and code state before trusting it.
3. The active roadmap/design document named by `docs/project-status.yaml`.
4. `docs/research_report_v1.md` — adopted answer-first, two-layer research-report experience and Monster acceptance contract.
5. `docs/INDUSTRY_REALITY_CHECK.md` — the current repo-specific gap analysis versus production web/research-software expectations.

## Research Report v1 priority

Until the Monster Energy / one-year blood-pressure acceptance case passes on the deployed Ask path, treat Research Report v1 as a standing product constraint. Prefer work that directly improves answer-first presentation, conclusion/certainty rendering, evidence/methodology inspection, provenance, counter-evidence visibility, missing-evidence disclosure, or durable research progress over purely decorative UI work.

Do not hide provider degradation, missing evidence, or source provenance to make the page look cleaner.

## How to use the reality check

`docs/INDUSTRY_REALITY_CHECK.md` is a durable quality-gap baseline, not a replacement for verified repository state or the active product roadmap.

Use it when selecting, designing, reviewing, and validating work:

- prefer roadmap-compatible work that closes a documented industry-quality gap when priorities are otherwise comparable;
- do not declare a gap closed merely because code exists or CI passes when the report calls for browser, accessibility, Product Reality, observability, performance, or integration evidence;
- when a major capability materially changes the assessment, update the reality check or explicitly record why the prior finding still applies;
- never let an old score override newer verified evidence.

## Knowledge Engine family coordination

This repository is the Web/API/frontend layer of one coordinated three-repository system. Coordinate shared contracts with:

- `jweter/knowledge-engine-core`
- `jweter/knowledge-engine-ai`

Do not assume cross-repository compatibility. Verify shared schemas, CLI/output contracts, persistence assumptions, Research Report v1 semantics, and orchestration boundaries before changing them.

## Execution rule

Existing broken, pending, or merge-ready work takes priority over new roadmap work. Never fabricate repository state, and never merge failed, pending, conflicted, blocked, or materially uncertain work.
