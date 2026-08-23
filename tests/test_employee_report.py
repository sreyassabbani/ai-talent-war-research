import csv
from pathlib import Path

import pytest

from tag_edgar.employee_report import (
    TOPIC_REVIEW_FIELDS,
    assert_descriptive_claims,
    build_employee_report,
    lint_claims,
    write_employee_report,
)


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _inputs(tmp_path: Path, *, gate_status: str = "pass") -> tuple[Path, ...]:
    documents = tmp_path / "documents.csv"
    passages = tmp_path / "passages.csv"
    topics = tmp_path / "topics.csv"
    deal_topics = tmp_path / "deal_topics.csv"
    diagnostics = tmp_path / "diagnostics.csv"
    _write(
        documents,
        ["document_id", "url"],
        [
            {"document_id": "doc-1", "url": "https://www.sec.gov/Archives/doc-1.htm"},
            {"document_id": "doc-2", "url": "https://www.sec.gov/Archives/doc-2.htm"},
        ],
    )
    _write(
        passages,
        ["passage_id", "deal_id", "document_id", "source_url", "heading", "text"],
        [
            {
                "passage_id": "p-1",
                "deal_id": "deal-1",
                "document_id": "doc-1",
                "source_url": "https://sec.gov/Archives/doc-1.htm",
                "heading": "Employee Matters",
                "text": "The agreement describes a retention pool for continuing employees.",
            },
            {
                "passage_id": "p-2",
                "deal_id": "deal-2",
                "document_id": "doc-2",
                "source_url": "https://www.sec.gov/Archives/doc-2.htm",
                "heading": "Benefits",
                "text": "The agreement describes benefits for continuing employees.",
            },
        ],
    )
    _write(
        topics,
        [
            "passage_id",
            "deal_id",
            "document_id",
            "source_url",
            "topic_id",
            "topic_weight",
            "primary_topic",
            "top_terms",
            "method",
            "coherence",
            "stability_recovery_rate",
        ],
        [
            {
                "passage_id": "p-2",
                "deal_id": "deal-2",
                "document_id": "doc-2",
                "source_url": "https://www.sec.gov/Archives/doc-2.htm",
                "topic_id": "topic-1",
                "topic_weight": "0.4",
                "primary_topic": "false",
                "top_terms": "benefits|continuing",
                "method": "nmf",
                "coherence": "0.31",
                "stability_recovery_rate": "0.8",
            },
            {
                "passage_id": "p-1",
                "deal_id": "deal-1",
                "document_id": "doc-1",
                "source_url": "https://sec.gov/Archives/doc-1.htm",
                "topic_id": "topic-1",
                "topic_weight": "0.9",
                "primary_topic": "true",
                "top_terms": "benefits|continuing",
                "method": "nmf",
                "coherence": "0.31",
                "stability_recovery_rate": "0.8",
            },
        ],
    )
    _write(
        deal_topics,
        [
            "deal_id",
            "acquirer_name",
            "target_name",
            "topic_id",
            "weight_sum",
            "normalized_weight",
            "primary_passage_count",
            "zero_state",
        ],
        [
            {
                "deal_id": "deal-2",
                "acquirer_name": "Buyer Two",
                "target_name": "Target Two",
                "topic_id": "",
                "weight_sum": "0",
                "normalized_weight": "0",
                "primary_passage_count": "0",
                "zero_state": "no_stable_topic_assignment",
            },
            {
                "deal_id": "deal-1",
                "acquirer_name": "Buyer One",
                "target_name": "Target One",
                "topic_id": "topic-1",
                "weight_sum": "0.9",
                "normalized_weight": "1",
                "primary_passage_count": "1",
                "zero_state": "",
            },
        ],
    )
    _write(
        diagnostics,
        ["stage", "name", "value", "status", "detail"],
        [
            {
                "stage": "stability",
                "name": "recovery",
                "value": "0.80",
                "status": gate_status,
                "detail": "Measured by leave-one-deal-out recovery.",
            }
        ],
    )
    return documents, passages, topics, deal_topics, diagnostics


def test_report_is_deterministic_source_linked_and_includes_zero_states(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)

    first = build_employee_report(*inputs, expected_deal_count=2)
    second = build_employee_report(*inputs, expected_deal_count=2)

    assert first == second
    assert first.gate_passed is True
    assert "**PASS**" in first.markdown
    assert "deal-1" in first.markdown
    assert "deal-2" in first.markdown
    assert "no stable topic assignment" in first.markdown
    assert "https://sec.gov/Archives/doc-1.htm" in first.markdown
    assert "descriptive-only" in first.markdown
    assert first.topic_review_rows[0]["representative_passage_ids"] == "p-1|p-2"
    assert first.topic_review_rows[0]["review_status"] == "pending"


def test_failed_diagnostic_produces_an_explicit_fail_verdict(tmp_path: Path) -> None:
    report = build_employee_report(
        *_inputs(tmp_path, gate_status="fail"), expected_deal_count=2
    )

    assert report.gate_passed is False
    assert "**FAIL**" in report.markdown
    assert "do not present it as a validated taxonomy" in report.markdown


def test_report_requires_the_complete_deal_roster(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly 10 deals"):
        build_employee_report(*_inputs(tmp_path))


def test_report_rejects_a_passage_source_not_retrieved_for_its_document(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    passages = inputs[1]
    rows = list(csv.DictReader(passages.open(newline="", encoding="utf-8")))
    rows[0]["source_url"] = "https://example.com/not-the-document"
    _write(passages, list(rows[0]), rows)

    with pytest.raises(ValueError, match="does not match"):
        build_employee_report(*inputs, expected_deal_count=2)


@pytest.mark.parametrize(
    ("claim", "category"),
    [
        ("This topic predicts layoffs.", "predictive"),
        ("The clause causes employees to leave.", "causal"),
        ("The retention program worked.", "actual_retention"),
        ("These filings prove the workforce outcome.", "unsupported_certainty"),
    ],
)
def test_claim_lint_rejects_non_descriptive_claims(claim: str, category: str) -> None:
    issues = lint_claims(claim)

    assert [issue.category for issue in issues] == [category]
    with pytest.raises(ValueError, match="Prohibited research claim"):
        assert_descriptive_claims(claim)


def test_claim_lint_allows_explicit_limitations_and_quoted_sources() -> None:
    text = (
        "This analysis does not predict workforce outcomes.\n\n"
        "> The buyer will retain key employees."
    )

    assert lint_claims(text) == []


def test_writer_emits_markdown_and_review_csv(tmp_path: Path) -> None:
    report = build_employee_report(*_inputs(tmp_path), expected_deal_count=2)
    markdown = tmp_path / "out" / "report.md"
    review = tmp_path / "out" / "topic_review.csv"

    write_employee_report(report, markdown, review)

    assert markdown.read_text(encoding="utf-8") == report.markdown
    with review.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == TOPIC_REVIEW_FIELDS
        rows = list(reader)
    assert rows == list(report.topic_review_rows)
