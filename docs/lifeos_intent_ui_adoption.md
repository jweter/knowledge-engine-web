# LifeOS-Inspired Intent and Verification UX for Knowledge Engine Web

**Status:** accepted UI architecture direction  
**Scope:** `knowledge-engine-web`  
**Source:** *LifeOS Engineering Teardown for an Ollama and Knowledge Engine Stack* (August 2026)

## Decision

The web application should make Knowledge Engine's research process **inspectable as movement from a current state to a verified ideal state**.

The UI must not expose LifeOS product concepts as branding or require LifeOS itself. It should translate the useful primitives into research-native user experience.

## User-facing model

For every durable research session, the UI should be able to show:

```text
Research question
    |
    v
Current state
    |
    v
Research plan
    |
    v
Definition of done / Research ISA
    |
    v
Evidence gathering + analysis
    |
    v
Verification probes
    |
    +--> unresolved -> next work
    |
    +--> satisfied -> verified synthesis
```

The user should never have to infer whether the system is "done" from fluent prose alone.

## UI concepts to add

### 1. Research Goal panel

Display the project/run objective in plain language:

- original question;
- normalized question where applicable;
- current scope;
- important constraints;
- evidence cutoff time;
- privacy/cloud policy summary.

This is the research-native equivalent of a task intent layer.

### 2. Definition of Done panel

Expose Research ISA criteria as explicit checks.

Example:

```text
Definition of Done
[PASS] Every material claim has a source link
[PASS] Citation integrity verified
[PASS] Contradictory evidence reviewed
[BLOCKED] Long-term follow-up coverage incomplete
[PASS] Uncertainty and known gaps disclosed
```

Each row should be expandable to show:

- criterion text;
- probe name;
- status;
- evidence/details supporting the status;
- timestamp;
- relevant source or workflow links.

### 3. Current State / Remaining Gaps

The session page should distinguish:

- what is currently known;
- what remains unknown;
- blocked work;
- evidence coverage limitations;
- unresolved contradictions;
- tasks awaiting user approval.

This prevents a polished synthesis from visually overpowering missing evidence.

### 4. Provenance-first synthesis

Every material scientific assertion in generated synthesis should remain inspectable back to source-linked evidence.

The UI should preserve distinctions among:

- primary evidence;
- secondary evidence;
- reference/background knowledge;
- deterministic calculation;
- model-generated inference/explanation;
- speculative hypothesis.

These categories must not collapse into one undifferentiated "AI answer."

### 5. Capability status

Add a compact diagnostics surface for features that affect user expectations.

Example:

```text
Local reasoner: verified
Structured output: verified
Semantic index: verified
PubMed discovery: degraded
Cloud reasoner: disabled
Statistics worker: verified
```

Use the four shared states:

- verified;
- degraded;
- unavailable;
- disabled.

Do not present an intentionally disabled provider as an application failure.

### 6. Privacy and model routing transparency

When synthesis uses a model, expose enough provenance for a technically literate user to inspect the route without cluttering the default view.

Recommended details in an expandable execution trace:

- provider role (`local_fast`, `local_reasoner`, `high_reasoning`, etc.);
- actual model/provider when available;
- whether cloud egress occurred;
- data classification used by policy;
- prompt/workflow version;
- generation timestamp;
- relevant source IDs;
- verification status.

The UI should never imply that "local-first" means "local-only."

### 7. Evidence ingestion visibility

The web layer should reflect the **journal-before-grade** invariant:

```text
Captured -> Parsed -> Normalized -> Extracted -> Reviewed -> Corpus eligible
```

A failed or held stage should not make the source disappear from the user's history. A source may be visible as captured but not yet eligible for synthesis.

### 8. Human approval for consequential actions

When a task crosses into consequential mutation or external action, surface an explicit approval state instead of letting the agent act silently.

Examples:

- canonical evidence mutation;
- project-level policy change;
- external publication/submission;
- destructive deletion;
- sending sensitive data to a cloud provider when policy requires confirmation.

## Recommended session page structure

```text
-------------------------------------------------
Question / Scope / Status
-------------------------------------------------
Current State
  known | unknown | coverage | blockers
-------------------------------------------------
Research Plan
  tasks + dependencies + progress
-------------------------------------------------
Definition of Done
  ISA criteria + probe states
-------------------------------------------------
Evidence
  sources + classifications + lifecycle state
-------------------------------------------------
Analysis
  comparisons + deterministic statistics + contradictions
-------------------------------------------------
Verified Synthesis
  claim-linked narrative
-------------------------------------------------
Execution / Provenance
  model route + tools + versions + events
-------------------------------------------------
```

The default view should remain readable for ordinary researchers. Deep provenance belongs behind expandable details rather than being removed.

## What Web should not do

- compute scientific confidence independently of core;
- infer verification status from prose;
- hide blocked criteria to make a session appear complete;
- merge reference knowledge and evidence visually;
- treat an LLM's self-reported certainty as a verified state;
- expose credentials or sensitive prompt context;
- require LifeOS runtime concepts in user-facing navigation;
- make model/provider names the primary mental model for research tasks.

## Cross-repository contract

`knowledge-engine-ai` should return typed session/ISA/probe/model-provenance data. `knowledge-engine-core` should return evidence, relationship, lifecycle, calculation, and provenance facts. Web composes those into an inspectable research experience without becoming the authority for either layer.

## Near-term implementation sequence

1. Add read-only UI models for Research ISA criteria and probe results when the AI API exposes them.
2. Add a Definition of Done panel to the durable research-session view.
3. Add explicit unresolved-gap and coverage sections.
4. Add a compact capability/diagnostics view.
5. Add expandable execution provenance, including local/cloud route disclosure.
6. Add ingestion lifecycle visibility for captured-but-not-yet-eligible evidence.
7. Add approval UX only when corresponding policy-gated actions exist in the backend.

## UX invariant

> The interface should make it obvious what the system knows, what it does not know, what evidence supports the answer, and what still has to become true before the research task is actually complete.
