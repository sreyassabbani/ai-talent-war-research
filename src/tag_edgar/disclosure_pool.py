"""Disclosure-first candidate selection for the 100+ deal employee-language sample.

The earlier AI-keyword-first screen chose deals by what the target did, then discovered that most
of their acquirers never file with the SEC. Employee-treatment language exists when an SEC
registrant files the transaction agreement or a merger proxy, so this module selects on that
property instead and leaves the AI question to a post-hoc label.

Selection here is deterministic and offline. It states a pool; it does not claim any deal has
usable disclosure. Only :mod:`tag_edgar.disclosure_probe` can establish that, against EDGAR.
"""

from __future__ import annotations

import csv
import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .technology import TechnologyScreen

__all__ = [
    "POOL_FIELDS",
    "DisclosurePoolConfig",
    "PoolResult",
    "build_disclosure_pool",
    "load_disclosure_pool_config",
    "write_disclosure_pool",
]

POOL_FIELDS = [
    "deal_id",
    "announcement_date",
    "effective_date",
    "acquirer_name",
    "target_name",
    "sdc_form",
    "target_primary_sic",
    "target_public_status",
    "transaction_value_mil",
    "candidate_cik",
    "candidate_sec_name",
    "cik_match_confidence",
    "target_candidate_cik",
    "target_cik_match_confidence",
    "technology_screen_reason",
    "pool_rule_version",
]

_EXCLUSION_ORDER = (
    "missing_announcement_date",
    "acquirer_cik_unresolved",
    "target_not_technology_sic",
    "below_transaction_value_floor",
)


@dataclass(frozen=True)
class DisclosurePoolConfig:
    """Frozen selection rule, read from ``config/disclosure_pool.toml``."""

    version: str
    cik_match_confidence: frozenset[str]
    require_technology_target: bool
    minimum_transaction_value_mil: float
    days_before_announcement: int
    days_after_announcement: int
    agreement_forms: frozenset[str]
    proxy_forms: frozenset[str]
    announcement_forms: frozenset[str]
    minimum_passages: int
    minimum_documents: int


@dataclass(frozen=True)
class PoolResult:
    rows: tuple[dict[str, str], ...]
    exclusions: dict[str, int] = field(default_factory=dict)
    manifest: dict[str, object] = field(default_factory=dict)


def _section(config: dict[str, object], name: str) -> dict[str, object]:
    value = config.get(name)
    if not isinstance(value, dict):
        raise TypeError(f"config/disclosure_pool.toml is missing the [{name}] table.")
    return value


def _forms(section: dict[str, object], key: str) -> frozenset[str]:
    value = section.get(key)
    if not isinstance(value, list):
        raise TypeError(f"[{key}] must be a list of SEC form types.")
    return frozenset(str(item).upper() for item in value)


def _number(section: dict[str, object], key: str, default: float) -> float:
    """Read a numeric setting without letting an unexpected TOML type pass silently."""
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError(f"{key} must be a number.")
    return float(value)


def load_disclosure_pool_config(path: Path) -> DisclosurePoolConfig:
    with path.open("rb") as file:
        raw = tomllib.load(file)
    pool = _section(raw, "pool")
    probe = _section(raw, "probe")
    gate = _section(raw, "yield_gate")
    confidence = pool.get("cik_match_confidence")
    if not isinstance(confidence, list):
        raise TypeError("pool.cik_match_confidence must be a list.")
    return DisclosurePoolConfig(
        version=str(raw.get("version", "unversioned")),
        cik_match_confidence=frozenset(str(item).lower() for item in confidence),
        require_technology_target=bool(pool.get("require_technology_target", True)),
        minimum_transaction_value_mil=_number(pool, "minimum_transaction_value_mil", 0.0),
        days_before_announcement=int(_number(probe, "days_before_announcement", 5)),
        days_after_announcement=int(_number(probe, "days_after_announcement", 60)),
        agreement_forms=_forms(probe, "agreement_forms"),
        proxy_forms=_forms(probe, "proxy_forms"),
        announcement_forms=_forms(probe, "announcement_forms"),
        minimum_passages=int(_number(gate, "minimum_passages", 10)),
        minimum_documents=int(_number(gate, "minimum_documents", 2)),
    )


def _reported_value(row: dict[str, str]) -> float | None:
    for column in (
        "transaction_value_mil",
        "transaction_value_effective_mil",
        "equity_value_mil",
    ):
        raw = (row.get(column) or "").replace(",", "").strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _parse_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_disclosure_pool(
    catalog_csv: Path,
    screen: TechnologyScreen,
    config: DisclosurePoolConfig,
    *,
    start: date | None = None,
    end: date | None = None,
) -> PoolResult:
    """Apply the frozen pool rule to the deal catalog.

    Every excluded deal is counted under exactly one reason, in a fixed order, so the funnel in
    the final report adds up and no drop is silent.
    """
    with catalog_csv.open(newline="", encoding="utf-8") as file:
        catalog = [{key: (value or "") for key, value in row.items()} for row in csv.DictReader(file)]

    exclusions: dict[str, int] = dict.fromkeys(_EXCLUSION_ORDER, 0)
    exclusions["outside_date_range"] = 0
    rows: list[dict[str, str]] = []
    for row in catalog:
        announced = _parse_date(row.get("announcement_date", ""))
        if announced is None:
            exclusions["missing_announcement_date"] += 1
            continue
        if (start is not None and announced < start) or (end is not None and announced > end):
            exclusions["outside_date_range"] += 1
            continue
        if row.get("cik_match_confidence", "").lower() not in config.cik_match_confidence:
            exclusions["acquirer_cik_unresolved"] += 1
            continue
        rationale = screen.rationale(row.get("target_primary_sic", ""))
        if config.require_technology_target and rationale is None:
            exclusions["target_not_technology_sic"] += 1
            continue
        value = _reported_value(row)
        if (
            config.minimum_transaction_value_mil > 0
            and value is not None
            and value < config.minimum_transaction_value_mil
        ):
            exclusions["below_transaction_value_floor"] += 1
            continue
        rows.append(
            {
                "deal_id": row.get("deal_id", ""),
                "announcement_date": row.get("announcement_date", ""),
                "effective_date": row.get("effective_date", ""),
                "acquirer_name": row.get("acquirer_name", ""),
                "target_name": row.get("target_name", ""),
                "sdc_form": row.get("sdc_form", ""),
                "target_primary_sic": row.get("target_primary_sic", ""),
                "target_public_status": row.get("target_public_status", ""),
                "transaction_value_mil": row.get("transaction_value_mil", ""),
                "candidate_cik": row.get("candidate_cik", ""),
                "candidate_sec_name": row.get("candidate_sec_name", ""),
                "cik_match_confidence": row.get("cik_match_confidence", ""),
                "target_candidate_cik": row.get("target_candidate_cik", ""),
                "target_cik_match_confidence": row.get("target_cik_match_confidence", ""),
                "technology_screen_reason": rationale or "",
                "pool_rule_version": config.version,
            }
        )

    rows.sort(
        key=lambda item: (
            -(_reported_value(item) or -1.0),
            item["cik_match_confidence"] != "high",
            item["announcement_date"],
            item["deal_id"],
        )
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "pool_rule_version": config.version,
        "catalog_csv_sha256": _sha256(catalog_csv),
        "catalog_rows": len(catalog),
        "pool_rows": len(rows),
        "exclusions": {key: value for key, value in exclusions.items() if value},
        "technology_screen_version": screen.version,
        "date_range": {
            "start": start.isoformat() if start else "",
            "end": end.isoformat() if end else "",
        },
        "selection_basis": (
            "acquirer is an SEC registrant with a technology-SIC target; disclosure existence is "
            "not asserted here and is decided by probe-disclosure"
        ),
    }
    return PoolResult(tuple(rows), exclusions, manifest)


def write_disclosure_pool(output_dir: Path, result: PoolResult) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "pool.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=POOL_FIELDS)
        writer.writeheader()
        writer.writerows(result.rows)
    (output_dir / "pool_manifest.json").write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
