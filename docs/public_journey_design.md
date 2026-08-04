# Public Journey Design

Status: Slice 1 implemented locally for architectural review on 2026-08-03.
The changes remain uncommitted and undeployed.

Delivered in Slice 1:

- stable `/demo` route anchored to the SELECT evidence record;
- visible snapshot identity and graph counts;
- shared stored/computed/reviewed trust language;
- simplified primary navigation and honest retrieval labeling;
- showcase-to-alpha bridge and current-versus-future status labels.

Deferred as designed: retrieval ranking changes, a golden-query benchmark,
additional evidence-map depth, and the persistent-host migration.

## Decision Summary

Knowledge Engine should present one continuous public journey:

```text
Project showcase
  -> stable web-alpha demonstration route
  -> one real GLP-1 claim and its source-linked evidence
  -> limitations, Evidence Intelligence, and reviewed relationships
  -> optional exploration of Ask, the graph, and the repositories
```

The showcase remains the mission-led public front door. The web alpha remains
the working, read-only laboratory. They do not need identical visual systems,
but they must use the same status language, trust boundaries, and project
identity.

The first guided example should use the existing SELECT claim,
`ev-glp1-select-trial-weight-loss-208wk-001`. It is the strongest current
demonstration because it already connects a large randomized trial to an exact
effect estimate, limitations, deterministic Evidence Intelligence, citations,
and five reviewed relationships. The showcase must link to a stable `/demo`
route rather than directly to the claim ID so the web application retains
control over the example as the corpus evolves.

## Evidence From the Current Sites

Audit date: 2026-08-03.

### Showcase

The showcase communicates the mission unusually well. Its strongest elements
are the literal project name, the "Human knowledge should compound" offer,
traceability/uncertainty/human-oversight commitments, and the source-to-
discovery architecture.

The current breaks in the journey are:

- The browser title is `Starter Project`, not `Knowledge Engine`.
- The only destinations are the vision sections and the core GitHub repository.
  There is no route to the working alpha.
- Decorative `claim 0.93` and `evidence 0.78` values have no definition,
  provenance, or live source. They look like scientific scores.
- "Discovery Engine" and "Education Engine" read as present-tense product
  capabilities even though they remain long-term vision.
- There is no bounded example showing what the project can truthfully do now.

### Web alpha

The alpha proves much more than the showcase reveals: real source-linked
Evidence Records, PICO fields, limitations, deterministic Evidence
Intelligence, Relationship Records, reports, and a deployed Ask workflow.

The current breaks are:

- `/` opens the Graph Summary, an operator-oriented inventory rather than a
  visitor journey.
- No page displays when the committed snapshot was generated or which core
  revision it represents.
- The deployed graph reports 154 claims, 11 relationships, and 5 citations,
  while newer core documentation records later relationship work. Nothing on
  the site tells a visitor that the snapshot is older.
- `/about` still says the site adds no confidence rating and calls AI a future
  layer, contradicting shipped deterministic Evidence Intelligence and opt-in
  local synthesis.
- The global footer says "nothing inferred or synthesized" even on a site that
  can expose explicitly requested AI narration. The intended boundary is more
  precise: no evidence, relationships, or scores are invented; narration is
  optional and labeled.
- The Roadmap page's outer disclaimer correctly labels its concept preview,
  but the embedded preview still says no code computes confidence and no live
  search-to-evidence matching exists.
- Claim pages are scientifically rich but lead with machine identifiers.
- Mobile claim reading is usable, but the full navigation wraps into a dense
  multi-line header before the evidence begins.

### Ask

The canonical question "Do GLP-1 receptor agonists reduce body weight in adults
with overweight or obesity?" currently ranks incidental or narrower matches
ahead of the strongest direct evidence. The first results include a menstrual-
function cohort, a ketogenic-diet case series, a reproductive-health review,
and an insulin-resistance comparison. Several have no matching Evidence Record.

This is valuable evidence for Current Project Path goal 2. It is not a reason to
hide Ask, but it is a reason not to make Ask the primary guided demonstration or
describe it as answering the question today.

## Audience

The first journey serves a scientifically curious visitor who has heard the
mission but has not read the architecture documents. They should be able to
answer, within a few minutes:

1. What is Knowledge Engine trying to become?
2. What can it actually do today?
3. Where did this scientific statement come from?
4. What are the study's limitations and scope?
5. Which values are stored, computed, reviewed, or AI-narrated?
6. How current is the displayed data?
7. Where can I inspect the source code?

Operator and reviewer workflows remain available in the existing navigation,
but they are not the first public journey.

## Goals

- Connect the showcase to a stable, real alpha demonstration.
- Give a new visitor one complete path from a research question to source,
  result, limitations, relationships, and citations.
- Make snapshot age and origin visible on every data-bearing page.
- Use one shared vocabulary for stored evidence, deterministic computation,
  human review, and optional AI narration.
- Keep the project ambitious without presenting future engines as shipped.
- Preserve direct access to the alpha's existing expert and operator pages.
- Work cleanly on desktop and mobile.

## Non-Goals

- Improving retrieval ranking; that is Current Project Path goal 2.
- Adding evidence or relationships; that is goal 3.
- Implementing new synthesis, confidence formulas, or statistical analysis.
- Building the persistent host or replacing snapshots.
- Redesigning every alpha page or making the operational UI resemble a
  marketing site.
- Making the alpha an unrestricted production service.
- Hard-coding corpus totals into the showcase.

## Product Roles

### Showcase: public front door

The showcase owns:

- Mission and long-term vision.
- Principles and the source-to-knowledge architecture.
- A concise, truthful "working today" status.
- The primary `Explore live evidence` call to action.
- Links to the alpha and the three repositories.

It does not own corpus counts, evidence rendering, scientific scores, or a copy
of the demonstration data. Those would become stale independently of the
alpha.

### Web alpha: working laboratory

The alpha owns:

- The stable `/demo` route.
- Snapshot provenance and freshness.
- The real Evidence Record, computed intelligence, relationships, and
  citations used by the demonstration.
- Clear navigation into deeper inspection and experimental Ask.
- Honest unavailable states if the selected demonstration record is absent.

### Core and AI repositories

Core remains the canonical source of evidence, graph data, deterministic
intelligence contracts, and the project roadmap. AI remains an optional
consumer for retrieval and grounded narration. Neither repository becomes a
public landing page.

## Canonical Guided Journey

### Step 1: Mission

The showcase hero remains mission-led. Its primary action becomes `Explore live
evidence`; `Read the vision` and `View source` remain secondary actions.

The showcase should say, in plain language:

> See one real scientific claim move from source evidence to an inspectable
> relationship map. This is a working alpha over a point-in-time research
> snapshot, not an automated verdict.

Unexplained `claim 0.93` and `evidence 0.78` decorations should be removed. If
that visual space is retained, use non-numeric commitments such as `source
linked`, `limitations visible`, and `relationships reviewed`.

### Step 2: Stable demonstration route

The showcase links to:

```text
https://knowledge-engine-web-alpha.onrender.com/demo
```

`/demo` is the alpha's visitor-facing home. The bare `/` route should redirect
to `/demo`; `/graph` remains the operational graph summary.

The page headline is the real question:

> Do GLP-1 receptor agonists produce sustained, long-term weight loss in adults
> with overweight or obesity?

The page must label itself `Working demonstration` and show the snapshot date
near the headline.

### Step 3: What this source reports

The page reads the real SELECT Evidence Record and renders:

- Study title and DOI.
- Study design and population.
- Intervention and comparator.
- Exact week-208 result with confidence interval.
- Three current limitations.
- Extraction/review provenance.
- A direct `Inspect the complete Evidence Record` link to the existing claim
  page.

The page says `This study reports`, not `Knowledge Engine concludes`.

### Step 4: How the claim connects

The page summarizes only stored and deterministically computed state:

- Evidence Quality and extraction tier.
- Evidence Consensus and reliability.
- Claim Confidence and its separate reliability label.
- Evidence Coverage.
- Counts and types of reviewed relationships.

It must retain the existing explanation that Quality, Consensus, and Confidence
are separate quantities. A visitor can follow relationships to STEP 5, the Gao
meta-analysis, and the contextualizing tirzepatide comparison.

### Step 5: Limits and next exploration

The journey ends with three choices:

- `Inspect all evidence and relationships` -> complete claim page.
- `Explore the graph` -> `/graph`.
- `Try experimental retrieval` -> `/ask` with the canonical question
  prefilled, accompanied by the note that ranking evaluation is active work.

The page does not generate a cross-paper answer.

## Shared Trust Language

Every surface should use the following distinctions:

- **Stored:** copied from a validated source, Evidence Record, Relationship
  Record, or graph row.
- **Computed:** deterministic code over stored fields; formula and inputs are
  inspectable.
- **Reviewed:** a person or declared grounding-verified process authored or
  approved the record, with provenance shown.
- **AI-narrated:** optional prose over retrieved evidence; never a new source,
  relationship, or confidence score.
- **Illustrative:** a clearly isolated mockup value that is not live output.

Recommended global footer:

> Read-only alpha over a point-in-time snapshot. Evidence and relationships
> remain source-linked; deterministic scores are labeled; optional AI narration
> is never treated as new evidence or scientific review.

## Snapshot Freshness Contract

The snapshot refresh must create a small committed
`data/snapshot_metadata.json` alongside the database and Evidence Records.

Version 1 contains:

- `schema_version`: integer `1`.
- `generated_at`: UTC ISO 8601 timestamp.
- `corpus_id`: `glp1_weight_loss`.
- `core_commit`: full core Git commit hash when available.
- `evidence_records_sha256`: hash of the copied Evidence Records file.
- `relationship_records_sha256`: hash when relationship records participate in
  the deployed snapshot; otherwise `null` with an explicit reason.
- Snapshot counts for claims, relationships, and citations after the copy.

The generator stores no private absolute paths. The web app validates the small
file and exposes a simple immutable `SnapshotMetadata` reader. Missing or
invalid metadata renders `Snapshot date unavailable`; it never guesses from
filesystem modification time or deployment time.

Display requirements:

- Global footer: `Data snapshot: <date>` linked to `/about#snapshot`.
- `/demo` and `/graph`: date, core revision prefix, and actual counts.
- `/about`: the complete freshness explanation and hashes/revision suitable for
  audit.

Relationship-only changes must trigger or explicitly queue the existing refresh
workflow. Until that automation ships, the documentation must retain the known
weekly/manual exception.

## Showcase Content Contract

The showcase implementation should make these bounded changes:

1. Set the document title and social metadata to `Knowledge Engine`.
2. Add `Explore live evidence` as the primary call to action to `/demo`.
3. Keep `Read the vision` and `View source` as secondary actions.
4. Remove unexplained numeric score decorations.
5. Label Discovery and Education as long-term layers.
6. Add the working alpha and web/AI repositories to the final project links.
7. Use the shared trust language above.

The showcase must not copy live counts or the SELECT result into static content.
The alpha owns changing scientific data.

## Alpha Information Architecture

The first slice does not replace expert navigation. It changes its hierarchy:

```text
Demo | Ask | Evidence | Graph | Reports | About
```

- `Demo`: new visitor journey.
- `Ask`: experimental retrieval, clearly labeled.
- `Evidence`: existing Claims view; label is human-readable while the route may
  remain `/claims`.
- `Graph`: current summary.
- `Reports`: current reports.
- `About`: scope, trust boundary, freshness, and repositories.

Dashboard, Unconfirmed Claims, Relationship Candidates, and Roadmap remain
available from an `Inspect` or secondary navigation menu. On mobile, the primary
navigation must not occupy several lines before every page's content.

## Failure and Empty States

- Missing SELECT record: `/demo` renders `Demonstration data unavailable in
  this snapshot` with snapshot metadata and links to Graph/About; no 500 and no
  substitute record chosen silently.
- Missing Evidence Records configuration: same bounded unavailable state.
- Missing relationship rows: show the claim and state that relationship
  coverage is unavailable; do not compute consensus or confidence.
- Missing snapshot metadata: show `Snapshot date unavailable` without blocking
  evidence display.
- Optional AI service unavailable: Ask remains retrieval-only and the demo is
  unaffected.

## Implementation Sequence

### Slice 1: truthful bridge

- Add and validate snapshot metadata generation/reading.
- Add `/demo` over the existing SELECT Evidence Record and graph readers.
- Redirect `/` to `/demo`.
- Add snapshot date to the footer, Demo, Graph, and About.
- Correct About/footer/concept-preview status language.
- Simplify primary navigation, including mobile behavior.
- Update the showcase title, calls to action, future-layer labels, and
  decorative scores.
- Add focused tests and verify desktop/mobile rendering.

This is the recommended next implementation milestone.

### Slice 2: measured retrieval handoff

- Done: Demo links to the canonical prefilled Ask query.
- Done: Ask is labeled experimental retrieval.
- Done: Current Project Path goal 2 begins with the versioned, deterministic
  golden-question benchmark in `docs/retrieval_benchmark_design.md`.
- Deferred to the next focused PR: ranking changes justified by the recorded
  baseline.

No ranking change belongs in Slice 1.

### Slice 3: evidence-map expansion

- Expand the guided view only after goal 3 adds reviewed coverage that changes
  what can be shown honestly.
- Do not hand-author a second static story in the showcase.

## Acceptance Criteria

### Journey

- A visitor reaches `/demo` from the showcase in one action.
- A visitor reaches the full SELECT claim, source DOI, limitations, and
  relationships from `/demo` in one additional action.
- The showcase, Demo, About, and footer agree on what is stored, computed,
  reviewed, narrated, and illustrative.
- Ask is visible but is not presented as the canonical scientific answer.

### Freshness and truth

- Every data-bearing page shows the snapshot date or an explicit unavailable
  state.
- No unexplained score appears on the showcase.
- No page calls AI wholly future or claims that the site has no confidence
  computation.
- No page implies that optional narration is evidence or scientific review.
- No page implies that Discovery or Education Intelligence is shipped.

### Responsive and accessible behavior

- Verify at 390x844, 768x1024, and 1440x900.
- The question, effect estimate, limitations, and first action appear without
  horizontal scrolling.
- Primary navigation remains one compact control or line on mobile.
- All badges and score states have text equivalents; color is not the only
  signal.
- Heading hierarchy, focus order, link names, and contrast pass the existing
  accessibility baseline.

### Tests

- Snapshot metadata generation is deterministic except for the explicit
  timestamp and hashes exact copied bytes.
- Snapshot metadata rejects malformed or unsupported versions without a
  traceback.
- `/demo` renders the selected real record and honest missing-data states.
- `/` redirects to `/demo`; existing routes remain stable.
- No route writes to core data.
- Existing graph, Ask, claim, dashboard, report, and authentication tests pass.
- Browser screenshots verify desktop and mobile framing with no overlaps.

## Risks

- **Curated-example bias:** one strong claim can look like the entire evidence
  base. Mitigation: label it one worked example and show limitations/coverage.
- **Stale snapshot presented as current:** mitigated by generated metadata and
  explicit unavailable states.
- **Hard-coded claim disappears:** mitigated by stable `/demo` ownership and an
  honest missing-record state.
- **Marketing language outruns implementation:** mitigated by the shared trust
  vocabulary and concrete acceptance checks.
- **Task 1 expands into retrieval work:** keep Ask ranking changes in Slice 2.
- **Two-site maintenance drift:** keep changing scientific values solely in the
  alpha; showcase copy remains conceptual and links to `/demo`.

## Explicit Recommendation

Approve Slice 1 as the next implementation milestone. It should be built in two
coordinated changes: one small web PR for `/demo`, snapshot provenance, trust
copy, and navigation; one showcase update for title, calls to action, and
future-layer labeling. Review both against the same acceptance checklist before
publication.

Do not begin the golden-question retrieval implementation until this bridge is
live. Once it is, the observed Ask failures above become the initial benchmark
evidence for Current Project Path goal 2.
