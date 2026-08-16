from __future__ import annotations

import csv
from pathlib import Path

from .cik import TICKER_REGISTRY_URL, entity_match_rows
from .models import EntityMatch
from .sec_client import SecClient


def resolve_seed_file(client: SecClient, deals_seed_csv: Path) -> list[EntityMatch]:
    """Generate candidate rows for each recorded acquirer and non-empty target."""
    registry = client.get_json(TICKER_REGISTRY_URL)
    with deals_seed_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required = {"deal_id", "acquirer_name", "acquirer_ticker", "target_name", "target_ticker"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("deals seed CSV lacks the expected canonical columns.")
        matches: list[EntityMatch] = []
        for row in reader:
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
    return matches
