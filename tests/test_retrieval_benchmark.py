from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, MetaData, Table, insert, text

from knowledge_engine_web.retrieval_benchmark import (
    RetrievalBenchmarkError,
    evaluate_benchmark,
    evaluation_as_json,
    load_benchmark,
    main,
    render_evaluation,
)
from tests._fixtures import build_engine, create_papers_table


def _create_fts_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                CREATE VIRTUAL TABLE paper_search
                USING fts5(
                    title,
                    abstract,
                    body_text,
                    raw_text,
                    tokenize='porter unicode61'
                )
                """)
        )


def _insert_paper(
    engine: Engine,
    *,
    paper_id: int,
    title: str,
    doi: str,
    abstract: str,
) -> None:
    metadata = MetaData()
    papers = Table("papers", metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            insert(papers).values(
                id=paper_id,
                title=title,
                doi=doi,
                abstract=abstract,
                publication_year=2022,
            )
        )
        connection.execute(
            text(
                "INSERT INTO paper_search(rowid, title, abstract, body_text, raw_text) "
                "VALUES (:id, :title, :abstract, '', '')"
            ),
            {"id": paper_id, "title": title, "abstract": abstract},
        )


def _write_evidence(path: Path) -> None:
    records = [
        {
            "evidence_record_id": "ev-direct",
            "source_doi": "10.1000/direct",
            "study_type": "randomized_controlled_trial",
        },
        {
            "evidence_record_id": "ev-secondary",
            "source_doi": "10.1000/secondary",
            "study_type": "systematic_review_meta_analysis",
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def _benchmark_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "benchmark_id": "test-benchmark-v2",
        "description": "A deterministic test benchmark.",
        "top_k": 3,
        "rank_depth": 10,
        "gated_domain_ids": ["metabolic_health"],
        "questions": [
            {
                "question_id": "weight-loss",
                "domain_id": "metabolic_health",
                "question": "Does semaglutide reduce body weight?",
                "expected_results": [
                    {
                        "doi": "https://doi.org/10.1000/DIRECT",
                        "title": "Direct semaglutide trial",
                        "publication_year": 2022,
                        "study_type": "randomized_controlled_trial",
                        "citation": "Scientist A. Direct Trial. 2022. doi:10.1000/direct.",
                        "evidence_record_ids": ["ev-direct"],
                    }
                ],
                "acceptable_secondary_dois": ["doi:10.1000/secondary"],
            }
        ],
    }


def _write_benchmark(path: Path, payload: dict[str, object] | None = None) -> None:
    path.write_text(json.dumps(payload or _benchmark_payload()), encoding="utf-8")


def _build_benchmark_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    database_path = tmp_path / "benchmark.sqlite3"
    engine = build_engine(tmp_path, "benchmark")
    create_papers_table(engine)
    _create_fts_table(engine)
    _insert_paper(
        engine,
        paper_id=1,
        title="Incidental body-weight article",
        doi="10.1000/incidental",
        abstract="Body weight and semaglutide are mentioned incidentally.",
    )
    _insert_paper(
        engine,
        paper_id=2,
        title="Direct semaglutide trial",
        doi="10.1000/direct",
        abstract="Semaglutide reduced body weight.",
    )
    _insert_paper(
        engine,
        paper_id=3,
        title="Semaglutide systematic review",
        doi="10.1000/secondary",
        abstract="A review of semaglutide and weight outcomes.",
    )
    engine.dispose()

    benchmark_path = tmp_path / "benchmark.json"
    evidence_path = tmp_path / "evidence.jsonl"
    _write_benchmark(benchmark_path)
    _write_evidence(evidence_path)
    return benchmark_path, database_path, evidence_path


def test_load_benchmark_normalizes_dois(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    _write_benchmark(path)

    benchmark = load_benchmark(path)

    question = benchmark.questions[0]
    assert question.expected_results[0].doi == "10.1000/direct"
    assert question.acceptable_secondary_dois == ("10.1000/secondary",)


@pytest.mark.parametrize("schema_version", [True, 3, "2", None])
def test_load_benchmark_rejects_unsupported_schema_versions(
    tmp_path: Path, schema_version: object
) -> None:
    path = tmp_path / "benchmark.json"
    payload = _benchmark_payload()
    payload["schema_version"] = schema_version
    _write_benchmark(path, payload)

    with pytest.raises(RetrievalBenchmarkError, match="Unsupported benchmark schema_version"):
        load_benchmark(path)


def test_load_benchmark_preserves_version_1_compatibility(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    payload = _benchmark_payload()
    payload["schema_version"] = 1
    payload.pop("gated_domain_ids")
    questions = payload["questions"]
    assert isinstance(questions, list)
    questions[0].pop("domain_id")
    _write_benchmark(path, payload)

    benchmark = load_benchmark(path)

    assert benchmark.schema_version == 1
    assert benchmark.gated_domain_ids == ("legacy",)
    assert benchmark.questions[0].domain_id == "legacy"


def test_load_benchmark_rejects_unknown_gated_domain(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    payload = _benchmark_payload()
    payload["gated_domain_ids"] = ["unknown"]
    _write_benchmark(path, payload)

    with pytest.raises(RetrievalBenchmarkError, match="Unknown gated domain IDs"):
        load_benchmark(path)


def test_load_benchmark_rejects_duplicate_question_ids(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    payload = _benchmark_payload()
    questions = payload["questions"]
    assert isinstance(questions, list)
    questions.append(dict(questions[0]))
    _write_benchmark(path, payload)

    with pytest.raises(RetrievalBenchmarkError, match="Duplicate question_id"):
        load_benchmark(path)


def test_evaluate_benchmark_reports_rank_metrics_and_evidence_links(tmp_path: Path) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)

    evaluation = evaluate_benchmark(
        load_benchmark(benchmark_path),
        database_path=database_path,
        evidence_path=evidence_path,
    )

    question = evaluation.questions[0]
    assert question.expected_found_at_k == 1
    assert question.recall_at_k == 1.0
    assert question.reciprocal_rank in {1.0, 0.5}
    assert question.expected_ranks[0].rank in {1, 2}
    assert question.evidence_linked_results_at_k >= 1
    expected_result = next(
        result for result in question.top_results if result.doi == "10.1000/direct"
    )
    assert expected_result.classification == "expected"
    assert expected_result.evidence_record_ids == ("ev-direct",)
    assert {result.classification for result in question.top_results} == {
        "expected",
        "secondary",
        "unexpected",
    }


def test_evaluate_benchmark_reports_macro_metrics_for_each_domain(tmp_path: Path) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    second_question = dict(payload["questions"][0])
    second_question["question_id"] = "weight-loss-second-domain"
    second_question["domain_id"] = "clinical_pharmacology"
    payload["questions"].append(second_question)
    payload["gated_domain_ids"].append("clinical_pharmacology")
    _write_benchmark(benchmark_path, payload)

    evaluation = evaluate_benchmark(
        load_benchmark(benchmark_path),
        database_path=database_path,
        evidence_path=evidence_path,
    )

    assert evaluation.domain_count == 2
    assert evaluation.macro_domain_recall_at_k == 1.0
    assert evaluation.macro_domain_reciprocal_rank in {1.0, 0.5}
    assert evaluation.regression_gate_passed is True
    assert [domain.domain_id for domain in evaluation.domains] == [
        "metabolic_health",
        "clinical_pharmacology",
    ]


def test_regression_gate_fails_when_a_gated_expected_source_misses_top_k(
    tmp_path: Path,
) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    payload["top_k"] = 1
    payload["questions"][0]["expected_results"].append(
        {
            "doi": "10.1000/secondary",
            "title": "Semaglutide systematic review",
            "publication_year": 2022,
            "study_type": "systematic_review_meta_analysis",
            "citation": "Scientist B. Systematic Review. 2022. doi:10.1000/secondary.",
            "evidence_record_ids": ["ev-secondary"],
        }
    )
    payload["questions"][0]["acceptable_secondary_dois"] = []
    _write_benchmark(benchmark_path, payload)

    evaluation = evaluate_benchmark(
        load_benchmark(benchmark_path),
        database_path=database_path,
        evidence_path=evidence_path,
    )

    assert evaluation.regression_gate_passed is False
    assert evaluation.domains[0].all_expected_within_top_k is False


def test_evaluate_benchmark_does_not_modify_the_database(tmp_path: Path) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)
    before = database_path.read_bytes()

    evaluate_benchmark(
        load_benchmark(benchmark_path),
        database_path=database_path,
        evidence_path=evidence_path,
    )

    assert database_path.read_bytes() == before


def test_evaluate_benchmark_rejects_stale_evidence_expectations(tmp_path: Path) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    payload["questions"][0]["expected_results"][0]["evidence_record_ids"] = ["missing"]
    _write_benchmark(benchmark_path, payload)

    with pytest.raises(RetrievalBenchmarkError, match="does not match DOI"):
        evaluate_benchmark(
            load_benchmark(benchmark_path),
            database_path=database_path,
            evidence_path=evidence_path,
        )


def test_evaluate_benchmark_rejects_stale_expected_paper_metadata(tmp_path: Path) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    payload["questions"][0]["expected_results"][0]["publication_year"] = 2021
    _write_benchmark(benchmark_path, payload)

    with pytest.raises(RetrievalBenchmarkError, match="publication_year"):
        evaluate_benchmark(
            load_benchmark(benchmark_path),
            database_path=database_path,
            evidence_path=evidence_path,
        )


def test_renderers_are_deterministic_and_machine_readable(tmp_path: Path) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)
    evaluation = evaluate_benchmark(
        load_benchmark(benchmark_path),
        database_path=database_path,
        evidence_path=evidence_path,
    )

    rendered = render_evaluation(evaluation)
    payload = json.loads(evaluation_as_json(evaluation))

    assert "Golden retrieval benchmark: test-benchmark-v2" in rendered
    assert "Regression gate: passed (metabolic_health)" in rendered
    assert "metabolic_health/weight-loss" in rendered
    assert "Expected source ranks:" in rendered
    assert payload["benchmark_id"] == "test-benchmark-v2"
    assert payload["domain_count"] == 1
    assert payload["macro_domain_recall_at_k"] == 1.0
    assert payload["regression_gate_passed"] is True
    assert payload["questions"][0]["question_id"] == "weight-loss"


def test_cli_writes_json_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    benchmark_path, database_path, evidence_path = _build_benchmark_inputs(tmp_path)
    output_path = tmp_path / "report.json"

    main(
        [
            "--benchmark",
            str(benchmark_path),
            "--database",
            str(database_path),
            "--evidence",
            str(evidence_path),
            "--format",
            "json",
            "--output",
            str(output_path),
        ]
    )

    assert json.loads(output_path.read_text(encoding="utf-8"))["question_count"] == 1
    assert "Benchmark report written:" in capsys.readouterr().out


def test_cli_exits_nonzero_for_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--benchmark", str(tmp_path / "missing.json")])

    assert exc_info.value.code == 1
    assert "Benchmark failed:" in capsys.readouterr().err


def test_committed_benchmark_is_a_retrieval_regression_gate() -> None:
    evaluation = evaluate_benchmark(
        load_benchmark(Path("data/retrieval_benchmark.json")),
        database_path=Path("data/knowledge_engine.sqlite3"),
        evidence_path=Path("data/evidence_records.jsonl"),
    )

    assert evaluation.question_count == 12
    assert evaluation.domain_count == 3
    assert evaluation.mean_recall_at_k == 1.0
    assert evaluation.mean_reciprocal_rank == pytest.approx(23 / 24)
    assert evaluation.macro_domain_recall_at_k == 1.0
    assert evaluation.macro_domain_reciprocal_rank == pytest.approx(23 / 24)
    assert evaluation.regression_gate_passed is True
    assert set(evaluation.gated_domain_ids) == {
        "glp1_weight_loss",
        "oncology_nsclc_checkpoint_inhibitors",
        "mental_health_mdd_antidepressants",
    }
    domain_mrr = {domain.domain_id: domain.mean_reciprocal_rank for domain in evaluation.domains}
    assert domain_mrr == {
        "glp1_weight_loss": 1.0,
        "oncology_nsclc_checkpoint_inhibitors": 0.875,
        "mental_health_mdd_antidepressants": 1.0,
    }
    assert all(
        expected.rank is not None and expected.rank <= evaluation.top_k
        for question in evaluation.questions
        for expected in question.expected_ranks
    )
