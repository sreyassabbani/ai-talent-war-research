from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .accessions import enumerate_documents, is_relevant_document
from .evidence import document_text, find_evidence
from .linking import deal_filing_links
from .models import Deal, DealFiling, Document, Evidence, Filing
from .sec_client import SecClient
from .settings import Settings
from .storage import write_csv
from .submissions import fetch_filings, normalized_cik, relevant_filings
from .windows import event_window


def run_vertical_slice(
    deal: Deal,
    settings: Settings,
    output_dir: Path,
    forms: frozenset[str] | None = None,
) -> dict[str, int]:
    """Retrieve transaction documents for every manually confirmed public deal party."""
    window = event_window(deal.announcement_date, deal.effective_date)
    party_ciks = [("acquirer", deal.acquirer_cik)]
    if deal.target_cik:
        party_ciks.append(("target", deal.target_cik))

    with SecClient(settings.user_agent, settings.cache_dir, settings.rate_per_second) as client:
        filings_by_cik: dict[str, list[Filing]] = {}
        filings_by_accession: dict[str, Filing] = {}
        party_counts = {"acquirer_filings": 0, "target_filings": 0}
        links: list[DealFiling] = []
        for party_role, cik in party_ciks:
            normalized_party_cik = normalized_cik(cik)
            if normalized_party_cik not in filings_by_cik:
                all_filings = fetch_filings(client, normalized_party_cik)
                filings_by_cik[normalized_party_cik] = relevant_filings(
                    all_filings, forms or settings.forms, window.start, window.end
                )
            party_filings = filings_by_cik[normalized_party_cik]
            party_counts[f"{party_role}_filings"] = len(party_filings)
            links.extend(
                deal_filing_links(
                    deal,
                    party_filings,
                    discovery_route=f"{party_role}_confirmed_cik",
                )
            )
            for filing in party_filings:
                filings_by_accession.setdefault(filing.accession_number, filing)

        filings = sorted(
            filings_by_accession.values(),
            key=lambda filing: (filing.filing_date, filing.accession_number),
        )
        documents: list[Document] = []
        for filing in filings:
            documents.extend(enumerate_documents(client, filing))

        relevant_documents = [
            document
            for document in documents
            if is_relevant_document(document, settings.document_prefixes)
        ]
        evidence: list[Evidence] = []
        for document in relevant_documents:
            text = document_text(client, document)
            evidence.extend(
                find_evidence(deal.deal_id, document, text, settings.patterns, deal.target_name)
            )

    deal_row = {
        **asdict(deal),
        "acquirer_cik": normalized_cik(deal.acquirer_cik),
        "target_cik": normalized_cik(deal.target_cik) if deal.target_cik else "",
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "window_status": window.status,
        "cik_match_confidence": "confirmed_required_for_vertical_slice",
        "retrieval_status": "complete",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_dict_csv(output_dir / "deals.csv", [deal_row])
    write_csv(
        output_dir / "filings.csv",
        filings,
        [
            "accession_number",
            "cik",
            "form",
            "filing_date",
            "report_date",
            "primary_document",
            "items",
        ],
    )
    write_csv(
        output_dir / "deal_filings.csv",
        links,
        [
            "deal_id",
            "accession_number",
            "discovery_route",
            "days_from_announcement",
            "days_from_effective",
            "automated_relevance_score",
            "manual_status",
            "reviewer_note",
        ],
    )
    write_csv(
        output_dir / "documents.csv",
        documents,
        [
            "document_id",
            "accession_number",
            "cik",
            "sequence",
            "description",
            "document_name",
            "document_type",
            "url",
            "is_primary",
        ],
    )
    write_csv(
        output_dir / "evidence.csv",
        evidence,
        [
            "evidence_id",
            "deal_id",
            "document_id",
            "category",
            "pattern",
            "excerpt",
            "score",
            "match_start",
            "match_end",
        ],
    )
    return {
        **party_counts,
        "filings": len(filings),
        "deal_filing_links": len(links),
        "documents": len(documents),
        "relevant_documents": len(relevant_documents),
        "evidence": len(evidence),
    }


def _write_dict_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
