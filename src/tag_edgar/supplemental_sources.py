"""Retrieve curated non-EDGAR primary sources for AI-transaction screening.

The SDC archive is a discovery universe, not evidence.  This module only reads an
explicitly curated source register and only accepts source classes that the project has
pre-approved.  Retrieved pages are cached by the shared HTTP client and remain subject to
the same target-linked AI screen as SEC documents.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .deal_retrieval import DocumentRecord, html_to_text

APPROVED_REVIEW_STATUS = "approved_for_machine_screening"
ALLOWED_SOURCE_QUALITIES = frozenset(
    {
        "official_company_announcement",
        "official_company_financial_statement",
        "official_company_press_release_distributor",
        "official_regulator_decision",
        "primary_sec_filing",
    }
)


@dataclass(frozen=True)
class SupplementalSource:
    """One curated source candidate with an explicit provenance classification."""

    deal_id: str
    source_url: str
    source_quality: str
    publisher: str
    publication_date: str
    source_title: str
    review_status: str
    notes: str
    approved_excerpt: str


def load_supplemental_sources(path: Path | None) -> dict[str, list[SupplementalSource]]:
    """Load approved HTTPS sources grouped by deal ID.

    Rows that are still proposed remain in the register for review but never enter the
    machine screen. Invalid approved rows fail loudly instead of being silently trusted.
    """
    if path is None or not path.exists():
        return {}
    grouped: dict[str, list[SupplementalSource]] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            source = SupplementalSource(
                deal_id=(row.get("deal_id") or "").strip(),
                source_url=(row.get("source_url") or "").strip(),
                source_quality=(row.get("source_quality") or "").strip(),
                publisher=(row.get("publisher") or "").strip(),
                publication_date=(row.get("publication_date") or "").strip(),
                source_title=(row.get("source_title") or "").strip(),
                review_status=(row.get("review_status") or "").strip(),
                notes=(row.get("notes") or "").strip(),
                approved_excerpt=(row.get("approved_excerpt") or "").strip(),
            )
            if source.review_status != APPROVED_REVIEW_STATUS:
                continue
            if not source.deal_id:
                raise ValueError(f"Approved supplemental source row {line_number} has no deal_id.")
            parsed = urlparse(source.source_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(
                    f"Approved supplemental source row {line_number} must use an HTTPS URL."
                )
            if source.source_quality not in ALLOWED_SOURCE_QUALITIES:
                raise ValueError(
                    f"Approved supplemental source row {line_number} has unsupported "
                    f"source_quality={source.source_quality!r}."
                )
            if len(source.approved_excerpt) > 2_000:
                raise ValueError(
                    f"Approved supplemental source row {line_number} has an excerpt over "
                    "2,000 characters."
                )
            grouped.setdefault(source.deal_id, []).append(source)
    for sources in grouped.values():
        sources.sort(key=lambda item: (item.source_quality, item.source_url))
    return grouped


def _document_id(url: str) -> str:
    return f"supp_{hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]}"


def retrieve_supplemental_documents(
    client: object,
    *,
    deal_id: str,
    sources: list[SupplementalSource],
    prefer_approved_excerpt: bool = False,
) -> tuple[list[tuple[str, str]], list[DocumentRecord], dict[str, str]]:
    """Retrieve curated pages with a terminal record for every attempted source."""
    texts: list[tuple[str, str]] = []
    records: list[DocumentRecord] = []
    quality_by_document: dict[str, str] = {}
    for source in sources:
        document_id = _document_id(source.source_url)
        family = (
            "regulator_decision"
            if source.source_quality == "official_regulator_decision"
            else "official_announcement"
        )
        fallback_error = ""
        if prefer_approved_excerpt and source.approved_excerpt:
            plain = source.approved_excerpt
            content_bytes = plain.encode("utf-8")
            fallback_error = "curated_excerpt_preferred_for_incremental_rescreen"
        else:
            try:
                response = client.get(source.source_url)  # type: ignore[attr-defined]
                content = getattr(response, "content", response)
                content_bytes = content if isinstance(content, bytes) else str(content).encode()
                content_type = str(getattr(response, "content_type", ""))
                plain = html_to_text(content_bytes, content_type)
                if not plain.strip():
                    raise ValueError("source body contained no extractable text")
            except Exception as error:  # noqa: BLE001 - terminal status per source
                if not source.approved_excerpt:
                    records.append(
                        DocumentRecord(
                            deal_id=deal_id,
                            document_id=document_id,
                            accession_number="",
                            form="OFFICIAL-SOURCE",
                            document_type=source.source_quality,
                            family=family,
                            url=source.source_url,
                            status="failed:retrieval",
                            content_sha256="",
                            char_count=0,
                            error=str(error),
                        )
                    )
                    continue
                plain = source.approved_excerpt
                content_bytes = plain.encode("utf-8")
                fallback_error = f"curated_excerpt_fallback_after_retrieval_error: {error}"
        records.append(
            DocumentRecord(
                deal_id=deal_id,
                document_id=document_id,
                accession_number="",
                form="OFFICIAL-SOURCE",
                document_type=source.source_quality,
                family=family,
                url=source.source_url,
                status="retrieved",
                content_sha256=hashlib.sha256(content_bytes).hexdigest(),
                char_count=len(plain),
                error=fallback_error,
            )
        )
        texts.append((document_id, plain))
        quality_by_document[document_id] = source.source_quality
    return texts, records, quality_by_document
