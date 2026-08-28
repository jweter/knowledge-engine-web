# Hosted Alpha Research Workspace

## Status

Implemented as the first deployment-enablement slice for hosted Research Copilot testing.

The Render alpha still fails closed until the remaining runtime prerequisites exist. This slice does **not** bypass `evaluate_ai_capability`, install Core, or invent a model endpoint. It removes two deployment blockers honestly: a Core-compatible `sources.csv` input and a durable writable Evidence Record workspace when a real persistent mount is attached.

## What changed

At image build time, `knowledge_engine_web.alpha_workspace build-sources` derives a deterministic `sources.csv` from the committed SQLite snapshot's `papers.doi` and `papers.title` columns. Core's public metadata-overlay contract requires those two columns; no new scientific metadata is inferred.

At container startup, `scripts/start-alpha.sh` checks whether the configured persistent root already exists and is writable. It never creates the root. If a real mount is present, the startup path:

1. seeds or reconciles `/var/data/evidence_records.jsonl` from the image baseline;
2. preserves Evidence Records promoted by prior research runs;
3. adds newly committed baseline Evidence Records by `evidence_record_id` on later deploys;
4. refreshes the derived `sources.csv` seed;
5. creates the research-paper and federated-discovery ledger directories inside the mounted root; and
6. points Web's evidence/source settings at those durable files for the running process.

If the mount is missing or preparation fails, the application still starts against the committed retrieval snapshot. Research Copilot remains capability-gated and disabled rather than degrading normal `/ask` retrieval.

## Why the database is not copied into the research workspace

The Web alpha database is deliberately trimmed. It contains the tables and FTS content Web needs, not Core's complete operational schema, source pages, or full parsed research state. Treating that snapshot as a writable Core database would create a false end-to-end path that can retrieve but cannot safely acquire, extract, ground, and promote new papers.

The next deployment slice must therefore solve the **Core execution boundary** explicitly. It should provide the `ke` capabilities AI actually invokes against a complete Core workspace or a narrow service boundary; it should not silently point Core at Web's trimmed snapshot.

## Remaining blockers before the checkbox can become available

After this slice, the hosted capability gate still correctly requires:

- a real persistent mount at the configured root;
- a resolvable Core `ke` execution boundary with the commands used by Research Copilot;
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
