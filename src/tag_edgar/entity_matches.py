from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

from .cik import TICKER_REGISTRY_URL, build_registry, entity_match_rows
from .models import EntityMatch
from .sec_client import SecClient

ProgressCallback = Callable[[int, int], None]


def count_deal_seeds(deals_seed_csv: Path) -> int:
    with deals_seed_csv.open(newline="", encoding="utf-8") as file:
        return sum(1 for _ in csv.DictReader(file))


def resolve_seed_file(
    client: SecClient,
    deals_seed_csv: Path,
    progress_callback: ProgressCallback | None = None,
) -> list[EntityMatch]:
    """Generate candidate rows for each recorded acquirer and non-empty target."""
    registry = build_registry(client.get_json(TICKER_REGISTRY_URL))
    total = count_deal_seeds(deals_seed_csv)
    with deals_seed_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required = {"deal_id", "acquirer_name", "acquirer_ticker", "target_name", "target_ticker"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("deals seed CSV lacks the expected canonical columns.")
        matches: list[EntityMatch] = []
        for completed, row in enumerate(reader, start=1):
            deal_id = row["deal_id"]
            matches.extend(
                entity_match_rows(
                    deal_id,
                    "acquirer",
                    row["acquirer_name"],
                    row["acquirer_ticker"] or None,
                    registry,
                )
            )
            target_name = row["target_name"] or None
            if target_name:
                matches.extend(
                    entity_match_rows(
                        deal_id,
                        "target",
                        target_name,
                        row["target_ticker"] or None,
                        registry,
                    )
                )
            if progress_callback is not None:
                progress_callback(completed, total)
    return matches
