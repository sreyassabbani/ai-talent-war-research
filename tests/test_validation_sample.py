import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tag_edgar.cli import app
from tag_edgar.technology import TechnologyScreen
from tag_edgar.validation_sample import (
    build_validation_preflight,
    write_validation_preflight,
)

FIELDS = [
    "deal_id",
    "announcement_date",
    "acquirer_name",
    "target_name",
    "target_primary_sic",
    "candidate_cik",
    "cik_match_confidence",
    "target_public_status",
    "sdc_form",
    "transaction_value_mil",
]


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _candidate(index: int) -> dict[str, str]:
    return {
        "deal_id": f"deal-{index:03d}",
        "announcement_date": f"202{index % 3}-01-{index % 27 + 1:02d}",
        "acquirer_name": f"Buyer {index}",
        "target_name": f"Target {index}",
        "target_primary_sic": "7372" if index % 2 else "3674",
        "candidate_cik": str(1_000_000 + index),
        "cik_match_confidence": "high" if index % 2 else "medium",
        "target_public_status": "Public" if index % 5 == 0 else "Priv.",
        "sdc_form": "Merger" if index % 3 == 0 else "Acq. of Assets",
        "transaction_value_mil": str(index * 10) if index % 4 else "",
    }


def _screen() -> TechnologyScreen:
    return TechnologyScreen(
        "test-tech-v1",
        "https://www.sec.gov/example",
        {"7372": "Software", "3674": "Semiconductors"},
    )


def test_validation_preview_is_deterministic_balanced_and_not_frozen(tmp_path: Path) -> None:
    rows = [_candidate(index) for index in range(60)]
    first_catalog = tmp_path / "first.csv"
    second_catalog = tmp_path / "second.csv"
    _write(first_catalog, rows)
    _write(second_catalog, list(reversed(rows)))

    first = build_validation_preflight(first_catalog, _screen(), limit=40, seed="fixed-seed")
    second = build_validation_preflight(second_catalog, _screen(), limit=40, seed="fixed-seed")

    assert [row["deal_id"] for row in first.preview_rows] == [
        row["deal_id"] for row in second.preview_rows
    ]
    assert len(first.preview_rows) == 40
    assert {row["preview_status"] for row in first.preview_rows} == {"not_frozen"}
    assert {row["supervisor_unit_of_analysis_gate"] for row in first.preview_rows} == {
        "pending"
    }
    assert len({row["selection_stratum"] for row in first.preview_rows}) > 4
    assert first.manifest["sample_freeze_allowed"] is False
    assert first.manifest["external_retrieval_started"] is False
    assert first.manifest["supervisor_acceptance_claimed"] is False


def test_validation_preflight_records_exclusions_and_writes_only_preview_artifacts(
    tmp_path: Path,
) -> None:
    rows = [_candidate(index) for index in range(40)]
    rows[0]["acquirer_name"] = "Buyer\nZero"
    rows.extend(
        [
            {**_candidate(100), "deal_id": "duplicate"},
            {**_candidate(101), "deal_id": "duplicate"},
            {**_candidate(102), "deal_id": "prior-pilot"},
            {**_candidate(103), "target_primary_sic": "9999"},
            {**_candidate(104), "candidate_cik": ""},
            {**_candidate(105), "announcement_date": "not-a-date"},
        ]
    )
    catalog = tmp_path / "catalog.csv"
    exclusions = tmp_path / "pilot.csv"
    _write(catalog, rows)
    exclusions.write_text("deal_id\nprior-pilot\n", encoding="utf-8")

    preflight = build_validation_preflight(
        catalog,
        _screen(),
        limit=30,
        excluded_deals_csv=exclusions,
    )
    output = tmp_path / "output"
    write_validation_preflight(output, preflight)

    counts = preflight.manifest["eligibility_decision_counts"]
    assert isinstance(counts, dict)
    assert counts["excluded_duplicate_deal_id"] == 2
    assert counts["excluded_prior_pilot_candidate"] == 1
    assert counts["excluded_outside_target_sic_screen"] == 1
    assert counts["excluded_missing_acquirer_cik_candidate"] == 1
    assert counts["excluded_invalid_announcement_date"] == 1
    assert sorted(path.name for path in output.iterdir()) == [
        "eligibility_diagnostics.csv",
        "preflight_manifest.json",
        "sample_preview.csv",
        "stratum_diagnostics.csv",
    ]
    manifest = json.loads((output / "preflight_manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifact_status"] == "not_frozen"
    assert manifest["supervisor_unit_of_analysis_gate"]["status"] == "pending"
    assert manifest["physical_line_count_is_not_deal_count"] is True


def test_validation_preview_rejects_sizes_outside_prespecified_range(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    _write(catalog, [_candidate(index) for index in range(40)])

    with pytest.raises(ValueError, match="between 30 and 50"):
        build_validation_preflight(catalog, _screen(), limit=29)


def test_validation_preview_command_is_exposed() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "preview-validation-sample" in result.stdout
