from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

SUMMARY_FIELDS = [
    "deal_id",
    "acquirer_name",
    "target_name",
    "announcement_date",
    "effective_date",
    "sdc_form",
    "target_public_status",
    "transaction_value_mil",
    "candidate_cik",
    "filings_found",
    "documents_found",
    "relevant_documents_found",
    "automated_evidence_hits",
    "agreement_exhibit_found",
    "automated_retention_compensation_hits",
    "automated_employee_specificity_hits",
    "automated_exit_protection_hits",
    "manual_document_review_status",
    "manual_evidence_review_status",
    "manual_employee_term_code",
    "employee_amount_or_named_package_publicly_disclosed",
    "manual_evidence_source_url",
    "manual_review_status",
    "manual_summary_note",
]

_AGREEMENT_EXHIBIT = re.compile(r"^EX-2(?:\.|$)", re.IGNORECASE)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _summary_counts(path: Path) -> dict[str, dict[str, str]]:
    summary = _read_rows(path / "run_summary.csv")
    return {row["deal_id"]: row for row in summary}


def _manual_coding(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    rows = _read_rows(path)
    if any(not row.get("deal_id") for row in rows):
        raise ValueError("Manual coding CSV has a row without deal_id.")
    return {row["deal_id"]: row for row in rows}


def pilot_audit_rows(
    review_csv: Path, runs_dir: Path, manual_coding_csv: Path | None = None
) -> list[dict[str, str]]:
    """Summarize retrieval coverage while preserving the need for manual evidence review."""
    review_rows = _read_rows(review_csv)
    selected = [row for row in review_rows if row.get("pilot_status", "").lower() == "selected"]
    counts_by_deal = _summary_counts(runs_dir)
    coding_by_deal = _manual_coding(manual_coding_csv)
    output: list[dict[str, str]] = []
    for row in selected:
        deal_id = row["deal_id"]
        run_counts = counts_by_deal.get(deal_id, {})
        run_path = runs_dir / deal_id
        documents = _read_rows(run_path / "documents.csv") if run_path.exists() else []
        evidence = _read_rows(run_path / "evidence.csv") if run_path.exists() else []
        categories = Counter(item["category"] for item in evidence)
        agreement = any(
            _AGREEMENT_EXHIBIT.match(document["document_type"] or "") for document in documents
        )
        coding = coding_by_deal.get(deal_id, {})
        output.append(
            {
                "deal_id": deal_id,
                "acquirer_name": row["acquirer_name"],
                "target_name": row["target_name"],
                "announcement_date": row["announcement_date"],
                "effective_date": row["effective_date"],
                "sdc_form": row["sdc_form"],
                "target_public_status": row["target_public_status"],
                "transaction_value_mil": row["transaction_value_mil"],
                "candidate_cik": row["candidate_cik"],
                "filings_found": run_counts.get("filings", "0"),
                "documents_found": run_counts.get("documents", "0"),
                "relevant_documents_found": run_counts.get("relevant_documents", "0"),
                "automated_evidence_hits": run_counts.get("evidence", "0"),
                "agreement_exhibit_found": "candidate" if agreement else "not_found_in_retrieval",
                "automated_retention_compensation_hits": str(categories["retention_compensation"]),
                "automated_employee_specificity_hits": str(categories["employee_specificity"]),
                "automated_exit_protection_hits": str(categories["exit_protections"]),
                "manual_document_review_status": coding.get("manual_review_status", "pending"),
                "manual_evidence_review_status": coding.get("manual_review_status", "pending"),
                "manual_employee_term_code": coding.get("manual_employee_term_code", ""),
                "employee_amount_or_named_package_publicly_disclosed": coding.get(
                    "amount_or_named_package_publicly_disclosed", ""
                ),
                "manual_evidence_source_url": coding.get("source_url", ""),
                "manual_review_status": coding.get("manual_review_status", "pending"),
                "manual_summary_note": coding.get(
                    "manual_finding", "Automated counts are leads, not verified facts."
                ),
            }
        )
    return output
