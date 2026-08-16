from __future__ import annotations

import re

from .models import CikCandidate
from .sec_client import SecClient
from .submissions import normalized_cik

TICKER_REGISTRY_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_LEGAL_SUFFIXES = {
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "llc",
    "plc",
    "sa",
}


def normalize_company_name(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    while words and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def _registry_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    fields = payload.get("fields")
    data = payload.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        raise TypeError("SEC ticker registry did not contain fields and data arrays.")
    labels = [str(field) for field in fields]
    required = {"cik", "name", "ticker", "exchange"}
    if not required.issubset(labels):
        raise ValueError("SEC ticker registry has an unexpected field layout.")

    rows: list[dict[str, str]] = []
    for values in data:
        if not isinstance(values, list) or len(values) != len(labels):
            continue
        rows.append({label: str(value) for label, value in zip(labels, values, strict=True)})
    return rows


def resolve_candidates(
    payload: dict[str, object], company_name: str, ticker: str | None = None
) -> list[CikCandidate]:
    """Return transparent exact candidates. Every result still requires manual confirmation."""
    rows = _registry_rows(payload)
    normalized_name = normalize_company_name(company_name)
    normalized_ticker = ticker.upper().strip() if ticker else None
    candidates: list[CikCandidate] = []

    for row in rows:
        row_name = normalize_company_name(row["name"])
        row_ticker = row["ticker"].upper().strip() or None
        if normalized_ticker and row_ticker == normalized_ticker:
            candidates.append(
                CikCandidate(
                    cik=normalized_cik(row["cik"]),
                    sec_name=row["name"],
                    ticker=row_ticker,
                    exchange=row["exchange"] or None,
                    match_method="exact_ticker",
                    confidence="high" if row_name == normalized_name else "medium",
                )
            )
        elif row_name == normalized_name:
            candidates.append(
                CikCandidate(
                    cik=normalized_cik(row["cik"]),
                    sec_name=row["name"],
                    ticker=row_ticker,
                    exchange=row["exchange"] or None,
                    match_method="exact_normalized_name",
                    confidence="medium",
                )
            )

    return sorted(candidates, key=lambda candidate: (candidate.confidence, candidate.cik))


def fetch_candidates(
    client: SecClient, company_name: str, ticker: str | None = None
) -> list[CikCandidate]:
    return resolve_candidates(client.get_json(TICKER_REGISTRY_URL), company_name, ticker)
