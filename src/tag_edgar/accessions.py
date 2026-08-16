from __future__ import annotations

import hashlib
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Document, Filing
from .sec_client import SecClient
from .submissions import normalized_cik


def accession_directory_url(cik: str, accession_number: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(normalized_cik(cik))}/{accession_number.replace('-', '')}/"


def filing_index_url(cik: str, accession_number: str) -> str:
    return f"{accession_directory_url(cik, accession_number)}{accession_number}-index.html"


def _document_id(accession_number: str, document_name: str) -> str:
    digest = hashlib.sha256(f"{accession_number}:{document_name}".encode()).hexdigest()[:16]
    return f"doc_{digest}"


def enumerate_documents(client: SecClient, filing: Filing) -> list[Document]:
    """Parse the SEC filing-detail page to enumerate submitted documents and exhibits."""
    index_url = filing_index_url(filing.cik, filing.accession_number)
    html = client.get(index_url).content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    directory_url = accession_directory_url(filing.cik, filing.accession_number)
    documents: list[Document] = []

    for table in soup.find_all("table"):
        headings = [heading.get_text(" ", strip=True).lower() for heading in table.find_all("th")]
        if "document" not in headings or "type" not in headings:
            continue
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            link = cells[2].find("a")
            href = link.get("href") if link is not None else None
            if not isinstance(href, str):
                continue
            assert link is not None
            document_name = link.get_text(" ", strip=True)
            if not document_name:
                continue
            sequence = cells[0].get_text(" ", strip=True) or None
            description = cells[1].get_text(" ", strip=True) or None
            document_type = cells[3].get_text(" ", strip=True).upper() or None
            documents.append(
                Document(
                    document_id=_document_id(filing.accession_number, document_name),
                    accession_number=filing.accession_number,
                    cik=filing.cik,
                    sequence=sequence,
                    description=description,
                    document_name=document_name,
                    document_type=document_type,
                    url=urljoin(directory_url, href),
                    is_primary=document_name == filing.primary_document,
                )
            )

    unique: dict[str, Document] = {document.document_id: document for document in documents}
    return list(unique.values())


def is_relevant_document(document: Document, prefixes: tuple[str, ...]) -> bool:
    document_type = document.document_type or ""
    return document.is_primary or any(document_type.startswith(prefix) for prefix in prefixes)
