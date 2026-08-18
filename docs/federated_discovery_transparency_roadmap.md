# Federated Discovery Transparency Roadmap

Status: adopted Web-layer direction, 2026-08-15.

This document translates the useful lessons from the review of
`surendranb/find-research-papers-mcp` into Knowledge Engine Web behavior. The
external MCP server is not a Web dependency. Web consumes Knowledge Engine's own
Core/AI contracts and makes their discovery provenance understandable to users.

The matching Core and AI plans are:

- `knowledge-engine-core/docs/roadmap/federated_research_discovery_adoption.md`
- `knowledge-engine-ai/docs/roadmap/federated_discovery_orchestration_adoption.md`

## Product principle

The future Ask experience should not only show *what evidence was found*. It
should also make it possible to understand *how broadly the system looked, what
failed, and how current that search is*.

A polished answer must never visually imply complete literature coverage when
one or more required providers were unavailable or when the search was
intentionally narrow.

## What Web should eventually render

### Discovery coverage summary

For each Research Session or answer, when Core exposes the data:

```text
Discovery coverage
PubMed              searched
Crossref            searched
OpenAlex            searched
Semantic Scholar    rate limited
arXiv               not relevant to this query
Citation expansion  completed, depth 1
Last search          2026-08-15 11:22 UTC
Overall run          degraded / partial
```

The UI must use deterministic statuses supplied by Core. It must not infer
provider success from the existence of results.

### Search-method disclosure

A compact expandable section should eventually show:

- providers requested;
- providers completed;
- providers skipped/failed and why;
- major query filters/date bounds;
- whether citation/reference expansion ran;
- whether a contradiction-oriented search ran;
- whether correction/retraction checks ran;
- search run time and revision ID;
- count of provider results before and after identity deduplication.

This is provenance, not marketing analytics.

### Provider identity without provider authority

Paper cards may display source/provider badges such as PubMed, Crossref,
OpenAlex, Semantic Scholar, or arXiv when useful for provenance. Multiple badges
mean multiple provider observations of the same work; they do not mean the
scientific claim is stronger.

Citation counts, provider-generated TLDRs, popularity, or provider rank must not
be presented as evidence quality.

### Preprint and publication-version state

When Core has linked a preprint and later journal version, Web should make that
relationship visible rather than silently replacing one with the other.

At minimum:

- preprint status is explicit;
- journal version is explicit;
- version link/provenance is visible;
- evidence views default to the version actually used by the Evidence Record.

### Retraction/correction visibility

Retraction or correction status should be impossible to miss on a work being
used as evidence.

The UI should distinguish:

- retracted;
- corrected;
- expression of concern;
- withdrawn;
- status unknown/not checked;
- landing-page resolution failure versus publication validity.

Web does not decide the consequence. Core/AI policy does. Web presents the
recorded state and resulting synthesis limitation.

## Degraded mode is a first-class user experience

Knowledge Engine already preserves deterministic retrieval when optional AI is
unavailable. Federated discovery extends the same principle to scholarly
providers.

A partial search should still be useful:

```text
We found 18 relevant works from PubMed, Crossref, and OpenAlex.
Semantic Scholar could not be searched because it was rate-limited.
This answer is therefore based on a degraded discovery run.
```

The exact wording may evolve, but the behavior may not:

- keep valid results;
- expose missing capability;
- do not convert technical failure into apparent scientific completeness;
- do not hide the evidence merely because one optional provider failed.

## Search freshness and "what changed"

The existing Web direction already includes snapshot revision and what-changed
visibility. Federated discovery should eventually extend this to research
questions themselves.

For a previously run question, Web should be able to show:

- last literature search date;
- newly discovered works since the previous run;
- newly available full text;
- newly discovered citation/reference links;
- corrections/retractions since the previous run;
- whether the evidence-map conclusion changed;
- whether provider coverage changed because a provider was newly added or was
  unavailable in one run.

This makes "knowledge is never final" visible in the product rather than merely a
project principle.

## Research path UI

A future Research Session should be inspectable as a sequence rather than only a
final paragraph:

```text
Question
  -> research scope / ISA
  -> federated discovery
  -> citation expansion
  -> evidence selection
  -> contradiction/counter-search
  -> analytical checks
  -> synthesis
  -> close-gate result
```

Users should be able to open the path and inspect the evidence/run artifacts
behind any stage without needing to understand internal implementation details.

This is particularly important for expert/scientific use, where trust often
depends on seeing *how* the answer was assembled.

## Progressive disclosure

The interface should serve both ordinary users and expert reviewers.

Default answer view:

- concise answer;
- confidence/uncertainty summary;
- key citations;
- clear degraded/partial-search warning when applicable;
- last-updated/search timestamp.

Expandable expert view:

- provider coverage;
- search strategy;
- identity/provider observations;
- evidence records;
- source locators;
- contradiction/qualification evidence;
- deterministic analytical checks;
- Research ISA close-gate criteria;
- exact limitations.

The product should not force every visitor to read an audit log, but it should
never make the audit trail inaccessible.

## No third-party telemetry inheritance

The reviewed external MCP includes default anonymous usage telemetry and a
remote convenience installer. None of that belongs in the Web product because
we studied the repository.

Web rules remain:

- external analytics are never introduced merely because an upstream provider
  uses them;
- scientific queries and research-session behavior are not sent to a third-party
  analytics endpoint by default;
- any future analytics feature must be independently justified, privacy-reviewed,
  and clearly separated from scientific functionality;
- provider calls required to execute the user's research are different from
  product telemetry and must not be conflated.

## Roadmap additions

### WEB-FRD-1 -- Provider coverage component

After Core exposes a stable search-run contract, render provider status on local
Research Sessions.

Exit criteria:

- fixture covers success, rate-limited, unavailable, disabled, and not-relevant;
- UI never infers status from result count;
- partial/degraded state is visible in both accessible text and visual treatment.

**Status: complete.** Core's search-run contract landed via
`ke federated-discover` (FRD-1/FRD-2/FRD-3) and `knowledge-engine-ai`'s
`ke_client.federated_discover()`. Implemented as a new `/discover` page
(`knowledge_engine_web/discovery_orchestration.py`, `templates/discover.html`)
-- separate and opt-in from `/ask`, not a change to Ask's cost/latency
profile. See `docs/web_design.md`'s "WEB-FRD-1 provider coverage" section for
the full account. This is one Research Session type's coverage view, not yet
wired into a saved/durable Research Session record (that link is future work
alongside WEB-FRD-2 through WEB-FRD-6, all still not started).

### WEB-FRD-2 -- Search provenance details

Add expandable search-method details and revision timestamps.

Exit criteria:

- provider list and statuses;
- filters/time bounds;
- search run ID/revision;
- citation-expansion and contradiction-search flags;
- no secrets, local paths, or internal configuration leakage.

### WEB-FRD-3 -- Work identity/provider observations

Render canonical work identity with optional provider aliases/badges.

Exit criteria:

- DOI/PMID/arXiv/provider identifiers are displayed only where useful;
- multiple provider observations do not duplicate the same paper card;
- provider disagreement can be inspected without confusing it with scientific
  contradiction.

### WEB-FRD-4 -- Publication-status warnings

Render preprint, correction, retraction, expression-of-concern, and withdrawal
state from Core data.

Exit criteria:

- retraction cannot be visually missed;
- unknown/not-checked remains distinct from clear;
- landing-page resolution failure is not labeled a retraction or invalid paper.

### WEB-FRD-5 -- Research freshness history

Compare current and previous discovery runs for the same Research Session or
tracked question.

Exit criteria:

- newly discovered works are visible;
- new corrections/retractions are highlighted;
- provider-coverage changes are shown;
- old synthesis is versioned rather than silently rewritten.

### WEB-FRD-6 -- Inspectable research path

Expose the sequence of discovery/evidence/analysis/verification artifacts behind
an answer.

Exit criteria:

- final answer remains simple by default;
- expert view can trace any substantive claim to evidence and search context;
- failed close-gate criteria are visible rather than replaced by generic errors.

## Improvements beyond the external reference

### Search-quality UX should distinguish recall from evidence quality

The UI should teach an important distinction:

- broad search coverage improves our chance of *finding* relevant evidence;
- Evidence Intelligence evaluates the *quality and agreement* of the evidence we
  found.

These should be separate displays/signals. A broad search can find weak evidence;
a narrow search can accidentally find one strong study while missing important
contradictions.

### Provider disagreement should be a metadata inspection feature

If OpenAlex and Crossref disagree on a publication date, open-access state, or
citation count, the UI can eventually show that as a metadata discrepancy. It
must not appear in the same visual category as studies disagreeing on a
scientific outcome.

### Coverage limitations should travel with exports

Downloaded Markdown/JSON reports should carry the same provider/search coverage
limitations shown in the browser. Exporting an answer must not strip away the
fact that the underlying search was degraded.

### User-controlled source scope

Advanced users may eventually choose a deliberately narrow source scope (for
example, PubMed only). The UI should make that choice explicit and preserve it in
the Research Session. A user-selected narrow scope is not an error, but it is
still a scope limitation.

### Accessibility is part of scientific transparency

Provider status, warnings, confidence, and retraction state must never depend on
color alone. All critical provenance and degraded-mode information needs text and
semantic markup so it survives screen readers, exports, printing, and future UI
redesigns.

## Product vision

The eventual Web product should make a Knowledge Engine answer feel less like a
chatbot response and more like an inspectable scientific instrument:

- ask naturally;
- see the answer quickly;
- know how current and broad the search was;
- see uncertainty and contradictions;
- inspect exactly where claims came from;
- understand what failed or remains unknown;
- return later and see what changed.

That is how broader scholarly discovery becomes a trust improvement rather than
merely a larger search box.
