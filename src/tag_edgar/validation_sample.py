from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .storage import write_dict_csv
from .technology import TechnologyScreen

PREVIEW_FIELDS = [
    "preview_rank",
    "preview_status",
    "supervisor_unit_of_analysis_gate",
    "proposed_unit_of_analysis",
    "selection_seed",
    "selection_hash",
    "deal_id",
    "announcement_date",
    "announcement_year",
    "acquirer_name",
    "target_name",
    "target_primary_sic",
    "technology_label",
    "candidate_cik",
    "cik_match_confidence",
    "target_public_status",
    "public_status_stratum",
    "sdc_form",
    "form_stratum",
    "transaction_value_mil",
    "value_stratum",
    "selection_stratum",
]

ELIGIBILITY_FIELDS = ["eligibility_status", "decision_reason", "deal_count", "share"]

STRATUM_FIELDS = [
    "dimension",
    "stratum",
    "eligible_count",
    "preview_count",
    "eligible_share",
    "preview_share",
]

PROPOSED_UNIT_OF_ANALYSIS = "one SDC/LSEG deal event keyed by deal_id"


@dataclass(frozen=True)
class ValidationPreflight:
    preview_rows: tuple[dict[str, str], ...]
    eligibility_rows: tuple[dict[str, object], ...]
    stratum_rows: tuple[dict[str, object], ...]
    manifest: dict[str, object]


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _physical_data_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as file:
        return max(sum(1 for _ in file) - 1, 0)


def _read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return [{key: _clean(value) for key, value in row.items()} for row in csv.DictReader(file)]


def _read_excluded_deal_ids(path: Path | None) -> frozenset[str]:
    if path is None:
        return frozenset()
    with path.open(newline="", encoding="utf-8-sig") as file:
        return frozenset(_clean(row.get("deal_id")) for row in csv.DictReader(file) if row.get("deal_id"))


def _valid_announcement(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _public_group(value: str) -> str:
    normalized = value.casefold().rstrip(".")
    if normalized == "public":
        return "public"
    if normalized:
        return "non_public"
    return "unknown"


def _form_group(value: str) -> str:
    return "merger" if "merger" in value.casefold() else "non_merger"


def _value_group(value: str) -> str:
    normalized = value.replace(",", "").strip().casefold()
    if not normalized or normalized in {"na", "n/a", "np", "not provided"}:
        return "value_missing"
    try:
        float(normalized)
    except ValueError:
        return "value_invalid"
    return "value_reported"


def _selection_hash(seed: str, deal_id: str) -> str:
    return hashlib.sha256(f"{seed}:{deal_id}".encode()).hexdigest()


def _eligibility_reason(
    row: Mapping[str, str],
    duplicate_ids: frozenset[str],
    excluded_deal_ids: frozenset[str],
    technology_screen: TechnologyScreen,
) -> str:
    deal_id = _clean(row.get("deal_id"))
    if not deal_id:
        return "excluded_missing_deal_id"
    if deal_id in duplicate_ids:
        return "excluded_duplicate_deal_id"
    if deal_id in excluded_deal_ids:
        return "excluded_prior_pilot_candidate"
    announcement = _clean(row.get("announcement_date"))
    if not _valid_announcement(announcement):
        return "excluded_invalid_announcement_date"
    sic = _clean(row.get("target_primary_sic"))
    if technology_screen.rationale(sic) is None:
        return "excluded_outside_target_sic_screen"
    if not _clean(row.get("candidate_cik")):
        return "excluded_missing_acquirer_cik_candidate"
    if _clean(row.get("cik_match_confidence")).casefold() not in {"high", "medium"}:
        return "excluded_low_or_unresolved_acquirer_match"
    return "eligible_preview_candidate"


def _preview_row(
    row: Mapping[str, str], technology_screen: TechnologyScreen, seed: str
) -> dict[str, str]:
    announcement = _clean(row.get("announcement_date"))
    public_group = _public_group(_clean(row.get("target_public_status")))
    form_group = _form_group(_clean(row.get("sdc_form")))
    value_group = _value_group(_clean(row.get("transaction_value_mil")))
    year = announcement[:4]
    sic = _clean(row.get("target_primary_sic"))
    selection_stratum = f"{year}|{public_group}|{form_group}|{value_group}"
    return {
        "preview_rank": "",
        "preview_status": "not_frozen",
        "supervisor_unit_of_analysis_gate": "pending",
        "proposed_unit_of_analysis": PROPOSED_UNIT_OF_ANALYSIS,
        "selection_seed": seed,
        "selection_hash": _selection_hash(seed, _clean(row.get("deal_id"))),
        "deal_id": _clean(row.get("deal_id")),
        "announcement_date": announcement,
        "announcement_year": year,
        "acquirer_name": _clean(row.get("acquirer_name")),
        "target_name": _clean(row.get("target_name")),
        "target_primary_sic": sic,
        "technology_label": technology_screen.codes[sic],
        "candidate_cik": _clean(row.get("candidate_cik")),
        "cik_match_confidence": _clean(row.get("cik_match_confidence")),
        "target_public_status": _clean(row.get("target_public_status")),
        "public_status_stratum": public_group,
        "sdc_form": _clean(row.get("sdc_form")),
        "form_stratum": form_group,
        "transaction_value_mil": _clean(row.get("transaction_value_mil")),
        "value_stratum": value_group,
        "selection_stratum": selection_stratum,
    }


def _round_robin_preview(candidates: Sequence[dict[str, str]], limit: int) -> list[dict[str, str]]:
    buckets: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        buckets[row["selection_stratum"]].append(row)
    for rows in buckets.values():
        rows.sort(key=lambda row: (row["selection_hash"], row["deal_id"]))

    selected: list[dict[str, str]] = []
    while len(selected) < limit and any(buckets.values()):
        for stratum in sorted(buckets):
            if buckets[stratum] and len(selected) < limit:
                selected.append(buckets[stratum].pop(0))
    for rank, row in enumerate(selected, start=1):
        row["preview_rank"] = str(rank)
    return selected


def _share(count: int, total: int) -> str:
    return f"{count / total:.10f}" if total else "0"


def _eligibility_diagnostics(reasons: Counter[str], total: int) -> list[dict[str, object]]:
    return [
        {
            "eligibility_status": "eligible" if reason == "eligible_preview_candidate" else "excluded",
            "decision_reason": reason,
            "deal_count": count,
            "share": _share(count, total),
        }
        for reason, count in sorted(reasons.items())
    ]


def _stratum_diagnostics(
    eligible: Sequence[dict[str, str]], preview: Sequence[dict[str, str]]
) -> list[dict[str, object]]:
    dimensions = {
        "selection_stratum": "selection_stratum",
        "announcement_year": "announcement_year",
        "public_status": "public_status_stratum",
        "form": "form_stratum",
        "transaction_value": "value_stratum",
        "technology_label": "technology_label",
    }
    output: list[dict[str, object]] = []
    for dimension, field in dimensions.items():
        eligible_counts = Counter(row[field] for row in eligible)
        preview_counts = Counter(row[field] for row in preview)
        for stratum in sorted(eligible_counts):
            output.append(
                {
                    "dimension": dimension,
                    "stratum": stratum,
                    "eligible_count": eligible_counts[stratum],
                    "preview_count": preview_counts[stratum],
                    "eligible_share": _share(eligible_counts[stratum], len(eligible)),
                    "preview_share": _share(preview_counts[stratum], len(preview)),
                }
            )
    return output


def build_validation_preflight(
    catalog_csv: Path,
    technology_screen: TechnologyScreen,
    *,
    limit: int = 40,
    seed: str = "validation-preview-v1",
    excluded_deals_csv: Path | None = None,
) -> ValidationPreflight:
    """Build a deterministic validation candidate preview without freezing or retrieving it."""
    if not 30 <= limit <= 50:
        raise ValueError("Validation preview limit must be between 30 and 50.")
    if not seed.strip():
        raise ValueError("Validation preview seed cannot be blank.")

    catalog_rows = _read_catalog(catalog_csv)
    deal_id_counts = Counter(_clean(row.get("deal_id")) for row in catalog_rows)
    duplicate_ids = frozenset(
        deal_id for deal_id, count in deal_id_counts.items() if deal_id and count > 1
    )
    excluded_deal_ids = _read_excluded_deal_ids(excluded_deals_csv)
    reasons: Counter[str] = Counter()
    eligible: list[dict[str, str]] = []
    for row in catalog_rows:
        reason = _eligibility_reason(row, duplicate_ids, excluded_deal_ids, technology_screen)
        reasons[reason] += 1
        if reason == "eligible_preview_candidate":
            eligible.append(_preview_row(row, technology_screen, seed))

    preview = _round_robin_preview(eligible, min(limit, len(eligible)))
    physical_lines = _physical_data_lines(catalog_csv)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact_status": "not_frozen",
        "purpose": "read_only_validation_candidate_preflight",
        "catalog_sha256": _file_sha256(catalog_csv),
        "catalog_logical_deal_rows": len(catalog_rows),
        "catalog_unique_deal_ids": len({key for key in deal_id_counts if key}),
        "catalog_physical_data_lines": physical_lines,
        "physical_line_count_is_not_deal_count": physical_lines != len(catalog_rows),
        "excluded_prior_pilot_deal_ids": len(excluded_deal_ids),
        "eligible_candidate_count": len(eligible),
        "requested_preview_count": limit,
        "preview_count": len(preview),
        "selection_seed": seed,
        "selection_method": "sha256_within_stratum_then_lexicographic_round_robin",
        "stratification_dimensions": [
            "announcement_year",
            "target_public_status",
            "transaction_form",
            "transaction_value_availability",
        ],
        "technology_screen_version": technology_screen.version,
        "technology_screen_source": technology_screen.source,
        "proposed_unit_of_analysis": PROPOSED_UNIT_OF_ANALYSIS,
        "supervisor_unit_of_analysis_gate": {
            "status": "pending",
            "required_before": ["sample_freeze", "external_retrieval"],
        },
        "sample_freeze_allowed": False,
        "external_retrieval_started": False,
        "supervisor_acceptance_claimed": False,
        "eligibility_decision_counts": dict(sorted(reasons.items())),
    }
    return ValidationPreflight(
        preview_rows=tuple(preview),
        eligibility_rows=tuple(_eligibility_diagnostics(reasons, len(catalog_rows))),
        stratum_rows=tuple(_stratum_diagnostics(eligible, preview)),
        manifest=manifest,
    )


def write_validation_preflight(output_dir: Path, preflight: ValidationPreflight) -> None:
    """Write local, derived preflight artifacts; no source data or network state is mutated."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dict_csv(output_dir / "sample_preview.csv", preflight.preview_rows, PREVIEW_FIELDS)
    write_dict_csv(
        output_dir / "eligibility_diagnostics.csv",
        preflight.eligibility_rows,
        ELIGIBILITY_FIELDS,
    )
    write_dict_csv(
        output_dir / "stratum_diagnostics.csv", preflight.stratum_rows, STRATUM_FIELDS
    )
    (output_dir / "preflight_manifest.json").write_text(
        json.dumps(preflight.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
