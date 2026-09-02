from __future__ import annotations

import csv
import json
from pathlib import Path

from tag_edgar.disclosure_freeze import FROZEN_FIELDS, build_frozen_sample, write_frozen_sample
from tag_edgar.disclosure_pool import load_disclosure_pool_config

CONFIG = load_disclosure_pool_config(
    Path(__file__).resolve().parents[1] / "config" / "disclosure_pool.toml"
)

QUEUE_FIELDS = [
    "deal_id",
    "acquirer_name",
    "target_name",
    "announcement_date",
    "effective_date",
    "transaction_value_mil",
    "target_public_status",
    "cik_match_method",
]

PASSAGE_FIELDS = [
    "deal_id",
    "document_id",
    "source_document_family_id",
    "inclusion_status",
]


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _queue(tmp_path: Path, deal_ids: list[str]) -> Path:
    return _write(
        tmp_path / "queue.csv",
        QUEUE_FIELDS,
        [
            {
                "deal_id": deal_id,
                "acquirer_name": f"Buyer {deal_id}",
                "target_name": f"Target {deal_id}",
                "announcement_date": "2021-04-01",
                "effective_date": "2021-09-01",
                "transaction_value_mil": "100",
                "target_public_status": "Priv.",
                "cik_match_method": "machine_target_name_in_acquirer_filing",
            }
            for deal_id in deal_ids
        ],
    )


def _passages(tmp_path: Path, spec: dict[str, tuple[int, int]]) -> Path:
    """spec maps deal_id -> (included passage count, distinct source document count)."""
    rows: list[dict[str, str]] = []
    for deal_id, (count, families) in spec.items():
        for index in range(count):
            rows.append(
                {
                    "deal_id": deal_id,
                    "document_id": f"doc_{index}",
                    "source_document_family_id": f"fam_{index % max(families, 1)}",
                    "inclusion_status": "included",
                }
            )
        rows.append(
            {
                "deal_id": deal_id,
                "document_id": "doc_x",
                "source_document_family_id": "fam_x",
                "inclusion_status": "excluded",
            }
        )
    return _write(tmp_path / "passages.csv", PASSAGE_FIELDS, rows)


def _runs(tmp_path: Path, deal_ids: list[str], documents: int = 5) -> Path:
    runs = tmp_path / "runs"
    for deal_id in deal_ids:
        _write(
            runs / deal_id / "documents.csv",
            ["document_id"],
            [{"document_id": f"d{index}"} for index in range(documents)],
        )
    return runs


def test_gate_separates_modelled_zero_yield_and_below_gate(tmp_path: Path) -> None:
    deals = ["rich", "thin", "empty", "missing"]
    queue = _queue(tmp_path, deals)
    passages = _passages(tmp_path, {"rich": (40, 6), "thin": (3, 1)})
    runs = _runs(tmp_path, ["rich", "thin", "empty"])

    sample = build_frozen_sample(queue, passages, runs, CONFIG)
    status = {row["deal_id"]: row["sample_status"] for row in sample.rows}
    assert status["rich"] == "modelled"
    assert status["thin"] == "below_yield_gate"
    assert status["empty"] == "zero_yield_reported_not_modelled"
    assert status["missing"] == "not_retrieved"
    assert sample.modelled_deal_ids == ("rich",)


def test_excluded_passages_do_not_count_toward_the_gate(tmp_path: Path) -> None:
    queue = _queue(tmp_path, ["one"])
    passages = _passages(tmp_path, {"one": (9, 3)})
    runs = _runs(tmp_path, ["one"])
    sample = build_frozen_sample(queue, passages, runs, CONFIG)
    row = sample.rows[0]
    assert row["included_passages"] == "9"
    assert row["sample_status"] == "below_yield_gate"
    assert "below the gate" in row["sample_reason"]


def test_single_source_document_fails_the_document_minimum(tmp_path: Path) -> None:
    """Twenty passages from one document is one clause repeated, not a corpus."""
    queue = _queue(tmp_path, ["single"])
    passages = _passages(tmp_path, {"single": (20, 1)})
    runs = _runs(tmp_path, ["single"])
    sample = build_frozen_sample(queue, passages, runs, CONFIG)
    assert sample.rows[0]["sample_status"] == "below_yield_gate"


def test_manifest_records_gate_hashes_and_concentration(tmp_path: Path) -> None:
    queue = _queue(tmp_path, ["a", "b"])
    passages = _passages(tmp_path, {"a": (75, 5), "b": (25, 5)})
    runs = _runs(tmp_path, ["a", "b"])
    sample = build_frozen_sample(queue, passages, runs, CONFIG)

    manifest = sample.manifest
    assert manifest["modelled_deals"] == 2
    assert manifest["modelled_passages"] == 100
    assert manifest["largest_deal_share"] == 0.75
    assert len(str(manifest["passages_csv_sha256"])) == 64
    assert "disclosure observation" in str(manifest["evidence_boundary"])


def test_write_frozen_sample_emits_schema_and_manifest(tmp_path: Path) -> None:
    queue = _queue(tmp_path, ["a"])
    passages = _passages(tmp_path, {"a": (30, 4)})
    runs = _runs(tmp_path, ["a"])
    sample = build_frozen_sample(queue, passages, runs, CONFIG)
    output = tmp_path / "frozen"
    write_frozen_sample(output, sample)

    with (output / "frozen_sample.csv").open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == FROZEN_FIELDS
        assert next(reader)["sample_status"] == "modelled"
    manifest = json.loads((output / "frozen_sample_manifest.json").read_text(encoding="utf-8"))
    assert manifest["queued_deals"] == 1


def test_probe_evidence_is_carried_into_the_frozen_row(tmp_path: Path) -> None:
    queue = _queue(tmp_path, ["a"])
    passages = _passages(tmp_path, {"a": (30, 4)})
    runs = _runs(tmp_path, ["a"])
    probe = _write(
        tmp_path / "probe.csv",
        ["deal_id", "probe_status", "agreement_exhibit_types", "target_name_hit"],
        [
            {
                "deal_id": "a",
                "probe_status": "agreement_exhibit",
                "agreement_exhibit_types": "EX-2.1",
                "target_name_hit": "yes",
            }
        ],
    )
    sample = build_frozen_sample(queue, passages, runs, CONFIG, probe_csv=probe)
    row = sample.rows[0]
    assert row["probe_status"] == "agreement_exhibit"
    assert row["agreement_exhibit_types"] == "EX-2.1"
    assert row["target_name_hit"] == "yes"
