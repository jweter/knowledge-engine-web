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
- distinguish `indexed_before_run` and `acquired_during_run` evidence at individual citation level;
- preserve source links/evidence detail navigation;
- label unsupported domain confidence profiles as unavailable.

### WEB-GQR-4 - Long-running research UX
Move the UI to a durable job/session polling model rather than extending HTTP request timeouts indefinitely. Session identity and live stage progress must survive refresh/redeploy where persistent storage is configured.

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
