from __future__ import annotations

from datetime import date

from .models import Filing
from .sec_client import SecClient


def normalized_cik(cik: str) -> str:
    digits = "".join(character for character in cik if character.isdigit())
    if not digits:
        raise ValueError("CIK must contain at least one digit.")
    return digits.zfill(10)


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{normalized_cik(cik)}.json"


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    return date.fromisoformat(value)


def _records(payload: dict[str, object], cik: str) -> list[Filing]:
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else payload
    if not isinstance(recent, dict):
        return []
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        return []

    result: list[Filing] = []
    for index, accession in enumerate(accessions):
        if not isinstance(accession, str):
            continue
        filing_date = _parse_date(_at(recent, "filingDate", index))
        form = _at(recent, "form", index)
        if filing_date is None or not isinstance(form, str):
            continue
        primary = _at(recent, "primaryDocument", index)
        items = _at(recent, "items", index)
        result.append(
            Filing(
                accession_number=accession,
                cik=normalized_cik(cik),
                form=form.upper(),
                filing_date=filing_date,
                report_date=_parse_date(_at(recent, "reportDate", index)),
                primary_document=primary if isinstance(primary, str) and primary else None,
                items=items if isinstance(items, str) and items else None,
            )
        )
    return result


def _at(data: dict[str, object], key: str, index: int) -> object:
    values = data.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def fetch_filings(client: SecClient, cik: str) -> list[Filing]:
    """Fetch current and historical submission history for one filer."""
    payload = client.get_json(submissions_url(cik))
    result = _records(payload, cik)
    filings = payload.get("filings")
    if not isinstance(filings, dict):
        return result
    historical_files = filings.get("files")
    if not isinstance(historical_files, list):
        return result
    for file_info in historical_files:
        if not isinstance(file_info, dict) or not isinstance(file_info.get("name"), str):
            continue
        historical_url = f"https://data.sec.gov/submissions/{file_info['name']}"
        result.extend(_records(client.get_json(historical_url), cik))
    return result


def relevant_filings(
    filings: list[Filing], forms: frozenset[str], start: date, end: date
) -> list[Filing]:
    return sorted(
        (
            filing
            for filing in filings
            if start <= filing.filing_date <= end and filing.form in forms
        ),
        key=lambda filing: (filing.filing_date, filing.accession_number),
    )
