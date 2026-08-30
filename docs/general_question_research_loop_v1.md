# General Question Research Loop v1 - Web responsibilities

Status: active cross-repository build plan  
Tracking issue: #86  
Parent AI tracking issue: `knowledge-engine-ai` #69

## Purpose

The Ask experience must behave like a research tool, not a fixed-corpus demo. A question outside the indexed evidence base should visibly enter a bounded research workflow when Research Copilot is available.

The Web layer does not decide scientific truth. It invokes the AI orchestration path safely and renders the resulting research state, evidence provenance, search coverage, and limitations.

## Current Research mode path

Research mode now supplies both AI policies required by the complete synchronous GQR path:

1. indexed evidence is searched first;
2. when AI's deterministic coverage-gap rule fires, Core federated discovery is attempted;
3. Web enables Core's bounded acquisition plan for that discovery run;
4. the same discovery ledger is passed to `GroundedCompletionPolicy`;
5. eligible accessible papers may be acquired or already-indexed papers reused;
6. automatic extraction must pass Core's grounded review and durable EvidenceRecord promotion boundary;
7. the original question is re-run against the enlarged grounded evidence base;
8. synthesis switches to that reretrieved report only when newly promoted grounded evidence exists;
9. deterministic citation/qualifier verification and the Research ISA close gate still control release.

Discovery candidates, acquisition-plan rows, acquired Papers, and staged automatic classifications never become answer evidence merely by existing.

Web consumes `knowledge-engine-ai`'s stable `derive_research_state` contract and renders that metadata directly on `/ask`. Web does not recreate or infer the state from answer prose. The pinned AI dependency includes `ResearchStateResult` schema v2, which distinguishes a releaseable indexed answer from a releaseable answer that actually used grounded post-research re-retrieval.

## Required user-visible states

The Web contract renders stable research states from AI rather than inferring them from prose:

- `indexed_answer`
- `research_required`
- `researching`
- `partial_answer`
- `researched_answer`
- `insufficient_evidence`
- `provider_degraded`
- `blocked`

`researched_answer` means the released narrative actually used newly promoted grounded evidence returned by the original-question re-retrieval. `partial_answer` means indexed evidence was releaseable, but newly discovered leads did not become the evidence used for that answer.

`researching` remains part of the stable schema for the later durable/polling workflow. The current HTTP request is synchronous, so the page can show an immediate generic running notice and the complete durable event trace after the request returns, but it cannot yet stream each in-progress event live.

Recommended visitor-facing progression:

```text
Searching indexed evidence...
Indexed evidence is thin; expanding the literature search...
Searching scholarly providers...
Validating and acquiring eligible sources...
Extracting grounded evidence...
Re-checking the original question against the enlarged evidence base...
Preparing and verifying a source-grounded answer...
```

Do not claim a stage succeeded unless its durable AI/Core result says so.

## Final answer requirements

Every completed Research Copilot result should make these distinctions explicit:

- whether indexed evidence was sufficient;
- whether grounded completion was attempted;
- how many new Evidence Records were promoted;
- whether the released answer used post-research re-retrieval or the initial index;
- providers searched and providers degraded/unavailable;
- incomplete coverage;
- citations and Evidence Record provenance;
- whether the answer is indexed, partial, researched, blocked, or insufficiently supported.

No model-memory assertion may be styled as evidence.

## UX rules

1. Do not turn `0 indexed results` into a dead-end message while bounded research is still eligible to run.
2. Do not render raw provider candidates or merely acquired Papers as answer evidence.
3. Do not hide provider, acquisition, extraction, or release-gate failures.
4. Keep deterministic retrieval visible if AI synthesis fails.
5. Keep the final citation path inspectable to source/evidence details.
6. Label a run `researched_answer` only when AI says reretrieved grounded evidence was actually used.
7. Label `insufficient_evidence` after the bounded research path has genuinely been evaluated, not immediately after an indexed miss.

## Configuration

General Question v1 uses:

- `KE_WEB_FEDERATED_DISCOVERY_LEDGER_ROOT`
- `KE_WEB_FEDERATED_OPENALEX_API_KEY`
- `KE_WEB_FEDERATED_SEMANTIC_SCHOLAR_API_KEY`
- `KE_WEB_RESEARCH_PAPERS_DIR`
- `KE_WEB_KE_EXECUTABLE`
- `KE_WEB_LLM_MODEL`
- writable `KE_WEB_EVIDENCE_RECORDS_PATH` for durable grounded promotion
- AI request timeout/rate/concurrency settings
- persistent session and discovery-ledger storage settings

On Render, acquired papers are placed under `/var/data/research_papers` so reusable full text survives redeploys when the persistent disk is actually provisioned.

The autonomous AI research path remains bounded even though the person-invoked discovery UI has separate limits.

## Build slices

### WEB-GQR-0 - Connect discovery policy
- [x] pass bounded `FederatedDiscoveryPolicy` into Web Research Copilot runs;
- [x] forward existing ledger/provider configuration;
- [x] add regression test with a non-GLP-1 question;
- [x] CI verification and merge.

### WEB-GQR-1 - Render research state
- [x] accept stable AI research-state metadata;
- [x] add state-specific visitor messaging;
- [x] never infer state solely from narrative text.

### WEB-GQR-1B - Execute grounded completion from Research mode
- [x] enable acquisition planning in Web's bounded AI discovery policy;
- [x] supply `GroundedCompletionPolicy` with the same discovery ledger;
- [x] configure a reusable acquired-paper directory;
- [x] require writable evidence storage before advertising full Research mode;
- [x] surface researched-vs-indexed answer provenance and promoted-record counts;
- [x] preserve the post-run durable ResearchSession trace, including grounded acquisition, extraction, and re-retrieval events produced by AI;
- [x] pin AI's grounded-completion + ResearchState v2 contract.

### WEB-GQR-2 - Coverage panel
- [x] show provider attempts/outcomes;
- [x] show candidate/acquisition totals separately from Evidence Record totals;
- [x] show truncation/budget exhaustion (grounded-completion/route skip and error reasons);
- [x] show freshness/research-run identity (search run ID, timestamp, completeness).

Implemented as a new `research_coverage_presentation.py` module (mirroring
`discovery_presentation.py`'s presentation-only, Protocol-typed contract) and a
"Research coverage" `<details>` section on `/ask`, reusing the existing
`/discover` provider-badge markup/CSS so no new presentation format was
invented. Reports the full acquisition/extraction funnel (discovered
candidates -> acquisition routes persisted/reused -> drafted -> classified ->
staged -> grounded -> promoted) as independent counts rather than one
collapsed number, so BT-2's conversion-funnel loss stays visible. One field
from AI's `AcquisitionRouteResult` (a route-level `skipped_reason`) exists on
AI's current main but not yet on the commit Web has pinned here, so it was
left out of this slice rather than bumping the pin as an unrelated change;
picking it up is a small follow-up once Web's pin is next bumped for another
reason.

### WEB-GQR-3 - Evidence provenance
- [x] distinguish `indexed_before_run` and `acquired_during_run` evidence at individual citation level;
- [x] preserve source links/evidence detail navigation;
- [x] label unsupported domain confidence profiles as unavailable.

Implemented in `knowledge_engine_web/main.py`'s `_citation_entries_for_session_report()`,
consumed by `ask.html`'s "Resolved citations" section. Provenance is derived from
`GroundedCompletionResult.promoted_record_ids` (already computed by AI's GQR-4/5
grounded completion, reaching Web unused) -- a citation is `acquired_during_run`
exactly when its `evidence_record_id` was promoted during this session's grounded
completion, `indexed_before_run` otherwise. Each citation now links to
`/claims/{evidence_record_id}` (evidence detail navigation) and, when
`SourcedClaim.paper_source_url` is set, a "Source" link -- that field already
existed on AI's `SourcedClaim` (AI-O7) but reached no Web template before this.
Confidence scoring reuses the exact same `_compute_evidence_intelligence()` this
page already runs for stored evidence, keyed off whether a graph claim exists for
that evidence record (this project's only scored assessment profile is
`CLINICAL_MEDICINE_V1`); when none exists, the citation says so explicitly
("Confidence scoring unavailable: no relationship data is recorded for this
evidence record") rather than fabricating or omitting a number.

### WEB-GQR-4 - Long-running research UX
Move the UI to a durable job/session polling model rather than extending HTTP request timeouts indefinitely. Session identity and live stage progress must survive refresh/redeploy where persistent storage is configured.

**First slice landed (this session):** the durable storage this milestone needs already
existed and did not need to be rebuilt. `knowledge-engine-ai`'s `SessionRepository`
(used by `ai_orchestration.run_ai_orchestration` since AI-O13/AI-O14) already persists a
`ResearchSession` header plus one `ResearchEvent` row per completed workflow step to
`Settings.session_db_path`, committing each row as the still-synchronous
`/ask?synthesize=1` request executes -- a real SQLite file, already covered by the
existing `session_storage_mode`/`session_persistent_root` local/persistent split that
lets it survive a Render redeploy. This session added a strictly read-only projection of
that same store (`knowledge_engine_web/research_session_status.py`, opened `mode=ro`) and
a new `GET /ask/session/{session_id}` route that returns a small JSON payload (session id,
question, status, a human-readable `last_completed_stage` derived from the latest durably
recorded *completed* `workflow_node` using the exact stage vocabulary in "Recommended
visitor-facing progression" above -- never presented as a live in-progress stage, since
only completions are durably recorded -- `terminal`, timestamps, and event count). Unknown session id, or no
session store yet, both 404. Live-verified against a real `uvicorn` process, not just
unit tests: seeded a session through the real `SessionRepository`, read it back over HTTP
from that running process, then killed the process and started an entirely new one
against the same on-disk file to confirm the state survives a process restart the way a
redeploy would see it.

**What this slice does not do yet:** `/ask`'s existing synchronous request/response shape
is completely unchanged -- the whole research run still happens inline within one HTTP
request, so there is nothing to poll *during* that request yet, only afterward (or after a
redeploy, for a session recorded before it). No frontend JavaScript polls this endpoint.
No background-task execution model exists; `/ask?synthesize=1` still blocks until the run
finishes. The `researching` state's live, event-by-event streaming described above is
still not implemented. This slice is the durable-identity/read-side foundation those later
slices need, not the complete durable job/session polling model.

### WEB-GQR-5 - Failure drills
Test and render:
- provider rate limit;
- one provider unavailable;
- all providers unavailable;
- source inaccessible/license unavailable;
- extraction produces no grounded Evidence Record;
- local LLM unavailable;
- overall budget exhausted;
- Core retrieval failure.

## Acceptance test

A visitor asks `Does creatine supplementation improve maximal strength?` on a deployment whose local evidence does not cover creatine. The page first checks indexed evidence, then broadens the search when the deterministic gap trigger fires. The same session can proceed through acquisition, grounded extraction/promotion, original-question re-retrieval, and a verified cited answer. If the research path completes without enough grounded evidence, the state is `insufficient_evidence` rather than a fabricated response. If newly grounded evidence actually supports the released answer, the state is `researched_answer` and the page says the answer came from post-research re-retrieval.

## Definition of done

Web's synchronous GQR path is complete when arbitrary questions can transparently move from indexed lookup through bounded grounded research to a verified final answer in one durable session. Live event-by-event progress streaming, richer coverage/funnel panels, and individual citation old-vs-new provenance remain subsequent Web slices.
