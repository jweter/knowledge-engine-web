# Golden-Question Retrieval Benchmark

## Decision

Knowledge Engine will measure the real `GET /ask` retrieval path against a
small, versioned set of human-curated scientific questions before changing its
ranking. The benchmark is deterministic, uses the committed alpha SQLite
snapshot and Evidence Records file, and never calls an LLM.

This begins Current Project Path goal 2. The first committed result was a
truthful failing baseline. The follow-up implements the smallest measured
correction: FTS5 still generates candidates, then stored source-linked evidence
text deterministically reranks them.

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

## Version 1 Contract

`data/retrieval_benchmark.json` contains:

- `schema_version`: integer `1`;
- a stable `benchmark_id`;
- `top_k` and full `rank_depth` evaluation bounds;
- natural-language golden questions;
- direct expected papers with DOI, title, year, study type, citation, and
  Evidence Record IDs;
- acceptable secondary DOI values that are useful context but do not satisfy
  direct recall.

The first benchmark uses four forms of the GLP-1/body-weight question:

- broad drug-class and body-weight effect;
- long-term semaglutide effect;
- randomized-evidence summary;
- two-to-four-year durability.

The direct gold set is deliberately limited to the three sources already
curated end to end in the public evidence journey: STEP 5, the Gao systematic
review/meta-analysis, and the SELECT prespecified analysis. Expanding that set
belongs to Current Project Path goal 3 and requires scientific coverage review,
not a ranking engineer adding convenient labels.

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

The initial milestone did not define a passing threshold. The measured
follow-up now makes the committed benchmark a regression gate: every direct
expected source must remain within the top five, yielding mean Recall@5 of
`1.000`. This protects the four reviewed questions; it does not claim broad
retrieval validity outside them.

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

## Trust Boundaries

- No LLM is called.
- No scientific conclusion is generated.
- Evidence linkage is matched only by normalized DOI.
- Secondary sources never count as direct recall.
- Missing or contradictory benchmark metadata fails visibly.
- Benchmark expectations are human-curated and reviewed in Git.
- Ranking changes must not rewrite the gold set merely to improve metrics.

## Known Limitations

- Four questions and three direct papers are enough to expose the current
  failure, but not enough to certify broad scientific retrieval quality.
- The benchmark evaluates the committed alpha snapshot, not an operator's
  larger private database.
- The reranker considers at most 500 FTS candidates. A relevant source absent
  from that lexical pool cannot be recovered by this change.
- Token overlap recognizes aligned language, not synonyms or deeper scientific
  equivalence.
- Ranking currently depends on the coverage and wording of stored Evidence
  Records; papers without records retain lexical order behind aligned records.
- Study-type and evidence expectations cover only the current golden sources.
- Recall@5 does not measure snippet usefulness or citation presentation.
- There are not yet hard regression thresholds in CI.

## Next Implementation

Current Project Path goal 2 now has a measured first correction. The next
project step is goal 3: complete and review the broader GLP-1/body-weight
evidence map. That work should expand scientific coverage and may later expand
the gold benchmark through explicit review. It must not rewrite today's gold
set merely to preserve a favorable metric.
