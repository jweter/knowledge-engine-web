# General Question Research Loop v1 - Web responsibilities

Status: active cross-repository build plan  
Tracking issue: #86  
Parent AI tracking issue: `knowledge-engine-ai` #69

## Purpose

The Ask experience must behave like a research tool, not a fixed-corpus demo. A question outside the indexed evidence base should visibly enter a bounded research workflow when Research Copilot is available.

The Web layer does not decide scientific truth. It invokes the AI orchestration path safely and renders the resulting research state, evidence provenance, search coverage, and limitations.

## Immediate change in this branch

Research Copilot now receives the AI layer's bounded `FederatedDiscoveryPolicy` by default from the Web orchestration bridge. This means:

1. indexed evidence is still searched first;
2. when the AI layer's deterministic coverage-gap rule fires, Core federated discovery is attempted;
3. provider credentials and the durable discovery-ledger path come from existing Web settings;
4. discovered candidates are still leads only and are not presented as citable Evidence Records.

WEB-GQR-1 now also consumes `knowledge-engine-ai`'s stable `derive_research_state` contract and renders that metadata directly on `/ask`. Web does not recreate or infer the state from answer prose. The AI dependency is pinned to the merged contract commit, and `poetry.lock` is regenerated from that dependency declaration.

This closes the current Web-to-AI discovery and research-state wiring gaps, but it does not complete arbitrary-question answering. Core's acquisition/extraction bridge and AI re-retrieval are still required before newly discovered literature can become grounded answer evidence.

## Required user-visible states

The Web contract renders stable research states from AI rather than inferring them from prose:

- `indexed_answer`
- `research_required`
- `researching`
- `partial_answer`
- `insufficient_evidence`
- `provider_degraded`
- `blocked`

`researching` is part of the stable schema and already has visitor-facing copy, but the current Research Copilot request is synchronous, so AI does not emit that state yet. It is reserved for the later durable/polling workflow.

Recommended visitor-facing progression:

```text
Searching indexed evidence...
Indexed evidence is thin; expanding the literature search...
Searching scholarly providers...
Validating and acquiring eligible sources...
Extracting grounded evidence...
Re-checking the original question against the enlarged evidence base...
Preparing a source-grounded answer...
```

Do not display a stage that Core/AI has not actually entered.

## Final answer requirements

Every completed Research Copilot result should make these distinctions explicit:

- evidence that was already indexed before this question;
- evidence newly acquired during this research run;
- providers searched and providers degraded/unavailable;
- incomplete coverage;
- domain-specific assessment profile availability;
- citations and Evidence Record provenance;
- whether the answer is complete, partial, or insufficiently supported.

No model-memory assertion may be styled as evidence.

## UX rules

1. Do not turn `0 indexed results` into a dead-end message when bounded discovery is available.
2. Do not say `searching the literature` before the AI layer has actually triggered discovery.
3. Do not render raw provider candidates as if they support the answer.
4. Do not hide provider failures.
5. Do not hide that domain-specific confidence scoring is unavailable.
6. Keep deterministic retrieval visible if AI synthesis fails.
7. Keep the final citation path inspectable to source/evidence details.

## Configuration

General Question v1 reuses existing settings:

- `KE_WEB_FEDERATED_DISCOVERY_LEDGER_ROOT`
- `KE_WEB_FEDERATED_OPENALEX_API_KEY`
- `KE_WEB_FEDERATED_SEMANTIC_SCHOLAR_API_KEY`
- `KE_WEB_KE_EXECUTABLE`
- AI request timeout/rate/concurrency settings
- persistent session and discovery-ledger storage settings

The autonomous AI research path must remain bounded even though the person-invoked discovery UI may have separate limits.

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

Verification completed on the PR branch before final CI: the repository's full `scripts/quality_preflight.py` gate passed after repairing the existing Ask test fixture for the new state contract, and a local `uvicorn` server successfully served an `/ask` request for a non-GLP-1 question. Fresh PR-triggered Quality and Docker checks on the exact final head remain the merge authority.

### WEB-GQR-2 - Coverage panel
- show provider attempts/outcomes;
- show candidate/acquisition totals separately from Evidence Record totals;
- show truncation/budget exhaustion;
- show freshness/research-run identity.

### WEB-GQR-3 - Evidence provenance
- distinguish `indexed_before_run` and `acquired_during_run` evidence;
- preserve source links/evidence detail navigation;
- label unsupported domain confidence profiles as unavailable.

### WEB-GQR-4 - Long-running research UX
Once Core acquisition can exceed a synchronous request safely, move the UI to a durable job/session polling model rather than extending HTTP request timeouts indefinitely. Session identity and progress must survive refresh/redeploy where persistent storage is configured.

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

A visitor asks `Does creatine supplementation improve maximal strength?` on a deployment whose local evidence does not cover creatine. The page first checks indexed evidence, then visibly broadens the search when the deterministic gap trigger fires. Once Core acquisition/re-retrieval is implemented, the same session progresses to newly acquired validated evidence and a cited answer. If the research cannot acquire enough grounded evidence, the page reports that outcome rather than fabricating a response.

## Definition of done

Web's portion is complete when arbitrary questions have a transparent, durable research-state experience from indexed lookup through bounded research and final grounded answer, with provider coverage and evidence provenance visible throughout.
