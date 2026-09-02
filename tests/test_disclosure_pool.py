from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from tag_edgar.disclosure_pool import (
    POOL_FIELDS,
    build_disclosure_pool,
    load_disclosure_pool_config,
    write_disclosure_pool,
)
from tag_edgar.technology import TechnologyScreen

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "disclosure_pool.toml"

SCREEN = TechnologyScreen(
    version="digital-tech-test",
    source="https://www.sec.gov/",
    codes={"7372": "Prepackaged software", "3674": "Semiconductors"},
)

CATALOG_HEADER = [
    "deal_id",
    "announcement_date",
    "effective_date",
    "acquirer_name",
    "target_name",
    "sdc_form",
    "target_primary_sic",
    "target_public_status",
    "transaction_value_mil",
    "transaction_value_effective_mil",
    "equity_value_mil",
    "candidate_cik",
    "candidate_sec_name",
    "cik_match_confidence",
    "target_candidate_cik",
    "target_cik_match_confidence",
]


def _row(**overrides: str) -> dict[str, str]:
    base = dict.fromkeys(CATALOG_HEADER, "")
    base.update(
        {
            "deal_id": "1",
            "announcement_date": "2021-03-01",
            "acquirer_name": "Buyer Inc",
            "target_name": "Target Inc",
            "target_primary_sic": "7372",
            "candidate_cik": "0000000001",
            "cik_match_confidence": "high",
            "transaction_value_mil": "500",
        }
    )
    base.update(overrides)
    return base


def _catalog(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "catalog.csv"
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CATALOG_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_config_loads_from_repository() -> None:
    config = load_disclosure_pool_config(CONFIG_PATH)
    assert config.version == "disclosure-first-v1"
    assert "high" in config.cik_match_confidence
    assert "DEFM14A" in config.proxy_forms
    assert config.minimum_passages >= 1


def test_pool_keeps_resolved_technology_deals(tmp_path: Path) -> None:
    config = load_disclosure_pool_config(CONFIG_PATH)
    catalog = _catalog(
        tmp_path,
        [
            _row(deal_id="keep"),
            _row(deal_id="unresolved", cik_match_confidence="low"),
            _row(deal_id="not_tech", target_primary_sic="2011"),
            _row(deal_id="no_date", announcement_date=""),
        ],
    )
    result = build_disclosure_pool(catalog, SCREEN, config)
    assert [row["deal_id"] for row in result.rows] == ["keep"]
    assert result.exclusions["acquirer_cik_unresolved"] == 1
    assert result.exclusions["target_not_technology_sic"] == 1
    assert result.exclusions["missing_announcement_date"] == 1


def test_pool_has_no_value_floor_by_default(tmp_path: Path) -> None:
    """Value is missing for most of the catalog, so a floor would silently shrink the pool."""
    config = load_disclosure_pool_config(CONFIG_PATH)
    catalog = _catalog(
        tmp_path,
        [_row(deal_id="tiny", transaction_value_mil="1"), _row(deal_id="blank", transaction_value_mil="")],
    )
    result = build_disclosure_pool(catalog, SCREEN, config)
    assert {row["deal_id"] for row in result.rows} == {"tiny", "blank"}


def test_pool_respects_date_range(tmp_path: Path) -> None:
    config = load_disclosure_pool_config(CONFIG_PATH)
    catalog = _catalog(
        tmp_path,
        [_row(deal_id="in", announcement_date="2021-06-01"), _row(deal_id="out", announcement_date="2018-06-01")],
    )
    result = build_disclosure_pool(
        catalog, SCREEN, config, start=date(2020, 1, 1), end=date(2022, 12, 31)
    )
    assert [row["deal_id"] for row in result.rows] == ["in"]
    assert result.exclusions["outside_date_range"] == 1


def test_pool_orders_larger_deals_first(tmp_path: Path) -> None:
    config = load_disclosure_pool_config(CONFIG_PATH)
    catalog = _catalog(
        tmp_path,
        [
            _row(deal_id="small", transaction_value_mil="10"),
            _row(deal_id="large", transaction_value_mil="9,000"),
            _row(deal_id="missing", transaction_value_mil=""),
        ],
    )
    result = build_disclosure_pool(catalog, SCREEN, config)
    assert [row["deal_id"] for row in result.rows][:2] == ["large", "small"]


def test_write_pool_emits_manifest_and_schema(tmp_path: Path) -> None:
    config = load_disclosure_pool_config(CONFIG_PATH)
    catalog = _catalog(tmp_path, [_row(deal_id="keep")])
    result = build_disclosure_pool(catalog, SCREEN, config)
    output = tmp_path / "out"
    write_disclosure_pool(output, result)

    with (output / "pool.csv").open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == POOL_FIELDS
        rows = list(reader)
    assert rows[0]["pool_rule_version"] == config.version

    manifest = json.loads((output / "pool_manifest.json").read_text(encoding="utf-8"))
    assert manifest["pool_rows"] == 1
    assert manifest["catalog_rows"] == 1
    assert len(manifest["catalog_csv_sha256"]) == 64
    assert "not asserted here" in str(manifest["selection_basis"])


def test_missing_sections_raise(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text('version = "x"\n', encoding="utf-8")
    with pytest.raises(TypeError):
        load_disclosure_pool_config(path)
