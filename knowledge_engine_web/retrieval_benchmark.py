"""Deterministic golden-question evaluation for the public Ask retrieval path.

The benchmark measures the same ``answer_retrieval`` function used by ``GET
/ask`` against a versioned set of human-curated expectations. It never calls an
LLM and never changes ranking. Its job is to make retrieval failures visible
before later work attempts to correct them.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from knowledge_engine_web.evidence_reader import (
    EvidenceRecordsError,
    list_evidence_records_for_doi,
    normalize_doi,
)
from knowledge_engine_web.retrieval import SearchResult, answer_retrieval

BENCHMARK_SCHEMA_VERSION = 2
SUPPORTED_BENCHMARK_SCHEMA_VERSIONS = frozenset({1, BENCHMARK_SCHEMA_VERSION})


class RetrievalBenchmarkError(RuntimeError):
    """A benchmark definition or one of its required inputs is invalid."""


@dataclass(frozen=True)
class ExpectedResult:
    """One source that a question should retrieve, with traceable expectations."""

    doi: str
    title: str
    publication_year: int
    study_type: str
    citation: str
    evidence_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class GoldenQuestion:
    """One natural-language question and its direct and secondary source sets."""

    question_id: str
    domain_id: str
    question: str
    expected_results: tuple[ExpectedResult, ...]
    acceptable_secondary_dois: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalBenchmark:
    """The versioned benchmark contract loaded from JSON."""

    schema_version: int
    benchmark_id: str
    description: str
    top_k: int
    rank_depth: int
    gated_domain_ids: tuple[str, ...]
    questions: tuple[GoldenQuestion, ...]


@dataclass(frozen=True)
class RankedResult:
    """One retrieved source classified against a golden question."""

    rank: int
    doi: str | None
    title: str
    evidence_record_ids: tuple[str, ...]
    classification: Literal["expected", "secondary", "unexpected"]


@dataclass(frozen=True)
class ExpectedRank:
    """The observed rank for one direct expected source."""

    doi: str
    title: str
    rank: int | None


@dataclass(frozen=True)
class QuestionEvaluation:
    """Deterministic metrics and diagnostics for one question."""

    question_id: str
    domain_id: str
    question: str
    expected_count: int
    expected_found_at_k: int
    recall_at_k: float
    reciprocal_rank: float
    evidence_linked_results_at_k: int
    expected_ranks: tuple[ExpectedRank, ...]
    top_results: tuple[RankedResult, ...]


@dataclass(frozen=True)
class DomainEvaluation:
    """Macro metrics for one scientific domain in the benchmark."""

    domain_id: str
    question_count: int
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    all_expected_within_top_k: bool


@dataclass(frozen=True)
class BenchmarkEvaluation:
    """Aggregate and per-question retrieval results."""

    schema_version: int
    benchmark_id: str
    top_k: int
    question_count: int
    domain_count: int
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    macro_domain_recall_at_k: float
    macro_domain_reciprocal_rank: float
    gated_domain_ids: tuple[str, ...]
    regression_gate_passed: bool
    domains: tuple[DomainEvaluation, ...]
    questions: tuple[QuestionEvaluation, ...]


def load_benchmark(path: Path) -> RetrievalBenchmark:
    """Load and structurally validate a version 1 benchmark definition."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RetrievalBenchmarkError(f"Could not read benchmark: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise RetrievalBenchmarkError(f"Benchmark is not valid JSON: {path.name}") from exc

    if not isinstance(payload, dict):
        raise RetrievalBenchmarkError("Benchmark root must be a JSON object.")
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or schema_version not in SUPPORTED_BENCHMARK_SCHEMA_VERSIONS
    ):
        raise RetrievalBenchmarkError(f"Unsupported benchmark schema_version: {schema_version!r}.")

    benchmark_id = _required_text(payload, "benchmark_id", "benchmark")
    description = _required_text(payload, "description", "benchmark")
    top_k = _positive_int(payload.get("top_k"), "top_k")
    rank_depth = _positive_int(payload.get("rank_depth"), "rank_depth")
    if rank_depth < top_k:
        raise RetrievalBenchmarkError("rank_depth must be greater than or equal to top_k.")

    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise RetrievalBenchmarkError("Benchmark questions must be a non-empty list.")

    questions: list[GoldenQuestion] = []
    seen_question_ids: set[str] = set()
    for question_index, raw_question in enumerate(raw_questions, start=1):
        context = f"question {question_index}"
        if not isinstance(raw_question, dict):
            raise RetrievalBenchmarkError(f"{context} must be a JSON object.")
        question_id = _required_text(raw_question, "question_id", context)
        if question_id in seen_question_ids:
            raise RetrievalBenchmarkError(f"Duplicate question_id: {question_id}")
        seen_question_ids.add(question_id)
        domain_id = (
            _required_text(raw_question, "domain_id", context)
            if schema_version == BENCHMARK_SCHEMA_VERSION
            else "legacy"
        )
        question_text = _required_text(raw_question, "question", context)

        raw_expected = raw_question.get("expected_results")
        if not isinstance(raw_expected, list) or not raw_expected:
            raise RetrievalBenchmarkError(f"{context} expected_results must be non-empty.")
        expected = tuple(
            _load_expected_result(value, f"{context} expected result {index}")
            for index, value in enumerate(raw_expected, start=1)
        )
        expected_dois = [result.doi for result in expected]
        if len(set(expected_dois)) != len(expected_dois):
            raise RetrievalBenchmarkError(f"{context} contains duplicate expected DOIs.")

        raw_secondary = raw_question.get("acceptable_secondary_dois", [])
        if not isinstance(raw_secondary, list) or not all(
            isinstance(value, str) and value.strip() for value in raw_secondary
        ):
            raise RetrievalBenchmarkError(
                f"{context} acceptable_secondary_dois must contain DOI strings."
            )
        secondary = tuple(normalize_doi(value) for value in raw_secondary)
        if set(expected_dois) & set(secondary):
            raise RetrievalBenchmarkError(
                f"{context} cannot classify one DOI as both expected and secondary."
            )

        questions.append(
            GoldenQuestion(
                question_id=question_id,
                domain_id=domain_id,
                question=question_text,
                expected_results=expected,
                acceptable_secondary_dois=secondary,
            )
        )

    declared_domain_ids = tuple(dict.fromkeys(question.domain_id for question in questions))
    if schema_version == BENCHMARK_SCHEMA_VERSION:
        raw_gated_domains = payload.get("gated_domain_ids")
        if (
            not isinstance(raw_gated_domains, list)
            or not raw_gated_domains
            or not all(isinstance(value, str) and value.strip() for value in raw_gated_domains)
        ):
            raise RetrievalBenchmarkError("gated_domain_ids must contain non-empty domain IDs.")
        gated_domain_ids = tuple(value.strip() for value in raw_gated_domains)
        if len(set(gated_domain_ids)) != len(gated_domain_ids):
            raise RetrievalBenchmarkError("gated_domain_ids must not contain duplicates.")
        unknown_gated_domains = set(gated_domain_ids) - set(declared_domain_ids)
        if unknown_gated_domains:
            unknown = ", ".join(sorted(unknown_gated_domains))
            raise RetrievalBenchmarkError(f"Unknown gated domain IDs: {unknown}.")
    else:
        gated_domain_ids = declared_domain_ids

    return RetrievalBenchmark(
        schema_version=schema_version,
        benchmark_id=benchmark_id,
        description=description,
        top_k=top_k,
        rank_depth=rank_depth,
        gated_domain_ids=gated_domain_ids,
        questions=tuple(questions),
    )


def evaluate_benchmark(
    benchmark: RetrievalBenchmark,
    *,
    database_path: Path,
    evidence_path: Path,
) -> BenchmarkEvaluation:
    """Evaluate the committed Ask retrieval path without changing any data."""

    if not database_path.is_file():
        raise RetrievalBenchmarkError(f"Database is unavailable: {database_path.name}")
    if not evidence_path.is_file():
        raise RetrievalBenchmarkError(f"Evidence Records are unavailable: {evidence_path.name}")

    _validate_expected_evidence(benchmark, evidence_path)
    database_uri = database_path.resolve().as_posix()
    engine = create_engine(f"sqlite:///file:{database_uri}?mode=ro&uri=true")
    evaluations: list[QuestionEvaluation] = []
    try:
        _validate_expected_papers(benchmark, engine)
        for question in benchmark.questions:
            results = answer_retrieval(
                engine,
                question.question,
                limit=benchmark.rank_depth,
                evidence_path=evidence_path,
            )
            evaluations.append(
                _evaluate_question(question, results, evidence_path, benchmark.top_k)
            )
    finally:
        engine.dispose()

    count = len(evaluations)
    domain_evaluations = _evaluate_domains(evaluations, benchmark.top_k)
    gated_domains = {
        domain.domain_id: domain
        for domain in domain_evaluations
        if domain.domain_id in benchmark.gated_domain_ids
    }
    return BenchmarkEvaluation(
        schema_version=benchmark.schema_version,
        benchmark_id=benchmark.benchmark_id,
        top_k=benchmark.top_k,
        question_count=count,
        domain_count=len(domain_evaluations),
        mean_recall_at_k=sum(item.recall_at_k for item in evaluations) / count,
        mean_reciprocal_rank=sum(item.reciprocal_rank for item in evaluations) / count,
        macro_domain_recall_at_k=(
            sum(item.mean_recall_at_k for item in domain_evaluations) / len(domain_evaluations)
        ),
        macro_domain_reciprocal_rank=(
            sum(item.mean_reciprocal_rank for item in domain_evaluations) / len(domain_evaluations)
        ),
        gated_domain_ids=benchmark.gated_domain_ids,
        regression_gate_passed=all(
            gated_domains[domain_id].all_expected_within_top_k
            for domain_id in benchmark.gated_domain_ids
        ),
        domains=domain_evaluations,
        questions=tuple(evaluations),
    )


def render_evaluation(evaluation: BenchmarkEvaluation) -> str:
    """Render deterministic, review-friendly benchmark output."""

    lines = [
        f"Golden retrieval benchmark: {evaluation.benchmark_id}",
        f"Questions: {evaluation.question_count}",
        f"Domains: {evaluation.domain_count}",
        f"Mean Recall@{evaluation.top_k}: {evaluation.mean_recall_at_k:.3f}",
        f"Mean reciprocal rank: {evaluation.mean_reciprocal_rank:.3f}",
        (f"Macro domain Recall@{evaluation.top_k}: {evaluation.macro_domain_recall_at_k:.3f}"),
        (f"Macro domain reciprocal rank: {evaluation.macro_domain_reciprocal_rank:.3f}"),
        (
            "Regression gate: "
            f"{'passed' if evaluation.regression_gate_passed else 'failed'} "
            f"({', '.join(evaluation.gated_domain_ids)})"
        ),
        "Domain results:",
    ]
    for domain in evaluation.domains:
        gate = "all expected within top k" if domain.all_expected_within_top_k else "baseline gaps"
        lines.append(
            f"  - {domain.domain_id}: {domain.question_count} question(s), "
            f"Recall@{evaluation.top_k} {domain.mean_recall_at_k:.3f}, "
            f"MRR {domain.mean_reciprocal_rank:.3f}, {gate}"
        )
    for question in evaluation.questions:
        lines.extend(
            [
                "",
                f"[{question.domain_id}/{question.question_id}] {question.question}",
                (
                    f"Recall@{evaluation.top_k}: {question.expected_found_at_k}/"
                    f"{question.expected_count} ({question.recall_at_k:.3f})"
                ),
                f"Reciprocal rank: {question.reciprocal_rank:.3f}",
                (
                    f"Evidence-linked results@{evaluation.top_k}: "
                    f"{question.evidence_linked_results_at_k}"
                ),
                "Expected source ranks:",
            ]
        )
        for expected in question.expected_ranks:
            rank = str(expected.rank) if expected.rank is not None else "not retrieved"
            lines.append(f"  - {expected.doi}: {rank} ({expected.title})")
        lines.append(f"Top {evaluation.top_k}:")
        for result in question.top_results:
            doi = result.doi or "DOI unavailable"
            evidence = ", ".join(result.evidence_record_ids) or "no linked evidence record"
            lines.append(
                f"  {result.rank}. [{result.classification}] {doi} - {result.title} ({evidence})"
            )
    return "\n".join(lines) + "\n"


def evaluation_as_json(evaluation: BenchmarkEvaluation) -> str:
    """Return stable machine-readable output for later regression automation."""

    return json.dumps(asdict(evaluation), indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    """Run the benchmark from the command line."""

    parser = argparse.ArgumentParser(description="Evaluate the golden Ask retrieval questions.")
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("data/retrieval_benchmark.json"),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/knowledge_engine.sqlite3"),
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("data/evidence_records.jsonl"),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        evaluation = evaluate_benchmark(
            load_benchmark(args.benchmark),
            database_path=args.database,
            evidence_path=args.evidence,
        )
    except (RetrievalBenchmarkError, EvidenceRecordsError) as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    rendered = (
        evaluation_as_json(evaluation) if args.format == "json" else render_evaluation(evaluation)
    )
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Benchmark report written: {args.output.as_posix()}")
    else:
        print(rendered, end="")


def _load_expected_result(value: Any, context: str) -> ExpectedResult:
    if not isinstance(value, dict):
        raise RetrievalBenchmarkError(f"{context} must be a JSON object.")
    year = value.get("publication_year")
    if isinstance(year, bool) or not isinstance(year, int):
        raise RetrievalBenchmarkError(f"{context} publication_year must be an integer.")
    raw_ids = value.get("evidence_record_ids")
    if (
        not isinstance(raw_ids, list)
        or not raw_ids
        or not all(isinstance(record_id, str) and record_id.strip() for record_id in raw_ids)
    ):
        raise RetrievalBenchmarkError(f"{context} evidence_record_ids must be non-empty.")
    return ExpectedResult(
        doi=normalize_doi(_required_text(value, "doi", context)),
        title=_required_text(value, "title", context),
        publication_year=year,
        study_type=_required_text(value, "study_type", context),
        citation=_required_text(value, "citation", context),
        evidence_record_ids=tuple(record_id.strip() for record_id in raw_ids),
    )


def _required_text(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RetrievalBenchmarkError(f"{context} field {field!r} must be non-empty text.")
    return value.strip()


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RetrievalBenchmarkError(f"{field} must be a positive integer.")
    return value


def _validate_expected_evidence(benchmark: RetrievalBenchmark, evidence_path: Path) -> None:
    for question in benchmark.questions:
        for expected in question.expected_results:
            records = list_evidence_records_for_doi(evidence_path, expected.doi)
            by_id = {record.evidence_record_id: record for record in records}
            for record_id in expected.evidence_record_ids:
                record = by_id.get(record_id)
                if record is None:
                    raise RetrievalBenchmarkError(
                        f"{question.question_id}: expected evidence record {record_id!r} "
                        f"does not match DOI {expected.doi}."
                    )
                if record.study_type != expected.study_type:
                    raise RetrievalBenchmarkError(
                        f"{question.question_id}: evidence record {record_id!r} has study_type "
                        f"{record.study_type!r}, expected {expected.study_type!r}."
                    )


def _validate_expected_papers(benchmark: RetrievalBenchmark, engine: Engine) -> None:
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT title, publication_year, doi FROM papers WHERE doi IS NOT NULL")
            ).all()
    except SQLAlchemyError as exc:
        raise RetrievalBenchmarkError("Could not read expected papers from the database.") from exc

    papers_by_doi = {normalize_doi(str(row.doi)): row for row in rows}
    checked: set[str] = set()
    for question in benchmark.questions:
        for expected in question.expected_results:
            if expected.doi in checked:
                continue
            checked.add(expected.doi)
            row = papers_by_doi.get(expected.doi)
            if row is None:
                raise RetrievalBenchmarkError(
                    f"Expected DOI {expected.doi} is not present in the benchmark database."
                )
            if str(row.title) != expected.title:
                raise RetrievalBenchmarkError(
                    f"Expected DOI {expected.doi} has a different title in the database."
                )
            if (
                row.publication_year is not None
                and row.publication_year != expected.publication_year
            ):
                raise RetrievalBenchmarkError(
                    f"Expected DOI {expected.doi} has publication_year "
                    f"{row.publication_year!r}, expected {expected.publication_year}."
                )


def _evaluate_question(
    question: GoldenQuestion,
    results: Sequence[SearchResult],
    evidence_path: Path,
    top_k: int,
) -> QuestionEvaluation:
    expected_dois = {item.doi for item in question.expected_results}
    secondary_dois = set(question.acceptable_secondary_dois)
    ranks: dict[str, int] = {}
    for rank, result in enumerate(results, start=1):
        if result.doi:
            ranks.setdefault(normalize_doi(result.doi), rank)

    expected_ranks = tuple(
        ExpectedRank(doi=item.doi, title=item.title, rank=ranks.get(item.doi))
        for item in question.expected_results
    )
    found_ranks = [item.rank for item in expected_ranks if item.rank is not None]
    found_at_k = sum(rank <= top_k for rank in found_ranks)
    first_rank = min(found_ranks) if found_ranks else None

    ranked_results: list[RankedResult] = []
    for rank, result in enumerate(results[:top_k], start=1):
        doi = normalize_doi(result.doi) if result.doi else None
        if doi in expected_dois:
            classification: Literal["expected", "secondary", "unexpected"] = "expected"
        elif doi in secondary_dois:
            classification = "secondary"
        else:
            classification = "unexpected"
        evidence_ids = (
            tuple(
                record.evidence_record_id
                for record in list_evidence_records_for_doi(evidence_path, doi)
            )
            if doi
            else ()
        )
        ranked_results.append(
            RankedResult(
                rank=rank,
                doi=doi,
                title=result.title,
                evidence_record_ids=evidence_ids,
                classification=classification,
            )
        )

    return QuestionEvaluation(
        question_id=question.question_id,
        domain_id=question.domain_id,
        question=question.question,
        expected_count=len(expected_dois),
        expected_found_at_k=found_at_k,
        recall_at_k=found_at_k / len(expected_dois),
        reciprocal_rank=1.0 / first_rank if first_rank is not None else 0.0,
        evidence_linked_results_at_k=sum(bool(item.evidence_record_ids) for item in ranked_results),
        expected_ranks=expected_ranks,
        top_results=tuple(ranked_results),
    )


def _evaluate_domains(
    questions: Sequence[QuestionEvaluation], top_k: int
) -> tuple[DomainEvaluation, ...]:
    grouped: dict[str, list[QuestionEvaluation]] = {}
    for question in questions:
        grouped.setdefault(question.domain_id, []).append(question)

    domains: list[DomainEvaluation] = []
    for domain_id, domain_questions in grouped.items():
        count = len(domain_questions)
        domains.append(
            DomainEvaluation(
                domain_id=domain_id,
                question_count=count,
                mean_recall_at_k=(
                    sum(question.recall_at_k for question in domain_questions) / count
                ),
                mean_reciprocal_rank=(
                    sum(question.reciprocal_rank for question in domain_questions) / count
                ),
                all_expected_within_top_k=all(
                    expected.rank is not None and expected.rank <= top_k
                    for question in domain_questions
                    for expected in question.expected_ranks
                ),
            )
        )
    return tuple(domains)


if __name__ == "__main__":
    main()
