import csv
from pathlib import Path

import pytest

from tag_edgar.employee_report import (
    TOPIC_REVIEW_FIELDS,
    assert_deal_claim_links,
    assert_descriptive_claims,
    build_employee_report,
    lint_claims,
    lint_deal_claim_links,
    lint_representative_passage,
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
                "text": (
                    "At closing, the agreement provides continuing employees with specified "
                    "benefits and bonus protections."
                ),
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
    assert first.taxonomy_ready is False
    assert "**PASS**" in first.markdown
    assert "deal-1" in first.markdown
    assert "deal-2" in first.markdown
    assert "no stable topic assignment" in first.markdown
    assert "https://sec.gov/Archives/doc-1.htm" in first.markdown
    assert "([Employee Matters](https://sec.gov/Archives/doc-1.htm))" in first.markdown
    deal_lines = [line for line in first.markdown.splitlines() if "deal-1" in line]
    assert deal_lines
    assert all("](https://" in line for line in deal_lines)
    assert "descriptive-only" in first.markdown
    assert first.topic_review_rows[0]["representative_passage_ids"] == "p-1"
    assert first.topic_review_rows[0]["passage_count"] == "1"
    assert first.topic_review_rows[0]["deal_count"] == "1"
    assert first.topic_review_rows[0]["representative_quality_status"] == "pass"
    assert first.topic_review_rows[0]["representative_fit_status"] == "pending"
    assert first.topic_review_rows[0]["coherence_score_1_to_5"] == ""
    assert first.topic_review_rows[0]["review_status"] == "pending"
    assert "human_review / representative_theme_fit: NOT_APPLICABLE" in first.markdown
    assert "PENDING HUMAN REVIEW" in first.markdown
    assert "taxonomy withheld" in first.markdown


def test_failed_diagnostic_produces_an_explicit_fail_verdict(tmp_path: Path) -> None:
    report = build_employee_report(
        *_inputs(tmp_path, gate_status="fail"), expected_deal_count=2
    )

    assert report.gate_passed is False
    assert "**FAIL**" in report.markdown
    assert "do not present it as a validated taxonomy" in report.markdown


def test_non_substantive_representative_forces_gate_failure_and_withholds_taxonomy(
    tmp_path: Path,
) -> None:
    inputs = list(_inputs(tmp_path))
    passages = inputs[1]
    rows = list(csv.DictReader(passages.open(newline="", encoding="utf-8")))
    rows[0]["heading"] = "Chief Executive Officer"
    rows[0]["text"] = "We lost you Franco."
    _write(passages, list(rows[0]), rows)

    report = build_employee_report(*inputs, expected_deal_count=2)

    assert report.gate_passed is False
    assert "report_quality / representative_substantiveness: FAIL" in report.markdown
    assert "diagnostic assignments; taxonomy withheld" in report.markdown
    assert "discovered topics" not in report.markdown
    assert report.topic_review_rows[0]["representative_quality_status"] == "fail"
    assert "call_transcript_noise" in report.topic_review_rows[0][
        "representative_quality_notes"
    ]


def test_report_requires_the_complete_deal_roster(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly 10 deals"):
        build_employee_report(*_inputs(tmp_path))


def test_report_rejects_a_passage_source_not_retrieved_for_its_document(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    passages = inputs[1]
    rows = list(csv.DictReader(passages.open(newline="", encoding="utf-8")))
    rows[0]["source_url"] = "https://www.sec.gov/Archives/not-the-document.htm"
    _write(passages, list(rows[0]), rows)

    with pytest.raises(ValueError, match="does not match"):
        build_employee_report(*inputs, expected_deal_count=2)


def test_report_rejects_a_non_sec_source_even_when_document_and_passage_match(
    tmp_path: Path,
) -> None:
    inputs = list(_inputs(tmp_path))
    documents = inputs[0]
    passages = inputs[1]
    topics = inputs[2]
    document_rows = list(csv.DictReader(documents.open(newline="", encoding="utf-8")))
    passage_rows = list(csv.DictReader(passages.open(newline="", encoding="utf-8")))
    topic_rows = list(csv.DictReader(topics.open(newline="", encoding="utf-8")))
    document_rows[0]["url"] = "https://example.com/document"
    passage_rows[0]["source_url"] = "https://example.com/document"
    topic_rows[1]["source_url"] = "https://example.com/document"
    _write(documents, list(document_rows[0]), document_rows)
    _write(passages, list(passage_rows[0]), passage_rows)
    _write(topics, list(topic_rows[0]), topic_rows)

    with pytest.raises(ValueError, match="HTTPS SEC URL"):
        build_employee_report(*inputs, expected_deal_count=2)


def test_deal_claim_link_lint_rejects_unlinked_claims_and_allows_zero_states() -> None:
    bad = "Buyer–Target (deal-1) disclosed a package."
    zero = (
        "Buyer–Target (deal-1) — pipeline zero state; no document-content claim"
    )

    assert lint_deal_claim_links(bad, {"deal-1"})
    with pytest.raises(ValueError, match="lack an inline SEC source"):
        assert_deal_claim_links(bad, {"deal-1"})
    assert lint_deal_claim_links(zero, {"deal-1"}) == []


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


@pytest.mark.parametrize(
    ("text", "heading", "reason"),
    [
        ("We lost you Franco.", "CEO", "call_transcript_noise"),
        (") Stock-Based Compensation ($",
            "(in millions)",
            "generic_accounting_noise",
        ),
        (
            "Name: Paul Viera Title: Chief Executive Officer Address:",
            "EARNEST PARTNERS",
            "title_or_contact_block",
        ),
    ],
)
def test_representative_lint_detects_known_report_noise(
    text: str, heading: str, reason: str
) -> None:
    assert reason in lint_representative_passage(text, heading)


def test_representative_lint_accepts_substantive_employee_term() -> None:
    text = (
        "Upon closing, employees will receive the value of vested restricted stock units in cash."
    )

    assert lint_representative_passage(text, "Restricted Stock Units") == []


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (
            (
                "The company may retain copies of confidential information under its records "
                "retention policy."
            ),
            "privacy_or_ip_noise",
        ),
        (
            "The seller retains title and ownership of all intellectual property rights.",
            "non_human_retain_use",
        ),
        ("The studio expects to retain its players.", "non_human_retain_use"),
        ("We will retain a strong presence in Israel.", "non_human_retain_use"),
        (
        (
            "We provide non-GAAP information about non-cash expenses including stock-based "
                "compensation and varying valuation methodologies for award types."
            ),
            "generic_accounting_noise",
        ),
        (
            (
                "The merger may cause disruptions and adverse changes in relationships with "
                "customers, suppliers, and employees."
            ),
            "generic_risk_boilerplate",
        ),
        (
            (
                "Travis Dalton 19,876 1,888,220 24,361 1,661,364 Mark Erceg 44,244 "
                "4,203,180 86,408 8,208,760"
            ),
            "numeric_table_noise",
        ),
        (
            "First quarter revenue was $102.4 million and net retention rate was 115%.",
            "generic_financial_metric",
        ),
        (
            (
                "Permitted Liens include deposits under worker's compensation laws and "
                "unemployment insurance laws."
            ),
            "generic_legal_boilerplate",
        ),
        (
            "Platforms may restrict access and cause loss of our player base.",
            "no_human_capital_subject",
        ),
        (
            "Representative means any director, officer, employee, agent, or adviser of a party.",
            "definition_or_proxy_noise",
        ),
        (
            "Employees may institute a charge under employment discrimination laws.",
            "generic_litigation_language",
        ),
        (
            "Participating employees may contribute compensation to the savings plan.",
            "no_acquisition_employee_context",
        ),
        ("Converted Parent RSU", "too_short"),
        (
            (
                "The interests of directors and executive officers may be different from, "
                "or in addition to, those of other stockholders."
            ),
            "proxy_interest_or_counsel_noise",
        ),
        (
            (
                "The shares of common stock multiplied by the merger consideration of $56.00 "
                "per share determine the aggregate value."
            ),
            "aggregate_securities_valuation",
        ),
        (
            (
                "The company will cause its directors, officers, and employees not to solicit "
                "an acquisition proposal before the merger closes."
            ),
            "no_employee_arrangement_evidence",
        ),
        (
            (
                "Completion of the merger may trigger change-in-control provisions in certain "
                "commercial agreements and counterparties may terminate those agreements."
            ),
            "no_employee_arrangement_evidence",
        ),
    ],
)
def test_representative_lint_rejects_privacy_ip_and_non_human_retain_uses(
    text: str, reason: str
) -> None:
    assert reason in lint_representative_passage(text)


def test_representatives_skip_higher_weight_noise_for_substantive_primary_passage(
    tmp_path: Path,
) -> None:
    inputs = list(_inputs(tmp_path))
    passages = inputs[1]
    topics = inputs[2]
    passage_rows = list(csv.DictReader(passages.open(newline="", encoding="utf-8")))
    topic_rows = list(csv.DictReader(topics.open(newline="", encoding="utf-8")))
    passage_rows[0]["heading"] = "Records Retention"
    passage_rows[0]["text"] = "The company may retain copies of confidential information."
    topic_rows[0]["primary_topic"] = "true"
    topic_rows[0]["topic_weight"] = "0.7"
    topic_rows[1]["topic_weight"] = "0.99"
    _write(passages, list(passage_rows[0]), passage_rows)
    _write(topics, list(topic_rows[0]), topic_rows)

    report = build_employee_report(*inputs, expected_deal_count=2)

    assert report.topic_review_rows[0]["representative_passage_ids"] == "p-2"
    assert "p-1" not in report.markdown.split(
        "## Candidate-topic diagnostics and source-linked representative passages", 1
    )[1]


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
