# Cross-Domain Golden-Question Retrieval Benchmark

## Decision

Knowledge Engine will measure the real `GET /ask` retrieval path against a
small, versioned set of human-curated scientific questions before changing its
ranking. The benchmark is deterministic, uses the committed alpha SQLite
snapshot and Evidence Records file, and never calls an LLM.

This began Current Project Path goal 2. The first committed result was a
truthful failing GLP-1 baseline. The follow-up implemented the smallest
measured correction: FTS5 still generates candidates, then stored source-linked
evidence text deterministically reranks them. Version 2 now asks whether that
same path generalizes across the project's three reviewed scientific domains.

## Objective

The benchmark answers four separate questions about retrieval quality:

1. Did direct expected papers appear in the first five results?
2. How far down the complete result list was the first direct paper?
3. Did top results have source-linked Evidence Records?
4. Which top results were direct, useful-but-secondary, or unexpected?

It does not score scientific truth, evidence quality, consensus, claim
confidence, or LLM prose.

## Ownership

The benchmark lives in `knowledge-engine-web` because it evaluates the exact
`answer_retrieval` function used by the public `/ask` route against the same
committed alpha snapshot. `knowledge-engine-core` remains authoritative for the
papers and Evidence Records copied into that snapshot.

The evaluator validates every expected DOI and title against the committed
database, rejects a conflicting non-null publication year, and validates every
study type and Evidence Record ID against the committed Evidence Records file
before computing metrics. The benchmark keeps the curated citation year when
the trimmed alpha snapshot's paper row has no year. Stale or contradictory
expectations fail explicitly instead of silently changing the gold standard.

## Version 2 Contract

`data/retrieval_benchmark.json` contains:

- `schema_version`: integer `2`;
- a stable `benchmark_id`;
- `top_k` and full `rank_depth` evaluation bounds;
- `gated_domain_ids`, naming domains whose direct expectations must all remain
  within the top-k regression boundary;
- natural-language golden questions;
- one stable `domain_id` per question;
- direct expected papers with DOI, title, year, study type, citation, and
  Evidence Record IDs;
- acceptable secondary DOI values that are useful context but do not satisfy
  direct recall.

Version 1 files remain readable as one `legacy` domain and retain their original
all-questions regression behavior. Writers use version 2.

The benchmark retains four forms of the GLP-1/body-weight question:

- broad drug-class and body-weight effect;
- long-term semaglutide effect;
- randomized-evidence summary;
- two-to-four-year durability.

It adds four oncology and four mental-health questions selected from Core's
reviewed golden evidence maps. Questions cover each domain's broad research
question plus narrower population, comparator, intervention, or treatment-line
slices. Direct expected sources must answer the exact wording. Reviewed but
narrower sources may be marked acceptable secondary context; they never count
as direct recall.

The gold set is deliberately limited to sources curated end to end in reviewed
golden maps. Expanding it requires scientific coverage review, not a ranking
engineer adding convenient labels after seeing output.

## Metrics

- **Recall@5:** direct expected papers retrieved in the first five divided by
  all direct expected papers for that question.
- **Reciprocal rank:** `1 / rank` for the first direct expected paper anywhere
  within the configured rank depth; zero when none is retrieved.
- **Evidence-linked results@5:** top-five papers with at least one matching
  Evidence Record by normalized DOI. This is diagnostic and is not treated as
  relevance by itself.
- **Expected source ranks:** full observed ranks for every direct expected DOI.
- **Top-five classification:** `expected`, `secondary`, or `unexpected`.
- **Macro domain Recall@5 and reciprocal rank:** compute each domain's mean
  first, then average domains equally so oncology's larger corpus cannot hide
  weakness in another domain.
- **Regression gate:** passes only when every direct expected source in every
  named gated domain remains within the top five.

The initial milestone did not define a passing threshold. The measured GLP-1
follow-up made its four questions a regression gate. Version 2 extends that
same top-five requirement to all three reviewed domains after recording the
cross-domain baseline. This protects twelve reviewed questions; it does not
claim broad retrieval validity outside them.

## Baseline

Run on the committed alpha snapshot after public-journey PR #27:

| Question | Recall@5 | Reciprocal rank | Expected ranks | Evidence-linked@5 |
| --- | ---: | ---: | --- | ---: |
| Broad GLP-1/body weight | 0/3 | 0.007 | STEP 5: 135; Gao: 141; SELECT: 347 | 2 |
| Long-term semaglutide | 1/2 | 0.250 | STEP 5: 43; SELECT: 4 | 2 |
| Randomized evidence | 1/1 | 0.200 | Gao: 5 | 4 |
| Two-to-four-year duration | 1/2 | 1.000 | STEP 5: 1; SELECT: 16 | 3 |

Aggregate baseline:

- mean Recall@5: `0.500`;
- mean reciprocal rank: `0.364`.

The canonical broad question is the clearest failure. Its first five results
include narrower reproductive-health, ketogenic-diet, insulin-resistance, and
cardiovascular contexts while the three direct sources appear far below them.
More specific wording improves retrieval sharply, demonstrating that the
sources and FTS rows exist. The likely failure is broad OR-query dilution and
the absence of evidence-aware ranking signals, not missing documents.

This baseline remains recorded as the diagnosis that justified the ranking
change.

The alpha snapshot currently leaves `publication_year` null on all three direct
gold papers. Their reviewed citation years remain explicit in the benchmark,
but fixing snapshot metadata completeness is separate from ranking work.

## Running the Benchmark

```bash
poetry run knowledge-engine-retrieval-benchmark
```

Machine-readable output:

```bash
poetry run knowledge-engine-retrieval-benchmark --format json
```

Alternate inputs can be supplied with `--benchmark`, `--database`, and
`--evidence`. `--output` writes the selected format to a file. The evaluator is
read-only and does not mutate the database or Evidence Records.

## Evidence-Aware Reranking

The shared `answer_retrieval` path now has two deterministic stages when an
Evidence Records file is configured:

1. SQLite FTS5 retrieves up to 500 lexical candidates using the existing
   title/abstract/body query.
2. For each candidate DOI, the reranker calculates question-token coverage in
   the paper's stored Evidence Records. It weights `research_question` at 5,
   `claim_text` at 3, the combined PICO fields at 2, and `result_summary` at 1.
3. Candidates sort by descending evidence alignment, with original FTS rank as
   the stable tie-breaker. A candidate with no Evidence Record or no matching
   evidence text receives zero alignment; merely having a record is not a
   boost.

The public Ask route and benchmark call the same function. If Evidence Records
are not configured or the file is unavailable, Ask retains the original
lexical ranking. The alignment value is a retrieval signal only. It does not
use or alter Evidence Quality, review tier, consensus, Claim Confidence, or any
scientific conclusion.

## Measured Result

The gold fixture and expected sources were not changed. Running the same four
questions over the same committed snapshot produces:

| Question | Recall@5 before | Recall@5 after | Expected ranks before | Expected ranks after |
| --- | ---: | ---: | --- | --- |
| Broad GLP-1/body weight | 0/3 | 3/3 | STEP 5: 135; Gao: 141; SELECT: 347 | STEP 5: 1; Gao: 2; SELECT: 3 |
| Long-term semaglutide | 1/2 | 2/2 | STEP 5: 43; SELECT: 4 | STEP 5: 3; SELECT: 1 |
| Randomized evidence | 1/1 | 1/1 | Gao: 5 | Gao: 1 |
| Two-to-four-year duration | 1/2 | 2/2 | STEP 5: 1; SELECT: 16 | STEP 5: 5; SELECT: 1 |

Aggregate comparison:

- mean Recall@5: `0.500` -> `1.000`;
- mean reciprocal rank: `0.364` -> `1.000`.

The correction materially fixes the broad question and does not regress the
three specific questions. The exact committed-data result is covered by the
test suite so a later change cannot silently restore the diagnosed failure.

## Cross-Domain Version 2 Baseline

The version 2 gold set was curated from Core's reviewed GLP-1, NSCLC checkpoint
inhibitor, and MDD antidepressant evidence maps before changing ranking. It
contains twelve questions: four per domain. The first run against the published
alpha snapshot produced:

| Domain | Questions | Mean Recall@5 | Mean reciprocal rank | All direct sources in top 5 |
| --- | ---: | ---: | ---: | --- |
| GLP-1/body weight | 4 | 1.000 | 1.000 | yes |
| NSCLC/checkpoint inhibitors | 4 | 1.000 | 0.875 | yes |
| MDD/antidepressants | 4 | 1.000 | 0.875 | yes |

Aggregate version 2 baseline:

- mean Recall@5: `1.000`;
- mean reciprocal rank: `0.917`;
- macro domain Recall@5: `1.000`;
- macro domain reciprocal rank: `0.917`;
- all three domain regression gates: passed.

The non-perfect reciprocal rank is preserved. On each broad non-GLP-1
question, a narrower but genuinely relevant reviewed golden-map source ranked
first while every direct source remained within the top three. Those sources
are labeled secondary context, not silently promoted into the direct gold set.
Because the measured baseline found no direct-recall failure, this milestone
makes no ranking change.

## Trust Boundaries

- No LLM is called.
- No scientific conclusion is generated.
- Evidence linkage is matched only by normalized DOI.
- Secondary sources never count as direct recall.
- Missing or contradictory benchmark metadata fails visibly.
- Benchmark expectations are human-curated and reviewed in Git.
- Ranking changes must not rewrite the gold set merely to improve metrics.

## Known Limitations

- Twelve questions across three domains are a meaningful generalization check,
  but not enough to certify broad scientific retrieval quality.
- The benchmark evaluates the committed alpha snapshot, not an operator's
  larger private database.
- The reranker considers at most 500 FTS candidates. A relevant source absent
  from that lexical pool cannot be recovered by this change.
- Token overlap recognizes aligned language, not synonyms or deeper scientific
  equivalence.
- Ranking currently depends on the coverage and wording of stored Evidence
  Records; papers without records retain lexical order behind aligned records.
- Study-type and evidence expectations cover only reviewed golden-map sources.
- Recall@5 does not measure snippet usefulness or citation presentation.
- The gate checks whether reviewed direct sources remain within the top five;
  it does not yet set a minimum reciprocal-rank threshold or grade unexpected
  results semantically.

## Next Implementation

The cross-domain baseline found no direct-recall defect requiring a ranking
change. The next update must therefore be chosen from the project's remaining
product gates rather than modifying retrieval speculatively. Future retrieval
work begins only when a new reviewed question, snapshot change, or user-facing
failure breaks a domain gate or exposes a diagnostic gap. It must not rewrite
today's gold set merely to preserve a favorable metric.
