import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from tag_edgar.cli import app
from tag_edgar.employee_tone import analyze_employee_tone, write_employee_tone

FIELDS = [
    "passage_id",
    "deal_id",
    "document_family_id",
    "document_type",
    "source_url",
    "heading",
    "text",
    "inclusion_status",
    "exclusion_reason",
]


def _write_passages(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _rows() -> list[dict[str, str]]:
    positive = (
        "The acquirer will preserve employee benefits and provide continued employment, "
        "including retention bonuses and severance protections for continuing employees."
    )
    negative = (
        "Employment may terminate, and unvested awards shall be subject to forfeiture upon "
        "a reduction in force or termination of employment; the employee may lose welfare coverage."
    )
    rows = []
    for index in range(6):
        deal = f"deal-{index % 2}"
        family = f"family-{index % 3}"
        rows.append(
            {
                "passage_id": f"passage-{index:02d}",
                "deal_id": deal,
                "document_family_id": family,
                "document_type": "EX-2.1" if index % 2 == 0 else "DEFM14A",
                "source_url": f"https://www.sec.gov/{index}",
                "heading": "EMPLOYMENT MATTERS",
                "text": positive if index % 2 == 0 else negative,
                "inclusion_status": "included",
                "exclusion_reason": "",
            }
        )
    rows.append(
        {
            "passage_id": "excluded-00",
            "deal_id": "deal-0",
            "document_family_id": "family-0",
            "document_type": "8-K",
            "source_url": "https://www.sec.gov/excluded",
            "heading": "TABLE OF CONTENTS",
            "text": "This passage mentions employees but was excluded by the screen.",
            "inclusion_status": "excluded",
            "exclusion_reason": "excluded_generic_term_without_people_context",
        }
    )
    return rows


def test_tone_features_count_expected_phrases(tmp_path: Path) -> None:
    csv_path = tmp_path / "passages.csv"
    _write_passages(csv_path, _rows())
    analysis = analyze_employee_tone(csv_path)
    assert analysis.passage_count == 6
    assert analysis.deal_count == 2
    by_id = {row["passage_id"]: row for row in analysis.passage_rows}
    positive = by_id["passage-00"]
    negative = by_id["passage-01"]
    assert float(str(positive["net_tone_per100"])) > 0.0
    assert float(str(negative["net_tone_per100"])) < 0.0
    assert int(str(negative["shall_count"])) >= 1
    assert int(str(negative["may_count"])) >= 1
    assert int(str(negative["negout_count"])) >= 2
    assert int(str(positive["protect_count"])) >= 3


def test_type_demeaning_centers_residuals(tmp_path: Path) -> None:
    csv_path = tmp_path / "passages.csv"
    _write_passages(csv_path, _rows())
    analysis = analyze_employee_tone(csv_path)
    assert analysis.type_rows, "expected document-type baseline rows"
    for row in analysis.passage_rows:
        baseline = next(
            candidate
            for candidate in analysis.type_rows
            if candidate["document_type"] == row["baseline_document_type"]
        )
        expected = float(str(row["net_tone_per100"])) - float(
            str(baseline["mean_net_tone_per100"])
        )
        assert abs(expected - float(str(row["net_tone_residual"]))) < 1e-6


def test_analysis_writes_are_byte_identical_across_runs(tmp_path: Path) -> None:
    csv_path = tmp_path / "passages.csv"
    _write_passages(csv_path, _rows())
    first_dir = tmp_path / "run-a"
    second_dir = tmp_path / "run-b"
    write_employee_tone(first_dir, analyze_employee_tone(csv_path))
    write_employee_tone(second_dir, analyze_employee_tone(csv_path))
    for name in (
        "passage_tone.csv",
        "family_baseline.csv",
        "type_baseline.csv",
        "deal_tone_summary.csv",
        "deal_term_usage.csv",
        "tone_manifest.json",
        "wordclouds/index.html",
    ):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes(), name


def test_term_usage_covers_comparison_vocabulary(tmp_path: Path) -> None:
    csv_path = tmp_path / "passages.csv"
    _write_passages(csv_path, _rows())
    analysis = analyze_employee_tone(csv_path)
    terms = {row["term"] for row in analysis.term_rows}
    assert {"retention", "severance", "vesting"}.issubset(terms)
    manifest = analysis.manifest
    assert manifest["lexicon_version"] == "employee-tone-v1"
    assert manifest["included_passages"] == 6
    assert "retention" in json.dumps(manifest["comparison_vocabulary"])


def test_cli_analyze_employee_tone_smoke(tmp_path: Path) -> None:
    csv_path = tmp_path / "passages.csv"
    _write_passages(csv_path, _rows())
    output_dir = tmp_path / "tone"
    result = CliRunner().invoke(
        app,
        ["analyze-employee-tone", str(csv_path), "--output-dir", str(output_dir)],
    )
    assert result.exit_code == 0, result.output
    assert (output_dir / "passage_tone.csv").exists()
    assert (output_dir / "deal_tone_summary.csv").exists()
    assert (output_dir / "wordclouds" / "index.html").exists()
