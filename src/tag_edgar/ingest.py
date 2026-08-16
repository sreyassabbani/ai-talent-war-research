from __future__ import annotations

import csv
import json
import tomllib
from datetime import date
from pathlib import Path

from .models import DealSeed

REQUIRED_COLUMNS = ("deal_id", "acquirer_name", "announcement_date")
OPTIONAL_COLUMNS = ("acquirer_ticker", "target_name", "target_ticker", "effective_date")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d")


def load_column_map(path: Path) -> dict[str, str]:
    with path.open("rb") as file:
        config = tomllib.load(file)
    columns = config.get("columns")
    if not isinstance(columns, dict):
        raise TypeError("Column-map TOML must contain a [columns] table.")
    mapping = {str(key): str(value) for key, value in columns.items()}
    missing = set(REQUIRED_COLUMNS) - set(mapping)
    if missing:
        raise ValueError(f"Column map is missing required canonical fields: {sorted(missing)}")
    unexpected = set(mapping) - set(REQUIRED_COLUMNS) - set(OPTIONAL_COLUMNS)
    if unexpected:
        raise ValueError(f"Column map contains unsupported canonical fields: {sorted(unexpected)}")
    return mapping


def _parse_date(value: str, field: str, row_number: int) -> date:
    for format_string in DATE_FORMATS:
        try:
            return date.strptime(value.strip(), format_string)
        except ValueError:
            continue
    raise ValueError(f"Row {row_number}: {field}={value!r} is not a supported date format.")


def _optional(row: dict[str, str], source_column: str | None) -> str | None:
    if source_column is None:
        return None
    value = row.get(source_column, "").strip()
    return value or None


def read_deal_seeds(input_path: Path, column_map: dict[str, str]) -> list[DealSeed]:
    with input_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header row.")
        unknown_source_columns = set(column_map.values()) - set(reader.fieldnames)
        if unknown_source_columns:
            raise ValueError(
                f"Column map names absent from input CSV: {sorted(unknown_source_columns)}"
            )

        seeds: list[DealSeed] = []
        for row_number, row in enumerate(reader, start=2):
            deal_id = row[column_map["deal_id"]].strip()
            acquirer_name = row[column_map["acquirer_name"]].strip()
            announcement_value = row[column_map["announcement_date"]].strip()
            if not deal_id or not acquirer_name or not announcement_value:
                raise ValueError(
                    f"Row {row_number}: deal_id, acquirer_name, and announcement_date must be non-empty."
                )
            effective_value = _optional(row, column_map.get("effective_date"))
            seeds.append(
                DealSeed(
                    deal_id=deal_id,
                    acquirer_name=acquirer_name,
                    acquirer_ticker=_optional(row, column_map.get("acquirer_ticker")),
                    target_name=_optional(row, column_map.get("target_name")),
                    target_ticker=_optional(row, column_map.get("target_ticker")),
                    announcement_date=_parse_date(
                        announcement_value, "announcement_date", row_number
                    ),
                    effective_date=(
                        _parse_date(effective_value, "effective_date", row_number)
                        if effective_value is not None
                        else None
                    ),
                    source_row_number=row_number,
                    raw_source_row=json.dumps(row, sort_keys=True),
                )
            )
    return seeds
