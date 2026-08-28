# Hosted Alpha Research Workspace

## Status

Implemented as the first two deployment-enablement slices for hosted Research Copilot testing.

The Render alpha still fails closed until the remaining runtime prerequisites exist. These slices do **not** bypass `evaluate_ai_capability`, install Core, or invent a model endpoint. They remove two deployment blockers honestly: a Core-compatible `sources.csv` input plus a durable writable Evidence Record workspace when a real persistent mount is attached, and a hosted-only command-surface preflight that rejects an incomplete `ke` runtime before the UI advertises Research mode.

## Persistent research workspace

At image build time, `knowledge_engine_web.alpha_workspace build-sources` derives a deterministic `sources.csv` from the committed SQLite snapshot's `papers.doi` and `papers.title` columns. Core's public metadata-overlay contract requires those two columns; no new scientific metadata is inferred.

At container startup, `scripts/start-alpha.sh` checks whether the configured persistent root already exists and is writable. It never creates the root. If a real mount is present, the startup path:

1. seeds or reconciles `/var/data/evidence_records.jsonl` from the image baseline;
2. preserves Evidence Records promoted by prior research runs;
3. adds newly committed baseline Evidence Records by `evidence_record_id` on later deploys;
4. refreshes the derived `sources.csv` seed;
5. creates the research-paper and federated-discovery ledger directories inside the mounted root; and
6. points Web's evidence/source settings at those durable files for the running process.

If the mount is missing or preparation fails, the application still starts against the committed retrieval snapshot. Research Copilot remains capability-gated and disabled rather than degrading normal `/ask` retrieval.

## Hosted Core command preflight

Finding an executable named `ke` is not enough to prove the deployment can execute the complete General Question Research Loop. Render now sets `KE_WEB_CORE_CLI_COMMAND_PREFLIGHT=true`. With that hosted-only flag enabled, Web performs cached, command-specific `--help` probes for every Core command the current Research Copilot path may invoke:

- `evidence-report`
- `evidence-intelligence`
- `federated-discover`
- `citation-snowball`
- `general-question-acquisition-plan`
- `general-question-acquire-pmc`
- `general-question-acquire-europe-pmc`
- `general-question-acquire-core`
- `general-question-acquire-unpaywall`
- `extraction-review-batch-generate`
- `extraction-review-autoclassify`
- `extraction-review-promote`
- `evidence-review-automate`
- `evidence-record-review-promote`

These probes do not contact providers, acquire papers, mutate research state, or run a model. If any required command is absent, times out, or returns a nonzero help result, the capability reason is `core_cli_incomplete` and `/ask` remains retrieval-only.

The preflight is intentionally disabled by default for local/test compatibility and explicitly enabled by the hosted blueprint. That keeps local development behavior stable while preventing a deployed checkbox from becoming available merely because an unrelated executable happens to exist at the configured path.

## Why the database is not copied into the research workspace

The Web alpha database is deliberately trimmed. It contains the tables and FTS content Web needs, not Core's complete operational schema, source pages, or full parsed research state. Treating that snapshot as a writable Core database would create a false end-to-end path that can retrieve but cannot safely acquire, extract, ground, and promote new papers.

The next deployment slice must therefore solve the **Core execution boundary** explicitly. It should provide the `ke` capabilities above against a complete Core workspace or a narrow service boundary; it should not silently point Core at Web's trimmed snapshot.

## Remaining blockers before the checkbox can become available

After these slices, the hosted capability gate still correctly requires:

- a real persistent mount at the configured root;
- a resolvable Core `ke` execution boundary that passes the complete command preflight;
- a configured LLM model and reachable authenticated/trusted inference endpoint; and
- the existing discovery/session/storage guardrails to pass.

When those prerequisites are real, the existing `/ask` capability check will enable Research Copilot automatically. No template bypass is required.

## Acceptance tests

`tests/test_alpha_workspace.py` verifies that:

- DOI metadata generation is deterministic and duplicate-safe;
- missing Core metadata columns fail closed;
- a persistent root must already exist;
- durable research-promoted evidence survives redeploy seeding;
- newer baseline evidence is merged without erasing prior research records;
- malformed durable evidence is never overwritten; and
- the Docker image and startup wrapper use the new preparation path.

`tests/test_ai_orchestration.py` additionally verifies that the hosted Core command preflight covers the complete explicit command manifest and fails closed with a stable `core_cli_incomplete` reason when the configured executable cannot satisfy it.
