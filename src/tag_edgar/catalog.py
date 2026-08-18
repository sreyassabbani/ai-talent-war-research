from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .ingest import _unique_headers
from .technology import TechnologyScreen

CATALOG_FIELDS = [
    "deal_id",
    "announcement_date",
    "effective_date",
    "acquirer_name",
    "acquirer_ticker",
    "target_name",
    "target_ticker",
    "sdc_form",
    "acquirer_primary_sic",
    "target_primary_sic",
    "target_public_status",
    "consideration_structure",
    "number_of_bidders",
    "transaction_value_mil",
    "transaction_value_effective_mil",
    "equity_value_mil",
    "candidate_cik",
    "candidate_sec_name",
    "candidate_sec_ticker",
    "candidate_exchange",
    "cik_match_method",
    "cik_match_confidence",
    "cik_manual_status",
    "cik_reviewer_note",
    "pilot_status",
    "technology_scope_status",
    "technology_screen_version",
    "technology_screen_reason",
    "pilot_reviewer_note",
]


def _read_sdc_rows(path: Path, metadata_rows: int) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        for _ in range(metadata_rows):
            next(reader, None)
        header_values = next(reader, None)
        if header_values is None:
            raise ValueError(f"{path} has no header row.")
        headers = _unique_headers(header_values)
        rows: list[dict[str, str]] = []
        for row_number, values in enumerate(reader, start=metadata_rows + 2):
            if not any(value.strip() for value in values):
                continue
            if len(values) != len(headers):
                raise ValueError(
                    f"{path} row {row_number}: expected {len(headers)} columns, found {len(values)}."
                )
            rows.append(dict(zip(headers, values, strict=True)))
    return rows


def _clean(value: str | None) -> str:
    return value.strip() if value else ""


def _best_acquirer_matches(path: Path) -> dict[str, dict[str, str]]:
    rank = {"high": 0, "medium": 1, "low": 2, "unresolved": 3}
    candidates_by_deal: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row.get("party_role") != "acquirer":
                continue
            deal_id = _clean(row.get("deal_id"))
            if not deal_id:
                continue
            candidates_by_deal[deal_id].append(row)

    best: dict[str, dict[str, str]] = {}
    for deal_id, candidates in candidates_by_deal.items():
        confirmed = [
            row for row in candidates if _clean(row.get("manual_status")).lower() == "confirmed"
        ]
        pool = confirmed or candidates
        best_rank = min(rank.get(_clean(row.get("confidence")), 99) for row in pool)
        top = [
            row for row in pool if rank.get(_clean(row.get("confidence")), 99) == best_rank
        ]
        distinct_ciks = {_clean(row.get("candidate_cik")) for row in top}
        distinct_ciks.discard("")
        if len(distinct_ciks) > 1:
            if confirmed:
                raise ValueError(
                    f"Deal {deal_id} has multiple manually confirmed acquirer CIK values."
                )
            ambiguous = top[0].copy()
            for field in (
                "candidate_cik",
                "sec_name",
                "sec_ticker",
                "exchange",
            ):
                ambiguous[field] = ""
            ambiguous["match_method"] = "ambiguous_candidates"
            ambiguous["confidence"] = "ambiguous"
            ambiguous["manual_status"] = "pending"
            ambiguous["reviewer_note"] = "Multiple equally ranked acquirer CIK candidates."
            best[deal_id] = ambiguous
            continue
        best[deal_id] = min(
            top,
            key=lambda row: (
                _clean(row.get("candidate_cik")),
                _clean(row.get("sec_ticker")),
                _clean(row.get("exchange")),
            ),
        )
    return best


def build_catalog(
    deals_seed_csv: Path, additional_csv: Path, entity_matches_csv: Path, metadata_rows: int
) -> list[dict[str, str]]:
    """Join deal seeds, the SDC supplemental export, and the best acquirer CIK candidate.

    This deliberately does not decide whether a deal is a technology acquisition or select it
    for SEC retrieval. Those are review decisions recorded in the output columns.
    """
    supplemental = {
        _clean(row.get("Deal Number")): row
        for row in _read_sdc_rows(additional_csv, metadata_rows)
        if _clean(row.get("Deal Number"))
    }
    matches = _best_acquirer_matches(entity_matches_csv)
    rows: list[dict[str, str]] = []
    with deals_seed_csv.open(newline="", encoding="utf-8") as file:
        for seed in csv.DictReader(file):
            deal_id = _clean(seed.get("deal_id"))
            main: dict[str, Any] = json.loads(seed["raw_source_row"])
            extra = supplemental.get(deal_id, {})
            match = matches.get(deal_id, {})
            rows.append(
                {
                    "deal_id": deal_id,
                    "announcement_date": _clean(seed.get("announcement_date")),
                    "effective_date": _clean(seed.get("effective_date")),
                    "acquirer_name": _clean(seed.get("acquirer_name")),
                    "acquirer_ticker": _clean(seed.get("acquirer_ticker")),
                    "target_name": _clean(seed.get("target_name")),
                    "target_ticker": _clean(seed.get("target_ticker")),
                    "sdc_form": _clean(main.get("Form")),
                    "acquirer_primary_sic": _clean(main.get("Acquiror Primary SIC Code")),
                    "target_primary_sic": _clean(main.get("Target Primary SIC Code")),
                    "target_public_status": _clean(extra.get("Target Public Status")),
                    "consideration_structure": _clean(extra.get("Consideration Structure")),
                    "number_of_bidders": _clean(extra.get("Number of Bidders")),
                    "transaction_value_mil": _clean(main.get("Value of Transaction ($mil)")),
                    "transaction_value_effective_mil": _clean(
                        main.get("Value Based on Effective Date ($mil)")
                    ),
                    "equity_value_mil": _clean(main.get("Equity Value ($mil)")),
                    "candidate_cik": _clean(match.get("candidate_cik")),
                    "candidate_sec_name": _clean(match.get("sec_name")),
                    "candidate_sec_ticker": _clean(match.get("sec_ticker")),
                    "candidate_exchange": _clean(match.get("exchange")),
                    "cik_match_method": _clean(match.get("match_method")),
                    "cik_match_confidence": _clean(match.get("confidence")),
                    "cik_manual_status": _clean(match.get("manual_status")) or "pending",
                    "cik_reviewer_note": _clean(match.get("reviewer_note")),
                    "pilot_status": "not_selected",
                    "technology_scope_status": "pending",
                    "technology_screen_version": "",
                    "technology_screen_reason": "",
                    "pilot_reviewer_note": "",
                }
            )
    return rows


def _parse_iso(value: str) -> date:
    return date.fromisoformat(value)


def create_review_queue(
    catalog_csv: Path,
    screen: TechnologyScreen,
    start: date,
    end: date,
    limit: int,
) -> list[dict[str, str]]:
    """Make a purposive technology-deal queue for validating the retrieval pipeline."""
    with catalog_csv.open(newline="", encoding="utf-8") as file:
        candidates = [
            row
            for row in csv.DictReader(file)
            if row["cik_match_confidence"] in {"high", "medium"}
            and start <= _parse_iso(row["announcement_date"]) <= end
            and screen.rationale(row["target_primary_sic"]) is not None
        ]
    buckets: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        form = row["sdc_form"].strip().upper() or "missing form"
        form_group = "merger" if "MERGER" in form else "non-merger"
        public_group = (
            "public" if row["target_public_status"].strip().lower() == "public" else "non-public"
        )
        value_group = "value reported" if row["transaction_value_mil"].strip() else "value missing"
        buckets[(public_group, form_group, value_group)].append(row)

    def reported_value(row: dict[str, str]) -> float:
        try:
            return float(row["transaction_value_mil"].replace(",", ""))
        except ValueError:
            return -1.0

    for rows in buckets.values():
        rows.sort(
            key=lambda row: (
                reported_value(row),
                row["cik_match_confidence"] == "high",
                row["announcement_date"],
                row["deal_id"],
            ),
            reverse=True,
        )

    selected: list[dict[str, str]] = []
    while len(selected) < limit and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(selected) < limit:
                row = buckets[key].pop(0).copy()
                row["pilot_status"] = "review"
                row["technology_scope_status"] = "candidate_in_scope"
                row["technology_screen_version"] = screen.version
                row["technology_screen_reason"] = screen.rationale(row["target_primary_sic"]) or ""
                row["pilot_reviewer_note"] = (
                    "Validation candidate only: confirm CIK and technology classification before selection."
                )
                selected.append(row)
    return selected
