from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from .models import CikCandidate, EntityMatch
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
_LEADING_ARTICLES = {"the"}


@dataclass(frozen=True)
class TickerRegistry:
    by_ticker: dict[str, tuple[dict[str, str], ...]]
    by_normalized_name: dict[str, tuple[dict[str, str], ...]]


def normalize_company_name(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    while words and words[0] in _LEADING_ARTICLES:
        words.pop(0)
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


def build_registry(payload: dict[str, object]) -> TickerRegistry:
    by_ticker: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    by_normalized_name: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _registry_rows(payload):
        ticker = row["ticker"].upper().strip()
        if ticker:
            by_ticker[ticker].append(row)
        normalized_name = normalize_company_name(row["name"])
        if normalized_name:
            by_normalized_name[normalized_name].append(row)
    return TickerRegistry(
        by_ticker={key: tuple(value) for key, value in by_ticker.items()},
        by_normalized_name={key: tuple(value) for key, value in by_normalized_name.items()},
    )


def _candidate(row: dict[str, str], method: str, confidence: str) -> CikCandidate:
    return CikCandidate(
        cik=normalized_cik(row["cik"]),
        sec_name=row["name"],
        ticker=row["ticker"].upper().strip() or None,
        exchange=row["exchange"] or None,
        match_method=method,
        confidence=confidence,
    )


def resolve_registry_candidates(
    registry: TickerRegistry, company_name: str, ticker: str | None = None
) -> list[CikCandidate]:
    """Resolve by O(1) indexes; every candidate still requires manual confirmation."""
    normalized_name = normalize_company_name(company_name)
    normalized_ticker = ticker.upper().strip() if ticker else None
    ticker_rows = registry.by_ticker.get(normalized_ticker, ()) if normalized_ticker else ()
    if ticker_rows:
        return sorted(
            [
                _candidate(
                    row,
                    "exact_ticker",
                    "high" if normalize_company_name(row["name"]) == normalized_name else "medium",
                )
                for row in ticker_rows
            ],
            key=lambda candidate: (candidate.confidence, candidate.cik),
        )
    return sorted(
        [
            _candidate(row, "exact_normalized_name", "medium")
            for row in registry.by_normalized_name.get(normalized_name, ())
        ],
        key=lambda candidate: (candidate.confidence, candidate.cik),
    )


def resolve_candidates(
    payload: dict[str, object], company_name: str, ticker: str | None = None
) -> list[CikCandidate]:
    """Return transparent exact candidates. Every result still requires manual confirmation."""
    return resolve_registry_candidates(build_registry(payload), company_name, ticker)


def fetch_candidates(
    client: SecClient, company_name: str, ticker: str | None = None
) -> list[CikCandidate]:
    return resolve_candidates(client.get_json(TICKER_REGISTRY_URL), company_name, ticker)


def entity_match_rows(
    deal_id: str,
    party_role: str,
    company_name: str,
    ticker: str | None,
    registry: TickerRegistry | dict[str, object],
) -> list[EntityMatch]:
    indexed_registry = build_registry(registry) if isinstance(registry, dict) else registry
    candidates = resolve_registry_candidates(indexed_registry, company_name, ticker)
    if not candidates:
        return [
            EntityMatch(
                deal_id=deal_id,
                party_role=party_role,
                source_name=company_name,
                source_ticker=ticker,
                candidate_cik=None,
                sec_name=None,
                sec_ticker=None,
                exchange=None,
                match_method="no_exact_candidate",
                confidence="unresolved",
                manual_status="pending",
                reviewer_note=None,
            )
        ]
    return [
        EntityMatch(
            deal_id=deal_id,
            party_role=party_role,
            source_name=company_name,
            source_ticker=ticker,
            candidate_cik=candidate.cik,
            sec_name=candidate.sec_name,
            sec_ticker=candidate.ticker,
            exchange=candidate.exchange,
            match_method=candidate.match_method,
            confidence=candidate.confidence,
            manual_status="pending",
            reviewer_note=None,
        )
        for candidate in candidates
    ]
