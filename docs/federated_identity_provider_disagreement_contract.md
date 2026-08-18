# Federated work identity and provider-disagreement contract

Status: implementation contract for WEB-FRD-3.

## Purpose

Knowledge Engine Core now exposes provider-metadata disagreement in the public federated discovery snapshot. The next Web slice must consume that information without turning metadata disagreement into scientific disagreement and without treating any scholarly provider as authoritative.

This document fixes the cross-repository contract before UI implementation so Core, AI, and Web can evolve independently without silently changing meaning.

## Architectural boundary

Web consumes only the public, JSON-ready federated discovery snapshot that crosses the documented Core -> AI -> Web boundary. Web must not read Core's search-run ledger directly, import Core as a Python package, inspect provider-native raw responses, or reconstruct provider disagreement from result counts or presentation fields.

AI may parse and type the public snapshot, but it must not re-decide identity, select a preferred provider value, or collapse disagreement into a confidence score. Core remains the deterministic source of identity/deduplication and provider-disagreement facts.

## Canonical work identity

A result card represents one Core-deduplicated candidate, not one provider response.

Web should use Core's canonical candidate identity and display only useful public identifiers when present:

- DOI;
- PMID;
- arXiv identifier;
- provider-native identifiers only when they help a user inspect provenance.

Provider observations must never create duplicate paper cards for the same Core candidate.

## Provider badges

A card may show compact provider badges such as PubMed, Crossref, OpenAlex, Semantic Scholar, and arXiv.

The meaning is strictly:

> This provider contributed an observation to this deduplicated work.

Multiple badges do not mean stronger evidence, higher confidence, more citations, or independent replication. The UI must include accessible text conveying the same meaning; color alone is insufficient.

## Metadata disagreement

Core's public `provider_disagreements` payload is descriptive metadata-quality state. Web may expose it in an expandable "Provider metadata differs" section on the corresponding work.

Examples include conflicting provider observations for:

- title;
- publication year/date;
- open-access status;
- retraction/correction metadata;
- citation counts;
- other provider-supplied bibliographic fields Core explicitly reports.

Web must preserve all reported observations. It must not pick a winner, average values, hide minority values, or label one provider correct unless Core later exposes a separately reviewed canonical decision.

## Scientific disagreement is separate

Provider metadata disagreement must never share the same label, iconography, severity category, or confidence semantics as evidence relationships such as `supports`, `contradicts`, or `qualifies`.

A Crossref/OpenAlex publication-year mismatch says nothing about whether two studies disagree scientifically. Likewise, agreement among five metadata providers says nothing about evidence quality.

## Degraded and incomplete data

Absence of a disagreement record means only that Core did not report a disagreement for that candidate in that run. Web must not translate absence into "verified", "confirmed", or "all providers agree" unless the public contract explicitly says that every relevant field was compared.

Unknown, unavailable, and not-observed values should remain distinguishable from explicit agreement.

## Privacy and security

The Web-facing contract must not expose:

- provider credentials or API keys;
- local filesystem paths;
- transport/debug state;
- provider-native raw responses;
- internal `initiated_by`, project IDs, or research-question IDs unless a future reviewed public contract explicitly adds them;
- hidden scoring or ranking internals.

Provider identifiers and public bibliographic fields are provenance, not secrets.

## WEB-FRD-3 implementation slices

### Slice A — AI contract widening

Extend `knowledge-engine-ai`'s federated discovery parser to carry the public Core fields needed by Web:

- canonical candidate ID;
- public work identifiers;
- provider observation/provider badge set;
- provider-disagreement records;
- existing coverage/search-run provenance unchanged.

Parsing must fail clearly on malformed required fields and must not guess missing values.

### Slice B — Web presentation model

Map the typed AI result into a small Web presentation object. Keep this mapping deterministic and free of provider preference logic.

### Slice C — `/discover` rendering

Render one card per canonical candidate with:

- title and useful canonical identifiers;
- provider badges;
- an expandable provider-disagreement section when Core reports conflicts;
- explicit wording that disagreement is bibliographic/provider metadata, not scientific contradiction.

### Slice D — regression coverage

Fixtures/tests must cover:

1. one provider observation;
2. multiple providers agreeing on displayed metadata;
3. multiple providers with a reported metadata disagreement;
4. missing/unknown provider fields;
5. one canonical candidate with multiple observations but only one rendered card;
6. accessible non-color text for provider provenance and disagreement;
7. no leakage of private/internal Core fields.

## Exit criteria for WEB-FRD-3

WEB-FRD-3 is complete only when:

- DOI/PMID/arXiv/provider identifiers are displayed only where useful;
- multiple provider observations do not duplicate the same paper card;
- provider disagreement is inspectable without being confused with scientific contradiction;
- no provider is presented as authoritative merely because its value was selected for display;
- privacy exclusions remain intact across Core -> AI -> Web;
- tests exercise disagreement, no-disagreement, and multi-provider deduplication states.

## Relationship to the roadmap

This contract implements the intent of `docs/federated_discovery_transparency_roadmap.md` WEB-FRD-3 and builds directly on Core's completed public federated snapshot and provider-disagreement work. It intentionally does not start WEB-FRD-4 publication-status policy, WEB-FRD-5 freshness comparison, or WEB-FRD-6 research-path UI.

The immediate next code slice should be AI contract widening, because Web should not parse Core's raw JSON ad hoc or read Core internals directly.
