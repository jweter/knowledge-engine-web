# Owner-approved roadmap direction — 2026-10-25

Status: proposed roadmap addendum for review, not an accepted implementation or permission to execute.

This records explicit owner decisions. Reconcile with the authoritative local roadmap, AGENTS.md, active claims, dirty worktrees, and newer accepted work before implementation. Existing safety, provenance, testing, product-reality, controller authorization, and worker lease gates remain mandatory. Do not treat GitHub main as newer than the authoritative local version.

## Research Report user experience
- One submitted research question initiates the complete local-compute / online-source research workflow; the user need not pre-ingest documents.
- Display progress, evidence, source links, citation provenance, uncertainty, final report, and useful error states.
- Do not require a large local document database or Ollama for the default flow. Avoid persistent bulk storage and respect bounded temporary data retention.

## Next slices
1. Audit existing /ask and Research Report integration for mandatory local-corpus dependencies.
2. Add one-request report orchestration UI with observable progress and citations.
3. Verify a real online-source report and cleanup using product-native acceptance tests.
