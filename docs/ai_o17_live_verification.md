# AI-O17 Live Research Copilot Verification

## Status

AI-O17 is complete for the local composed deployment. It does not enable the
public Render alpha.

On 2026-08-13, the Web, AI, and Core repositories were exercised together with
the committed GLP-1 corpus database, Evidence Records, relationship records,
and a local Ollama `llama3.1:8b` model. The canonical question was:

> Does semaglutide reduce body weight in adults with overweight or obesity?

The successful run completed in 84.140 seconds. Deterministic retrieval and
Evidence Intelligence plus the contradiction branch completed in 10.125
seconds; local synthesis took 71.250 seconds. The Research ISA close gate
passed workflow integrity, citation integrity, and contradiction review. The
released narrative cited all five retrieved evidence records, including the
two qualifying safety and study-design records, and the page retained five
independent deterministic paper results.

## Release Boundary

Web now treats `ResearchQuestionResult.narrative_releaseable` as the sole
presentation boundary for a generated narrative and its resolved citations.
When deterministic verification or the close gate blocks, Web withholds the
draft and leaves deterministic retrieval visible. The durable session remains
available to an operator for inspection.

This is intentionally stricter than checking only whether an LLM returned
text. A generated draft is not a user-facing answer until the independent
workflow, citation, and contradiction gates pass.

## Failure Rehearsals

Two failure modes were exercised against the same composed deployment:

- unavailable Ollama: the request returned sanitized no-narrative output in
  15.125 seconds while deterministic retrieval remained visible;
- forced 0.1-second execution deadline: both workflow branches timed out, the
  workflow-integrity criterion blocked session close, and deterministic
  retrieval remained visible without leaking a traceback or private path.

Admission concurrency and fixed-window rate behavior remain covered by
deterministic Web tests. They were not re-exercised with repeated expensive
model calls because AI-O17 did not change the admission implementation.

## Dependency Contract

Web pins `knowledge-engine-ai` to merged commit
`5e20e9e55015ad784c495bb73001156500609371`. That revision supplies the
explicit narrative release property, qualifier-aware synthesis prompt,
deterministic numeric grounding correction, and workflow-integrity close-gate
criterion used by this rendering boundary.

## Public Deployment Decision

The Render alpha remains retrieval-only. The successful local run proves the
software composition and failure behavior, not the hosted operating
infrastructure. Public Research Copilot enablement still requires:

- a durable Research Session disk;
- the Core runtime and corpus inputs inside the hosted environment; and
- a secured inference service reachable by Render.

A laptop Ollama listener is not an acceptable public inference backend. Until
those prerequisites exist and are rehearsed in the hosted environment, Web
must fail closed and must not expose an enabled Research Copilot control.

## Verification Gate

The Web-side acceptance gate is:

- a blocked narrative is withheld while deterministic retrieval remains;
- the immutable AI dependency contains the release contract;
- the full Web test, Ruff, Black, mypy, dependency, and lock-file checks pass;
- no private path or model output is added to tracked fixtures; and
- the Render blueprint remains retrieval-only.

## Next Handoff

The next hosted step is an operator infrastructure decision, not another
prompt change: provision durable session storage and a secured hosted inference
endpoint, then repeat this exact question and the unavailable/timeout drills in
the real Render environment before enabling the control.
