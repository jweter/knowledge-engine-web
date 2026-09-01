# Research Report v1 — Web Experience Contract

Status: active roadmap contract  
Date: 2026-08-31  
Parent product contract: `knowledge-engine-core/docs/roadmap/research_report_v1.md`

## Goal

The Ask page must make a Knowledge Engine research result **immediately understandable without hiding the evidence machinery that makes it trustworthy**.

The product target is:

> A researcher gets the answer quickly, then can inspect exactly how the answer was built.

The Web layer must not force a choice between readability and auditability.

## Two-layer presentation

### Layer 1 — Answer first

Default view should prioritize:

1. **Bottom line** — direct answer in concise prose.
2. **Conclusion matrix** — major sub-questions, conclusion, and certainty.
3. **Evidence-weighted explanation** — readable narrative tied to citations.
4. **Missing evidence / key limitation** — visible without expanding a diagnostics panel.
5. **Practical interpretation** — only when supported by the report contract.

Pipeline internals must not crowd out the answer.

### Layer 2 — Evidence and methodology

An expandable or secondary view should expose:

- claim-to-source citations;
- EvidenceRecord provenance;
- indexed-before-run vs acquired-during-run evidence;
- direct vs indirect evidence;
- supporting vs null/contradictory evidence;
- population, exposure/intervention, dose, duration, comparator, measurement method, effect size, confidence interval, study design, and limitations where available;
- provider coverage and degraded providers;
- acquisition/extraction funnel and failure reasons;
- missing direct evidence;
- certainty rationale;
- durable research-session identity and research state.

This layer is not a debug console. It is the researcher's audit trail.

Implementation status: the Web renderer now has an expandable Layer-2 audit surface driven only by the existing structured `ResearchReport` contract. It exposes conclusion-level supporting and null/contradictory EvidenceRecord IDs, directness, direct/indirect summaries, indexed-vs-new provenance, provider coverage/degradation/status, limitations/missing evidence, and durable session/state identity. Each EvidenceRecord ID in conclusion relationships and provenance lists now links to Web's existing authoritative `/claims/{evidence_record_id}` detail route, where the stored evidence record, paper citation, DOI/source navigation, concepts, relationship edges, and deterministic Evidence Intelligence can be inspected without fabricating source metadata in the report renderer. Richer inline study-detail composition remains follow-up work where the authoritative detail surface lacks a requested study attribute.

## Progressive research behavior

Long research runs must remain useful while work continues.

Required behavior:

- show the first deterministic state immediately;
- never turn an initial indexed miss into a final `no papers found` outcome while bounded research is still eligible;
- show durable completed stages without inventing a percent complete;
- render a bounded partial answer when validated evidence already supports one;
- preserve the same session identity as research deepens;
- make provider degradation and incomplete coverage visible without blanking the whole answer when usable grounded evidence exists;
- replace the running view with the verified final report only after AI's release gates pass.

## Monster Energy acceptance case

The deployed Ask page must pass the `monster-energy-bp-one-year` golden case.

The Layer-1 answer must make these distinctions visible without requiring the user to open methodology:

- acute post-consumption BP effect;
- chronic/baseline BP evidence;
- incident hypertension evidence;
- measurement artifact from recent caffeine;
- Zero Ultra vs Original Monster;
- whether direct approximately one-year evidence was found;
- certainty for each conclusion.

The Layer-2 view must make visible:

- direct Monster vs broader energy-drink vs caffeine/coffee/soda evidence;
- positive and null/counter-evidence;
- source-level study details and limitations;
- provider coverage/degradation;
- newly acquired vs previously indexed evidence;
- missing-evidence disclosure.

## UX acceptance criteria

Research Report v1 fails if:

1. the user must inspect pipeline details before learning the answer;
2. the primary answer is materially harder to understand than a strong scholarly-assistant baseline;
3. acute/chronic/incident-hypertension conclusions are visually collapsed;
4. certainty is shown without the reason being inspectable;
5. citations do not resolve to source/evidence detail;
6. direct and indirect evidence are visually indistinguishable;
7. a missing one-year direct study is buried or omitted;
8. null/contradictory evidence is not accessible;
9. research progress implies a stage succeeded before durable AI/Core state says it did;
10. provider or extraction degradation that changes interpretation is hidden.

## Roadmap priority

Until the Monster benchmark passes on the deployed Ask path, prioritize:

1. render AI's structured Research Report contract;
2. answer-first Layer-1 composition;
3. conclusion/certainty matrix;
4. evidence/methodology Layer-2 inspection;
5. source-level directness and counter-evidence presentation;
6. durable long-running session/polling experience;
7. end-to-end Monster acceptance run;
8. cross-domain golden cases and polish.

Decorative UI work should not outrank these requirements.

## Related work

- #86 — General Question Research Loop v1 research-state UI and provenance
- #93 — progressive research UX
- `docs/general_question_research_loop_v1.md`
- `docs/federated_discovery_transparency_roadmap.md`
