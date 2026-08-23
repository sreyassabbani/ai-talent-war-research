from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook
from typer.testing import CliRunner

from tag_edgar.cli import app
from tag_edgar.h1b_coverage import audit_h1b_coverage, normalize_employer_name


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_workbook(path: Path, rows: list[tuple[Any, ...]]) -> None:
    workbook = Workbook()
    sheet = workbook.worksheets[0]
    sheet.append(["EMPLOYER_NAME", "CASE_STATUS", "NEW_EMPLOYMENT"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


def _inputs(tmp_path: Path) -> tuple[Path, Path, dict[int, Path]]:
    review = tmp_path / "pilot.csv"
    aliases = tmp_path / "aliases.csv"
    _write_csv(
        review,
        ["deal_id", "announcement_date", "effective_date"],
        [{"deal_id": "d1", "announcement_date": "2021-09-13", "effective_date": "2021-11-01"}],
    )
    _write_csv(
        aliases,
        ["deal_id", "party_role", "party_name", "normalized_employer_alias"],
        [
            {
                "deal_id": "d1",
                "party_role": "acquirer",
                "party_name": "Example, Inc.",
                "normalized_employer_alias": "EXAMPLE INC",
            },
            {
                "deal_id": "d1",
                "party_role": "target",
                "party_name": "Target LLC",
                "normalized_employer_alias": "TARGET LLC",
            },
        ],
    )
    fy2020 = tmp_path / "fy2020.xlsx"
    fy2022 = tmp_path / "fy2022.xlsx"
    _write_workbook(
        fy2020,
        [
            (" Example, Inc. ", "Certified", 2),
            ("EXAMPLE---INC", "CERTIFIED-WITHDRAWN", "3"),
            ("TARGET LLC", "Denied", 50),
            ("Unlisted Inc", "CERTIFIED", 100),
        ],
    )
    _write_workbook(
        fy2022,
        [
            ("Target LLC", " certified ", None),
            ("Example Inc", "WITHDRAWN", 9),
        ],
    )
    return review, aliases, {2020: fy2020, 2022: fy2022}


def test_normalize_employer_name_uses_prespecified_exact_rule() -> None:
    assert normalize_employer_name("  Acme,  R&D---LLC ") == "ACME R D LLC"


def test_audit_counts_alias_years_and_writes_reproducible_manifest(tmp_path: Path) -> None:
    review, aliases, workbooks = _inputs(tmp_path)
    output = tmp_path / "output"

    manifest = audit_h1b_coverage(review, aliases, workbooks, output)

    with (output / "h1b_pilot_coverage.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    example_pre = next(
        row
        for row in rows
        if row["normalized_employer_alias"] == "EXAMPLE INC" and row["period"] == "pre"
    )
    target_post = next(
        row
        for row in rows
        if row["normalized_employer_alias"] == "TARGET LLC" and row["period"] == "post"
    )
    assert (example_pre["certified_case_count"], example_pre["new_employment_sum"]) == ("2", "5")
    assert (target_post["certified_case_count"], target_post["new_employment_sum"]) == ("1", "0")
    assert manifest["deals_with_both_period_case_presence"] == 1
    assert manifest["deals_with_both_period_positive_new_employment"] == 0
    saved = json.loads((output / "h1b_pilot_coverage_manifest.json").read_text())
    assert saved["offline_only"] is True
    assert saved["broad_hiring_outcome_decision"] == "no-go"
    assert "not verified hiring" in saved["interpretation"]
    assert len(saved["inputs"]["official_fy_q4_workbooks"][0]["sha256"]) == 64


def test_audit_requires_every_derived_pre_and_post_year(tmp_path: Path) -> None:
    review, aliases, workbooks = _inputs(tmp_path)

    with pytest.raises(ValueError, match="2022"):
        audit_h1b_coverage(review, aliases, {2020: workbooks[2020]}, tmp_path / "output")


def test_h1b_cli_accepts_repeated_local_year_workbooks(tmp_path: Path) -> None:
    review, aliases, workbooks = _inputs(tmp_path)
    output = tmp_path / "cli-output"

    result = CliRunner().invoke(
        app,
        [
            "audit-h1b-coverage",
            str(review),
            "--aliases-csv",
            str(aliases),
            "--workbook",
            f"2020={workbooks[2020]}",
            "--workbook",
            f"2022={workbooks[2022]}",
            "--output-dir",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Broad hiring-outcome decision: no-go" in result.stdout
    assert (output / "h1b_pilot_coverage_manifest.json").is_file()
