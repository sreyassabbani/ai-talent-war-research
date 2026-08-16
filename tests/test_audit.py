import csv
from pathlib import Path

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
        ["deal_id", "filings", "documents", "relevant_documents", "evidence"],
        [
            {
                "deal_id": "one",
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
    assert rows[0]["automated_retention_compensation_hits"] == "1"
    assert rows[0]["manual_evidence_review_status"] == "pending"


def test_pilot_audit_merges_manual_coding(tmp_path: Path) -> None:
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
    coding = tmp_path / "coding.csv"
    _write(
        coding,
        [
            "deal_id",
            "manual_employee_term_code",
            "amount_or_named_package_publicly_disclosed",
            "source_url",
            "manual_review_status",
            "manual_finding",
        ],
        [
            {
                "deal_id": "one",
                "manual_employee_term_code": "specific_retention",
                "amount_or_named_package_publicly_disclosed": "yes",
                "source_url": "https://example.com",
                "manual_review_status": "triaged",
                "manual_finding": "Reviewed.",
            }
        ],
    )

    rows = pilot_audit_rows(review, runs, coding)

    assert rows[0]["manual_employee_term_code"] == "specific_retention"
    assert rows[0]["manual_review_status"] == "triaged"
