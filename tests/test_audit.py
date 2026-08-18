import csv
from pathlib import Path

import pytest

from tag_edgar.audit import pilot_audit_rows


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_pilot_audit_flags_an_agreement_without_treating_hits_as_verified(tmp_path: Path) -> None:
    review = tmp_path / "review.csv"
    _write(
        review,
        [
            "deal_id",
            "pilot_status",
            "acquirer_name",
            "target_name",
            "announcement_date",
            "effective_date",
            "sdc_form",
            "target_public_status",
            "transaction_value_mil",
            "candidate_cik",
        ],
        [
            {
                "deal_id": "one",
                "pilot_status": "selected",
                "acquirer_name": "Buyer",
                "target_name": "Target",
                "announcement_date": "2022-01-01",
                "effective_date": "",
                "sdc_form": "Merger",
                "target_public_status": "Public",
                "transaction_value_mil": "10",
                "candidate_cik": "1",
            }
        ],
    )
    runs = tmp_path / "runs"
    _write(
        runs / "run_summary.csv",
        [
            "deal_id",
            "acquirer_filings",
            "target_filings",
            "filings",
            "documents",
            "relevant_documents",
            "evidence",
        ],
        [
            {
                "deal_id": "one",
                "acquirer_filings": "1",
                "target_filings": "2",
                "filings": "1",
                "documents": "2",
                "relevant_documents": "1",
                "evidence": "3",
            }
        ],
    )
    _write(
        runs / "one" / "documents.csv",
        ["document_type"],
        [{"document_type": "EX-2.1"}, {"document_type": "EX-23.1"}],
    )
    _write(
        runs / "one" / "evidence.csv",
        ["category"],
        [{"category": "retention_compensation"}, {"category": "exit_protections"}],
    )

    rows = pilot_audit_rows(review, runs)

    assert rows[0]["agreement_exhibit_found"] == "candidate"
    assert rows[0]["acquirer_filings_found"] == "1"
    assert rows[0]["target_filings_found"] == "2"
    assert rows[0]["automated_retention_compensation_hits"] == "1"
    assert rows[0]["manual_evidence_review_status"] == "pending"


def _complete_manual_inputs(
    tmp_path: Path, source_url: str = "https://www.sec.gov/Archives/deal/exhibit.htm"
) -> tuple[Path, Path, Path]:
    review = tmp_path / "review.csv"
    _write(
        review,
        [
            "deal_id",
            "pilot_status",
            "acquirer_name",
            "target_name",
            "announcement_date",
            "effective_date",
            "sdc_form",
            "target_public_status",
            "transaction_value_mil",
            "candidate_cik",
        ],
        [
            {
                "deal_id": "one",
                "pilot_status": "selected",
                "acquirer_name": "Buyer",
                "target_name": "Target",
                "announcement_date": "2022-01-01",
                "effective_date": "",
                "sdc_form": "Merger",
                "target_public_status": "Public",
                "transaction_value_mil": "10",
                "candidate_cik": "1",
            }
        ],
    )
    runs = tmp_path / "runs"
    _write(runs / "run_summary.csv", ["deal_id"], [{"deal_id": "one"}])
    _write(
        runs / "one" / "documents.csv",
        ["document_type", "url"],
        [
            {
                "document_type": "EX-2.1",
                "url": "https://www.sec.gov/Archives/deal/exhibit.htm",
            }
        ],
    )
    _write(runs / "one" / "evidence.csv", ["category"], [])
    coding = tmp_path / "coding.csv"
    _write(
        coding,
        [
            "deal_id",
            "manual_document_review_status",
            "manual_evidence_review_status",
            "manual_employee_term_code",
            "amount_or_named_package_publicly_disclosed",
            "source_url",
            "manual_review_status",
            "manual_finding",
        ],
        [
            {
                "deal_id": "one",
                "manual_document_review_status": "reviewed",
                "manual_evidence_review_status": "reviewed",
                "manual_employee_term_code": "specific_retention",
                "amount_or_named_package_publicly_disclosed": "yes",
                "source_url": source_url,
                "manual_review_status": "triaged",
                "manual_finding": "Reviewed.",
            }
        ],
    )
    return review, runs, coding


def test_pilot_audit_merges_manual_coding(tmp_path: Path) -> None:
    review, runs, coding = _complete_manual_inputs(tmp_path)

    rows = pilot_audit_rows(review, runs, coding)

    assert rows[0]["manual_employee_term_code"] == "specific_retention"
    assert rows[0]["manual_review_status"] == "triaged"
    assert rows[0]["manual_document_review_status"] == "reviewed"
    assert rows[0]["manual_evidence_review_status"] == "reviewed"


def test_pilot_audit_rejects_a_manual_source_not_retrieved_for_the_deal(
    tmp_path: Path,
) -> None:
    review, runs, coding = _complete_manual_inputs(tmp_path, "https://example.com/not-sec.htm")

    with pytest.raises(ValueError, match="HTTPS SEC URL"):
        pilot_audit_rows(review, runs, coding)


def test_pilot_audit_rejects_duplicate_manual_deal_ids(tmp_path: Path) -> None:
    review, runs, coding = _complete_manual_inputs(tmp_path)
    rows = coding.read_text(encoding="utf-8").splitlines()
    coding.write_text("\n".join([*rows, rows[-1]]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate deal_id"):
        pilot_audit_rows(review, runs, coding)
