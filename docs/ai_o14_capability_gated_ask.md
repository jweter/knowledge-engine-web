# AI-O14 Capability-Gated Ask Integration

## Status

Implemented. The `/ask` page now invokes `knowledge-engine-ai`'s complete
`run_research_question` workflow only when the deployment has every static
prerequisite. Deterministic web retrieval remains the primary, always-available
path.

## Objective

Replace the historical web-local Ollama narration call with the Research
Copilot composition already built in `knowledge-engine-ai`: durable session
creation, primary and contradiction-oriented retrieval, local-model narration,
deterministic verification, sourced-claim resolution, and the Research ISA
close gate.

The integration must fail closed. An incomplete AI runtime may disable the
optional control, but it must never disable retrieval or imply that generated
text is evidence, legal approval, scientific review, or a scientific verdict.

## Architecture

`knowledge_engine_web.ai_orchestration` is the boundary between FastAPI and the
AI repository.

- `evaluate_ai_capability` inspects static deployment prerequisites without
  executing core, contacting Ollama, or creating a database.
- `run_ai_orchestration` creates a `SessionRepository`, constructs the AI
  package's `OllamaLLM`, invokes `run_research_question`, and closes its SQLite
  connection.
- `main.py` remains an adapter: it always performs deterministic retrieval,
  optionally calls the integration service, and renders the returned durable
  result.
- `ask.html` shows the session ID, close-gate state, verification state,
  narrative, and resolved source citations without recomputing them.

The former `knowledge_engine_web.llm` and `knowledge_engine_web.synthesis`
modules remain for backward-compatible tests and history, but `/ask` no longer
uses them.

## Capability Contract

Research Copilot is enabled only when all of these are true:

1. `KE_WEB_LLM_MODEL` is non-empty.
2. `KE_WEB_SOURCES_PATH` names an existing regular file.
3. `KE_WEB_EVIDENCE_RECORDS_PATH` names an existing regular file.
4. `KE_WEB_KE_EXECUTABLE` resolves through the platform's executable search.
5. `KE_WEB_SESSION_DB_PATH` names a writable file, or its existing parent
   directory is writable so SQLite can create it.

The first failed requirement produces a stable internal reason code. Visitor
text intentionally does not expose environment-variable names, executable
paths, database paths, or raw exceptions.

This is a static capability check, not a live Ollama health check. A network
probe on every form render would make deterministic retrieval depend on model
latency and availability. Ollama and core are exercised only after a person
opts in; a runtime failure is sanitized and retrieval remains visible.

## Configuration

The complete local or trusted-LAN configuration is:

```text
KE_WEB_LLM_MODEL=qwen2.5:1.5b
KE_WEB_OLLAMA_HOST=http://127.0.0.1:11434
KE_WEB_SOURCES_PATH=/safe/local/path/sources.csv
KE_WEB_EVIDENCE_RECORDS_PATH=/safe/local/path/evidence_records.jsonl
KE_WEB_SESSION_DB_PATH=data/research_sessions.db
KE_WEB_KE_EXECUTABLE=ke
```

`KE_WEB_KE_EXECUTABLE` defaults to `ke`. An absolute executable path is useful
for local development where core and web use separate virtual environments.

## Request Behavior

Without `synthesize=1`, `/ask` performs no Research Copilot work and creates no
session. With `synthesize=1`:

- an unavailable capability safely downgrades to retrieval-only output;
- an available capability creates one durable Research Session and renders its
  committed outcome;
- core or Ollama runtime failure produces a neutral inline error while normal
  retrieval remains visible; and
- generated narration is always labeled AI-generated and not reviewed.

## Deployment Decision

The Render alpha remains intentionally retrieval-only. Its current image does
not ship `sources.csv`, the core `ke` runtime, a durable Research Session store,
or an authenticated hosted Ollama service. AI-O14 does not solve those operator
decisions by quietly inflating the image or exposing a laptop model endpoint.

AI-O15 must decide durable hosted session storage before public Research
Copilot is enabled. AI-O16 then owns timeouts, concurrency, rate limits, and the
deployment weight of core. A hosted inference service still requires its own
authentication, privacy, provenance, and cost controls.

## Testing

Tests cover every static prerequisite, non-mutating form checks, sanitized
runtime failures, exact settings passed into `run_research_question`, disabled
and enabled controls, forged unavailable requests, durable result rendering,
resolved citations, and preservation of deterministic retrieval after an AI
failure.

## Explicit Non-Goals

AI-O14 does not:

- expose Ollama to the public internet;
- add a hosted model provider;
- make Render run core or Ollama;
- make the session database durable across hosted redeploys;
- add rate limiting, queues, cancellation, or request timeouts;
- change retrieval ranking or Evidence Intelligence;
- treat narration as evidence or scientific review; or
- replace snapshot reads with core's future persistent HTTP host.

## Next Handoff

AI-O15 is complete: deployed Research Sessions require a canonically contained
persistent mount, while local development may use local SQLite. See
`docs/ai_o15_deployed_session_persistence.md`. AI-O16 is next: bound execution
time and request concurrency before public Research Copilot is enabled.
