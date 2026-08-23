import csv
import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from tag_edgar.cli import app
from tag_edgar.employee_topics import (
    AssignmentRow,
    DiagnosticRow,
    EmployeeTopicResult,
    TopicRow,
)
from tag_edgar.employee_workflow import (
    _provision_family_ids,
    analyze_employee_topics_workflow,
    build_employee_corpus_workflow,
    summarize_employee_topics_workflow,
)


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _review(path: Path) -> None:
    _write(
        path,
        ["deal_id", "acquirer_name", "target_name", "pilot_status"],
        [
            {
                "deal_id": "deal-1",
                "acquirer_name": "Buyer One",
                "target_name": "Target One",
                "pilot_status": "selected",
            },
            {
                "deal_id": "deal-2",
                "acquirer_name": "Buyer Two",
                "target_name": "Target Two",
                "pilot_status": "selected",
            },
            {
                "deal_id": "deal-3",
                "acquirer_name": "Buyer Three",
                "target_name": "Target Three",
                "pilot_status": "selected",
            },
        ],
    )


def _cached_document(
    runs: Path, cache: Path, deal_id: str, document_id: str, body: bytes
) -> None:
    url = f"https://www.sec.gov/Archives/{document_id}.htm"
    _write(
        runs / deal_id / "documents.csv",
        [
            "document_id",
            "accession_number",
            "description",
            "document_name",
            "document_type",
            "url",
            "is_primary",
        ],
        [
            {
                "document_id": document_id,
                "accession_number": f"accession-{document_id}",
                "description": "Merger agreement",
                "document_name": f"{document_id}.htm",
                "document_type": "EX-2.1",
                "url": url,
                "is_primary": "False",
            }
        ],
    )
    digest = hashlib.sha256(url.encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{digest}.body").write_bytes(body)
    (cache / f"{digest}.json").write_text(
        json.dumps({"content_type": "text/html"}), encoding="utf-8"
    )


def test_workflows_deduplicate_globally_but_propagate_topics_to_each_deal(
    monkeypatch, tmp_path: Path
) -> None:
    review = tmp_path / "review.csv"
    runs = tmp_path / "runs"
    cache = tmp_path / "cache"
    corpus_dir = tmp_path / "corpus"
    analysis_dir = tmp_path / "analysis"
    report_dir = tmp_path / "report"
    _review(review)
    body = b"<h2>Employee Matters</h2><p>Key employees receive a retention bonus.</p>"
    _cached_document(runs, cache, "deal-1", "doc-1", body)
    _cached_document(runs, cache, "deal-2", "doc-2", body)

    corpus_summary = build_employee_corpus_workflow(review, runs, corpus_dir, cache)

    passages = _rows(corpus_dir / "passages.csv")
    sources = _rows(corpus_dir / "passage_sources.csv")
    assert corpus_summary.counts["deals"] == 3
    assert len(passages) == 1
    assert len(sources) == 2
    assert {row["deal_id"] for row in sources} == {"deal-1", "deal-2"}
    assert passages[0]["inclusion_status"] == "included"
    assert passages[0]["raw_text"] == passages[0]["text"]

    passage = passages[0]
    fake_result = EmployeeTopicResult(
        status="modeled",
        reason=None,
        assignments=(
            AssignmentRow(
                passage_id=passage["passage_id"],
                deal_id=passage["deal_id"],
                document_id=passage["document_id"],
                document_family_id=passage["document_family_id"],
                source_url=passage["source_url"],
                topic_id="topic_1",
                topic_weight=1.0,
                primary_topic=True,
            ),
        ),
        topics=(
            TopicRow(
                topic_id="topic_1",
                top_terms=("retention bonus", "employees"),
                primary_passage_count=1,
                document_family_count=1,
                deal_count=1,
                coherence=0.4,
                stability_median_cosine=0.9,
                stability_recovery_rate=0.8,
            ),
        ),
        deal_topics=(),
        diagnostics=(
            DiagnosticRow("stability", "overall_recovery_rate", 0.8, "pass", "Measured."),
        ),
        sensitivity_assignments=(),
        stability=(),
    )
    monkeypatch.setattr(
        "tag_edgar.employee_workflow.analyze_employee_topics_csv",
        lambda _path, _config: fake_result,
    )

    analysis_summary = analyze_employee_topics_workflow(review, corpus_dir, analysis_dir)

    assert analysis_summary.status == "modeled"
    deal_topics = _rows(analysis_dir / "deal_topic_matrix.csv")
    assert {(row["deal_id"], row["topic_id"]) for row in deal_topics} == {
        ("deal-1", "topic_1"),
        ("deal-2", "topic_1"),
        ("deal-3", ""),
    }
    assert next(row for row in deal_topics if row["deal_id"] == "deal-2")[
        "normalized_weight"
    ] == "1"
    assert next(row for row in deal_topics if row["deal_id"] == "deal-3")[
        "zero_state"
    ] == "no_employee_passages"
    assert (analysis_dir / "deal_topic_heatmap.svg").read_text(encoding="utf-8").startswith(
        '<svg xmlns="http://www.w3.org/2000/svg"'
    )
    assert json.loads((analysis_dir / "analysis_manifest.json").read_text())["status"] == (
        "modeled"
    )

    report_summary = summarize_employee_topics_workflow(
        review, corpus_dir, analysis_dir, report_dir
    )

    assert report_summary.status == "pass"
    report = (report_dir / "employee_topics_report.md").read_text(encoding="utf-8")
    assert "Buyer Two–Target Two" in report
    assert "no employee passages" in report
    assert _rows(report_dir / "topic_review.csv")[0]["topic_id"] == "topic_1"


def test_employee_workflow_commands_are_exposed() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "build-employee-corpus" in result.stdout
    assert "analyze-employee-topics" in result.stdout
    assert "summarize-employee-topics" in result.stdout


def test_near_duplicate_legal_provisions_share_a_deterministic_family() -> None:
    base = (
        "employee matters continuing employees shall receive salary bonus benefits equity awards "
        "and vesting treatment under the agreement after closing subject to applicable law and "
        "company policies"
    )
    passages = [
        {"passage_id": "passage-a", "model_text": base},
        {"passage_id": "passage-b", "model_text": base.replace("company", "buyer")},
        {
            "passage_id": "passage-c",
            "model_text": "founder leadership reporting lines remain after closing",
        },
    ]

    first = _provision_family_ids(passages)
    second = _provision_family_ids(list(reversed(passages)))

    assert first == second
    assert first["passage-a"] == first["passage-b"]
    assert first["passage-a"] != first["passage-c"]
