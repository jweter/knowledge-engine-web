# Golden-Question Retrieval Benchmark

## Decision

Knowledge Engine will measure the real `GET /ask` retrieval path against a
small, versioned set of human-curated scientific questions before changing its
ranking. The benchmark is deterministic, uses the committed alpha SQLite
snapshot and Evidence Records file, and never calls an LLM.

This begins Current Project Path goal 2. It does not improve ranking yet. The
first result is intentionally a truthful failing baseline that tells the next
implementation exactly what must improve.

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

The first milestone does not define a passing threshold. Freezing today's poor
ranking as an acceptable threshold would turn a baseline into a guarantee. A
later ranking PR must show the before/after report and justify any proposed
regression gate.

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

This is a diagnosis, not yet a ranking-design decision.

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
- Study-type and evidence expectations cover only the current golden sources.
- Recall@5 does not measure snippet usefulness or citation presentation.
- There are not yet hard regression thresholds in CI.

## Next Implementation

Use this baseline to design the smallest explainable ranking correction. The
first candidate should evaluate evidence-aware reranking and stronger treatment
of question concepts before changing tokenization or adding model-generated
query expansion. Any correction must:

1. materially improve the broad canonical question;
2. preserve or improve the three more specific questions;
3. keep ranking deterministic and inspectable;
4. avoid treating “has an Evidence Record” as proof of relevance;
5. publish an exact before/after benchmark report.

Only after retrieval behavior is measured and improved should the project move
to Current Project Path goal 3's broader golden evidence-map completion.
