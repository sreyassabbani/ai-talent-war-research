from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Deal:
    deal_id: str
    acquirer_cik: str
    announcement_date: date
    effective_date: date | None = None
    target_name: str | None = None


@dataclass(frozen=True)
class Filing:
    accession_number: str
    cik: str
    form: str
    filing_date: date
    report_date: date | None
    primary_document: str | None
    items: str | None = None


@dataclass(frozen=True)
class Document:
    document_id: str
    accession_number: str
    cik: str
    sequence: str | None
    description: str | None
    document_name: str
    document_type: str | None
    url: str
    is_primary: bool


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    deal_id: str
    document_id: str
    category: str
    pattern: str
    excerpt: str
    score: int


@dataclass(frozen=True)
class CikCandidate:
    cik: str
    sec_name: str
    ticker: str | None
    exchange: str | None
    match_method: str
    confidence: str


@dataclass(frozen=True)
class DealSeed:
    deal_id: str
    acquirer_name: str
    acquirer_ticker: str | None
    target_name: str | None
    target_ticker: str | None
    announcement_date: date
    effective_date: date | None
    source_row_number: int
    raw_source_row: str


@dataclass(frozen=True)
class EntityMatch:
    deal_id: str
    party_role: str
    source_name: str
    source_ticker: str | None
    candidate_cik: str | None
    sec_name: str | None
    sec_ticker: str | None
    exchange: str | None
    match_method: str
    confidence: str
    manual_status: str
    reviewer_note: str | None
