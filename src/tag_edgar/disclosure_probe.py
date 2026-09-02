"""Probe EDGAR for the existence of transaction filings before any bulk retrieval.

One submissions index per acquirer answers the question that decides the whole sample: did this
buyer actually file something about this deal? A deal with no transaction filing in the event
window cannot contain employee-treatment language, so retrieving it spends requests for nothing.
Probing first turns a blind 1,060-deal crawl into a targeted one.

Two details matter for the probe to predict what retrieval will find:

* It uses :func:`tag_edgar.windows.event_window`, the same window the retrieval pipeline uses.
  A narrower window misses the merger proxies and tender-offer statements filed months after
  announcement, which is where much employee language lives. Take-Two's tender-offer statement
  for Zynga was filed 133 days after announcement.
* Exhibit types come from the filing-detail page through :func:`enumerate_documents`, not from
  the accession ``index.json``, whose ``type`` field holds the directory-listing icon name
  rather than the SEC exhibit type.

The probe also does the CIK confirmation work that a human did one deal at a time in the pilot.
When the acquirer's own filing names the target, the deal and the CIK match are corroborated by
the filer's own document rather than by name similarity. That is recorded as
``machine_target_name_in_acquirer_filing`` and is never described as human review.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .accessions import accession_directory_url, enumerate_documents
from .disclosure_pool import DisclosurePoolConfig
from .models import Filing
from .sec_client import SecClient
from .submissions import fetch_filings, normalized_cik
from .windows import event_window

__all__ = [
    "PROBE_FIELDS",
    "PROBE_STATUS_RANK",
    "ProbeOutcome",
    "distinctive_target_tokens",
    "probe_deal",
    "probe_row",
    "target_named_in",
    "write_probe_results",
]

PROBE_FIELDS = [
    "deal_id",
    "announcement_date",
    "effective_date",
    "acquirer_name",
    "target_name",
    "candidate_cik",
    "target_candidate_cik",
    "transaction_value_mil",
    "target_public_status",
    "probe_status",
    "window_start",
    "window_end",
    "windowed_filings",
    "probe_forms",
    "agreement_accession",
    "agreement_exhibit_types",
    "target_name_hit",
    "cik_confirmation_basis",
    "probe_note",
]

# Ranked best-to-worst. Retrieval order follows this rank so the richest deals land first.
PROBE_STATUS_RANK = {
    "agreement_exhibit": 0,
    "merger_proxy": 1,
    "announcement_only": 2,
    "no_transaction_filing": 3,
    "probe_failed": 4,
}

# Filings whose detail page is worth opening to look for the transaction agreement. The exhibit
# is nearly always attached to the announcement 8-K or carried by a registration statement.
_AGREEMENT_INDEX_LIMIT = 3
_ANNOUNCEMENT_DAYS = 21

_EXHIBIT_PREFIX = "EX-2."
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_GENERIC_TOKENS = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "corp",
        "corporation",
        "company",
        "co",
        "holdings",
        "holding",
        "group",
        "the",
        "and",
        "of",
        "plc",
        "sa",
        "ag",
        "nv",
        "gmbh",
        "lp",
        "limited",
        "technologies",
        "technology",
        "systems",
        "solutions",
        "software",
        "services",
        "international",
        "global",
        "usa",
        "new",
    }
)


@dataclass(frozen=True)
class ProbeOutcome:
    """One deal's probe result. ``status`` is the ranked outcome; the rest is its evidence."""

    status: str
    window_start: str
    window_end: str
    windowed_filings: int
    forms: tuple[str, ...]
    agreement_accession: str
    agreement_exhibit_types: tuple[str, ...]
    target_name_hit: str
    note: str


def distinctive_target_tokens(target_name: str) -> tuple[str, ...]:
    """Return the tokens of a target name that could identify it inside a filing.

    Corporate suffixes and industry words match almost any technology filing, so they cannot
    corroborate a deal. Only distinctive tokens count, and a name with none of them yields an
    empty tuple, which callers must treat as "cannot confirm" rather than "no match".
    """
    tokens = [token.lower() for token in _TOKEN.findall(target_name or "")]
    return tuple(token for token in tokens if len(token) > 2 and token not in _GENERIC_TOKENS)


def target_named_in(text: str, target_name: str) -> bool:
    """True when a distinctive token of the target name appears in the filing text."""
    tokens = distinctive_target_tokens(target_name)
    if not tokens:
        return False
    lowered = text.lower()
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered) for token in tokens
    )


def _agreement_candidates(filings: list[Filing], announced: date) -> list[Filing]:
    """Filings worth opening to look for an EX-2 transaction agreement, most likely first."""
    scored: list[tuple[int, int, Filing]] = []
    for filing in filings:
        distance = abs((filing.filing_date - announced).days)
        if filing.form in {"S-4", "S-4/A", "424B3"}:
            scored.append((0, distance, filing))
        elif filing.form in {"8-K", "8-K/A"} and distance <= _ANNOUNCEMENT_DAYS:
            scored.append((1, distance, filing))
    scored.sort(key=lambda item: (item[0], item[1], item[2].accession_number))
    return [filing for _, _, filing in scored[:_AGREEMENT_INDEX_LIMIT]]


def probe_deal(
    client: SecClient,
    row: dict[str, str],
    config: DisclosurePoolConfig,
    forms: frozenset[str],
    *,
    confirm_target_name: bool = True,
) -> ProbeOutcome:
    """Probe one deal: submissions index, event window, exhibit types, target-name check."""
    try:
        announced = date.fromisoformat(row["announcement_date"])
    except (KeyError, ValueError):
        return ProbeOutcome(
            "probe_failed", "", "", 0, (), "", (), "", "unparsable announcement date"
        )
    effective_raw = (row.get("effective_date") or "").strip()
    try:
        effective = date.fromisoformat(effective_raw) if effective_raw else None
    except ValueError:
        effective = None

    window = event_window(announced, effective)
    try:
        all_filings = fetch_filings(client, normalized_cik(row["candidate_cik"]))
    except (RuntimeError, ValueError, TypeError) as error:
        return ProbeOutcome(
            "probe_failed",
            window.start.isoformat(),
            window.end.isoformat(),
            0,
            (),
            "",
            (),
            "",
            f"submissions lookup failed: {error}",
        )

    windowed = sorted(
        (f for f in all_filings if window.start <= f.filing_date <= window.end and f.form in forms),
        key=lambda f: (f.filing_date, f.accession_number),
    )
    window_start, window_end = window.start.isoformat(), window.end.isoformat()
    if not windowed:
        return ProbeOutcome(
            "no_transaction_filing",
            window_start,
            window_end,
            0,
            (),
            "",
            (),
            "",
            "no configured form in the event window",
        )

    form_set = tuple(dict.fromkeys(filing.form for filing in windowed))
    agreement_accession = ""
    agreement_types: tuple[str, ...] = ()
    agreement_documents: list[str] = []
    for filing in _agreement_candidates(windowed, announced):
        try:
            documents = enumerate_documents(client, filing)
        except (RuntimeError, ValueError, TypeError):
            continue
        types = tuple(
            document.document_type
            for document in documents
            if (document.document_type or "").upper().startswith(_EXHIBIT_PREFIX)
        )
        if types:
            agreement_accession = filing.accession_number
            agreement_types = tuple(str(item) for item in types)
            agreement_documents = [
                document.url
                for document in documents
                if (document.document_type or "").upper().startswith(_EXHIBIT_PREFIX)
                or document.is_primary
            ]
            break

    proxy_filings = [filing for filing in windowed if filing.form in config.proxy_forms]
    if agreement_types:
        status = "agreement_exhibit"
    elif proxy_filings:
        status = "merger_proxy"
    elif any(filing.form in config.announcement_forms for filing in windowed):
        status = "announcement_only"
    else:
        status = "no_transaction_filing"

    # When no agreement exhibit was found, corroborate against the proxy or tender-offer
    # statement itself, which names the target in its own caption.
    if not agreement_documents:
        for filing in proxy_filings[:1]:
            if filing.primary_document:
                directory = accession_directory_url(filing.cik, filing.accession_number)
                agreement_documents = [f"{directory}{filing.primary_document}"]

    target_hit = "not_checked"
    if confirm_target_name and status in {"agreement_exhibit", "merger_proxy"}:
        target_name = row.get("target_name", "")
        if not distinctive_target_tokens(target_name):
            target_hit = "no_distinctive_target_tokens"
        else:
            target_hit = "no"
            for url in agreement_documents[:2]:
                try:
                    text = client.get(url).content.decode("utf-8", errors="replace")
                except (RuntimeError, ValueError):
                    continue
                if target_named_in(text, target_name):
                    target_hit = "yes"
                    break

    return ProbeOutcome(
        status=status,
        window_start=window_start,
        window_end=window_end,
        windowed_filings=len(windowed),
        forms=form_set,
        agreement_accession=agreement_accession,
        agreement_exhibit_types=agreement_types,
        target_name_hit=target_hit,
        note=window.status if window.status != "closing_observed" else "",
    )


def probe_row(row: dict[str, str], outcome: ProbeOutcome) -> dict[str, str]:
    basis = (
        "machine_target_name_in_acquirer_filing"
        if outcome.target_name_hit == "yes"
        else "machine_form_and_window_only"
    )
    return {
        "deal_id": row.get("deal_id", ""),
        "announcement_date": row.get("announcement_date", ""),
        "effective_date": row.get("effective_date", ""),
        "acquirer_name": row.get("acquirer_name", ""),
        "target_name": row.get("target_name", ""),
        "candidate_cik": row.get("candidate_cik", ""),
        "target_candidate_cik": row.get("target_candidate_cik", ""),
        "transaction_value_mil": row.get("transaction_value_mil", ""),
        "target_public_status": row.get("target_public_status", ""),
        "probe_status": outcome.status,
        "window_start": outcome.window_start,
        "window_end": outcome.window_end,
        "windowed_filings": str(outcome.windowed_filings),
        "probe_forms": "; ".join(outcome.forms),
        "agreement_accession": outcome.agreement_accession,
        "agreement_exhibit_types": "; ".join(outcome.agreement_exhibit_types),
        "target_name_hit": outcome.target_name_hit,
        "cik_confirmation_basis": basis,
        "probe_note": outcome.note,
    }


def write_probe_results(
    output_dir: Path, rows: list[dict[str, str]], manifest: dict[str, object]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "probe_results.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=PROBE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "probe_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
