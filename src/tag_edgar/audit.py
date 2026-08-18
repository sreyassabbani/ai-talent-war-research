from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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
    "target_candidate_cik",
    "acquirer_filings_found",
    "target_filings_found",
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
_MANUAL_CODING_FIELDS = {
    "deal_id",
    "manual_document_review_status",
    "manual_evidence_review_status",
    "manual_employee_term_code",
    "amount_or_named_package_publicly_disclosed",
    "source_url",
    "manual_review_status",
    "manual_finding",
}
_STAGE_REVIEW_STATUSES = {"pending", "in_progress", "reviewed", "not_applicable"}
_OVERALL_REVIEW_STATUSES = {"pending", "in_progress", "triaged", "complete"}
_COMPLETED_OVERALL_STATUSES = {"triaged", "complete"}
_COMPLETED_STAGE_STATUSES = {"reviewed", "not_applicable"}
_DISCLOSURE_VALUES = {"yes", "no", "unknown", "not_applicable"}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _summary_counts(path: Path) -> dict[str, dict[str, str]]:
    summary = _read_rows(path / "run_summary.csv")
    return {row["deal_id"]: row for row in summary}


def _manual_coding(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing_fields = _MANUAL_CODING_FIELDS - set(reader.fieldnames or ())
        if missing_fields:
            raise ValueError(
                f"Manual coding CSV is missing required columns: {sorted(missing_fields)}"
            )
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if any(not row.get("deal_id") for row in rows):
        raise ValueError("Manual coding CSV has a row without deal_id.")
    deal_ids = [row["deal_id"] for row in rows]
    duplicates = sorted(deal_id for deal_id, count in Counter(deal_ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"Manual coding CSV has duplicate deal_id values: {duplicates}")
    for row in rows:
        deal_id = row["deal_id"]
        for field in ("manual_document_review_status", "manual_evidence_review_status"):
            if row[field] not in _STAGE_REVIEW_STATUSES:
                raise ValueError(f"Manual coding for {deal_id} has invalid {field}={row[field]!r}.")
        if row["manual_review_status"] not in _OVERALL_REVIEW_STATUSES:
            raise ValueError(
                f"Manual coding for {deal_id} has invalid "
                f"manual_review_status={row['manual_review_status']!r}."
            )
        disclosure = row["amount_or_named_package_publicly_disclosed"]
        if disclosure and disclosure not in _DISCLOSURE_VALUES:
            raise ValueError(
                f"Manual coding for {deal_id} has invalid disclosure value={disclosure!r}."
            )
    return {row["deal_id"]: row for row in rows}


def _canonical_sec_url(value: str) -> str:
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or not (host == "sec.gov" or host.endswith(".sec.gov")):
        raise ValueError(f"Manual evidence source must be an HTTPS SEC URL, got {value!r}.")
    normalized_host = "sec.gov" if host in {"sec.gov", "www.sec.gov"} else host
    return urlunsplit(("https", normalized_host, parts.path.rstrip("/"), "", ""))


def _validate_completed_coding(
    deal_id: str, coding: dict[str, str], documents: list[dict[str, str]]
) -> None:
    if coding["manual_review_status"] not in _COMPLETED_OVERALL_STATUSES:
        return
    for field in ("manual_document_review_status", "manual_evidence_review_status"):
        if coding[field] not in _COMPLETED_STAGE_STATUSES:
            raise ValueError(
                f"Manual coding for {deal_id} cannot be complete while {field}={coding[field]!r}."
            )
    for field in (
        "manual_employee_term_code",
        "amount_or_named_package_publicly_disclosed",
        "source_url",
        "manual_finding",
    ):
        if not coding[field]:
            raise ValueError(f"Completed manual coding for {deal_id} requires {field}.")

    source_url = _canonical_sec_url(coding["source_url"])
    retrieved_urls = {
        _canonical_sec_url(document["url"])
        for document in documents
        if document.get("url", "").strip()
    }
    if source_url not in retrieved_urls:
        raise ValueError(
            f"Manual evidence source for {deal_id} is not one of that deal's retrieved documents."
        )


def pilot_audit_rows(
    review_csv: Path, runs_dir: Path, manual_coding_csv: Path | None = None
) -> list[dict[str, str]]:
    """Summarize retrieval coverage while preserving the need for manual evidence review."""
    review_rows = _read_rows(review_csv)
    selected = [row for row in review_rows if row.get("pilot_status", "").lower() == "selected"]
    counts_by_deal = _summary_counts(runs_dir)
    coding_by_deal = _manual_coding(manual_coding_csv)
    selected_ids = {row["deal_id"] for row in selected}
    unknown_coding_ids = sorted(set(coding_by_deal) - selected_ids)
    if unknown_coding_ids:
        raise ValueError(
            f"Manual coding contains deal_id values that are not selected: {unknown_coding_ids}"
        )
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
        if coding:
            _validate_completed_coding(deal_id, coding, documents)
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
                "target_candidate_cik": row.get("target_candidate_cik", ""),
                "acquirer_filings_found": run_counts.get("acquirer_filings", "0"),
                "target_filings_found": run_counts.get("target_filings", "0"),
                "filings_found": run_counts.get("filings", "0"),
                "documents_found": run_counts.get("documents", "0"),
                "relevant_documents_found": run_counts.get("relevant_documents", "0"),
                "automated_evidence_hits": run_counts.get("evidence", "0"),
                "agreement_exhibit_found": "candidate" if agreement else "not_found_in_retrieval",
                "automated_retention_compensation_hits": str(categories["retention_compensation"]),
                "automated_employee_specificity_hits": str(categories["employee_specificity"]),
                "automated_exit_protection_hits": str(categories["exit_protections"]),
                "manual_document_review_status": coding.get(
                    "manual_document_review_status", "pending"
                ),
                "manual_evidence_review_status": coding.get(
                    "manual_evidence_review_status", "pending"
                ),
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
