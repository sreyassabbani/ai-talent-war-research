"""Retrieval and inventory of deal documents with explicit per-document status.

Every attempted document gets exactly one terminal status: ``retrieved`` or
``failed:<reason>``. Nothing is silently skipped, so an overnight run can resume without
losing track of what remains.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .accessions import enumerate_documents
from .models import Filing
from .sec_client import SecClient  # noqa: F401 - re-exported for orchestrators

RETRIEVAL_FORMS = frozenset(
    {"8-K", "8-K/A", "425", "SC 14D9", "SC TO-T", "SC TO-C", "DEFM14A", "DEF 14A", "PREM14A"}
)
EXHIBIT_PRIORITY_PREFIXES: tuple[str, ...] = ("EX-99", "EX-2", "EX-10")
MAX_DOCUMENTS_PER_FILING = 6
MAX_FILINGS_PER_DEAL = 12
_HTML_TAG = re.compile(r"<(?:html|body|div|p|table|td|font)\b", re.IGNORECASE)

FAMILY_RULES: tuple[tuple[str, str], ...] = (
    ("EX-2", "merger_agreement"),
    ("EX-10", "employment_or_plan"),
    ("EX-99", "press_release_exhibit"),
    ("425", "prospectus_communication"),
    ("SC 14D9", "tender_recommendation"),
    ("SC TO", "tender_offer"),
    ("DEFM14A", "proxy_statement"),
    ("PREM14A", "proxy_statement"),
    ("DEF 14A", "proxy_statement"),
    ("8-K", "current_report_body"),
)


@dataclass(frozen=True)
class DocumentRecord:
    """Inventory row for one attempted document."""

    deal_id: str
    document_id: str
    accession_number: str
    form: str
    document_type: str
    family: str
    url: str
    status: str
    content_sha256: str
    char_count: int
    error: str


class GetClient(Protocol):
    """Duck type shared by :class:`SecClient` and offline test doubles."""

    def get(self, url: str) -> object: ...


def document_family(form: str, document_type: str | None) -> str:
    doc_type = (document_type or "").upper()
    for prefix, family in FAMILY_RULES:
        if doc_type.startswith(prefix):
            return family
    for prefix, family in FAMILY_RULES:
        if form.upper().startswith(prefix):
            return family
    return "other"


def html_to_text(content: bytes, content_type: str = "") -> str:
    """Extract readable text from HTML bodies; pass plain text through unchanged."""
    text = content.decode("utf-8", errors="replace")
    inspection_window = text[:100_000]
    is_html = "html" in content_type.casefold() or bool(_HTML_TAG.search(inspection_window))
    if not is_html:
        return text
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")
    for unwanted in soup.find_all(["script", "style", "noscript"]):
        unwanted.decompose()
    return soup.get_text("\n")


def candidate_documents(documents: Iterable) -> list:
    """Order documents by exhibit priority then primary flag, deterministically."""

    def sort_key(document) -> tuple[int, str]:
        doc_type = (document.document_type or "").upper()
        priority = next(
            (
                index
                for index, prefix in enumerate(EXHIBIT_PRIORITY_PREFIXES)
                if doc_type.startswith(prefix)
            ),
            len(EXHIBIT_PRIORITY_PREFIXES),
        )
        return (priority, "" if document.is_primary else document.document_name)

    return sorted(documents, key=sort_key)


def _record(
    deal_id: str,
    filing: Filing,
    document,
    url: str,
    status: str,
    sha256: str,
    plain_len: int,
    error: str,
) -> DocumentRecord:
    document_id = document.document_id if document is not None else ""
    document_type = document.document_type or "" if document is not None else ""
    return DocumentRecord(
        deal_id=deal_id,
        document_id=document_id,
        accession_number=filing.accession_number,
        form=filing.form,
        document_type=document_type,
        family=document_family(filing.form, document_type),
        url=url,
        status=status,
        content_sha256=sha256,
        char_count=plain_len,
        error=error,
    )


def retrieve_deal_documents(
    client: GetClient,
    *,
    deal_id: str,
    filings: list[Filing],
) -> tuple[list[tuple[str, str]], list[DocumentRecord]]:
    """Retrieve screening texts and inventory records for one deal's windowed filings.

    Returns ``(texts, records)`` where ``texts`` holds ``(document_id, plain_text)`` pairs
    for successfully parsed documents only.
    """
    texts: list[tuple[str, str]] = []
    records: list[DocumentRecord] = []
    ordered_filings = sorted(filings, key=lambda item: (item.filing_date, item.accession_number))[
        :MAX_FILINGS_PER_DEAL
    ]
    for filing in ordered_filings:
        try:
            documents = enumerate_documents(client, filing)  # type: ignore[arg-type]
        except Exception as error:  # noqa: BLE001 - recorded, never silently skipped
            records.append(
                _record(
                    deal_id,
                    filing,
                    None,
                    f"https://www.sec.gov/Archives/edgar/data/{int(filing.cik)}/"
                    f"{filing.accession_number.replace('-', '')}/",
                    "failed:index_enumeration",
                    "",
                    0,
                    str(error),
                )
            )
            continue

        selected = candidate_documents(documents)[:MAX_DOCUMENTS_PER_FILING]
        for document in selected:
            url = document.url
            try:
                response = client.get(url)  # type: ignore[attr-defined]
                content = getattr(response, "content", response)
                content_bytes = content if isinstance(content, bytes) else str(content).encode()
                sha256 = hashlib.sha256(content_bytes).hexdigest()
                content_type = str(getattr(response, "content_type", ""))
                plain = html_to_text(content_bytes, content_type)
            except Exception as error:  # noqa: BLE001 - recorded, never silently skipped
                records.append(
                    _record(deal_id, filing, document, url, "failed:retrieval", "", 0, str(error))
                )
                continue
            if not plain.strip():
                records.append(
                    _record(
                        deal_id,
                        filing,
                        document,
                        url,
                        "failed:empty_document",
                        sha256,
                        0,
                        "document body contained no extractable text",
                    )
                )
                continue
            records.append(
                _record(deal_id, filing, document, url, "retrieved", sha256, len(plain), "")
            )
            texts.append((document.document_id, plain))
    return texts, records
