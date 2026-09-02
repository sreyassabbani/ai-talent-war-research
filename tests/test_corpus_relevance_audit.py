import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tag_edgar.cli import app
from tag_edgar.corpus_relevance_audit import (
    PACKET_FIELDS,
    prepare_corpus_relevance_audit,
    score_corpus_relevance_audit,
    write_corpus_relevance_audit,
    write_corpus_relevance_scores,
)

FIELDS = [
    "passage_id",
    "deal_id",
    "document_family_id",
    "source_url",
    "heading",
    "text",
    "inclusion_status",
    "exclusion_reason",
]


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _candidates() -> list[dict[str, str]]:
    rows = []
    for decision in ("included", "excluded"):
        for index in range(12):
            rows.append(
                {
                    "passage_id": f"{decision}-{index:02d}",
                    "deal_id": f"deal-{index % 3}",
                    "document_family_id": f"family-{index % 4}",
                    "source_url": f"https://www.sec.gov/{decision}/{index}",
                    "heading": f"Heading {index}",
                    "text": f"Candidate passage {decision} {index}.",
                    "inclusion_status": decision,
                    "exclusion_reason": "" if decision == "included" else "screen_rule",
                }
            )
    return rows


def _complete(packet_path: Path, labels: dict[str, str] | None = None) -> None:
    rows = _rows(packet_path)
    for row in rows:
        row["relevance_label"] = (labels or {}).get(row["audit_item_id"], "relevant")
        row["assessor_id"] = "reviewer-1"
        row["human_attestation"] = "human_assessed"
    _write(packet_path, PACKET_FIELDS, rows)


def test_prepare_is_deterministic_stratified_blinded_and_pending(tmp_path: Path) -> None:
    first_input = tmp_path / "first.csv"
    second_input = tmp_path / "second.csv"
    _write(first_input, FIELDS, _candidates())
    _write(second_input, FIELDS, list(reversed(_candidates())))

    first = prepare_corpus_relevance_audit(
        first_input, included_limit=8, excluded_limit=8, seed="fixed"
    )
    second = prepare_corpus_relevance_audit(
        second_input, included_limit=8, excluded_limit=8, seed="fixed"
    )

    assert first.packet_rows == second.packet_rows
    assert first.key_rows == second.key_rows
    assert {row["inclusion_decision"] for row in first.key_rows} == {"included", "excluded"}
    assert len({row["deal_id"] for row in first.key_rows}) == 3
    assert len({row["document_family_id"] for row in first.key_rows}) == 4
    assert all(not row["relevance_label"] for row in first.packet_rows)
    assert all("deal_id" not in row and "inclusion_decision" not in row for row in first.packet_rows)
    assert first.manifest["gate_status"] == "pending"
    assert first.manifest["labels_present"] is False


def test_writer_separates_packet_key_and_records_pending_manifest(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.csv"
    _write(candidates, FIELDS, _candidates())
    audit = prepare_corpus_relevance_audit(candidates, included_limit=4, excluded_limit=4)
    output = tmp_path / "audit"

    write_corpus_relevance_audit(output, audit)

    assert sorted(path.name for path in output.iterdir()) == [
        "assessor_packet.csv",
        "audit_manifest.json",
        "private_key.csv",
    ]
    manifest = json.loads((output / "audit_manifest.json").read_text())
    assert manifest["gate_status"] == "pending"
    assert manifest["assessor_packet_sha256"]
    assert "inclusion_decision" not in _rows(output / "assessor_packet.csv")[0]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda row: row.update(relevance_label=""), "relevance_label"),
        (lambda row: row.update(relevance_label="maybe"), "relevance_label"),
        (lambda row: row.update(relevance_label="Relevant"), "relevance_label"),
        (lambda row: row.update(assessor_id=""), "assessor_id"),
        (lambda row: row.update(human_attestation="yes"), "human_attestation"),
        (lambda row: row.update(passage_text="changed"), "Immutable packet content changed"),
    ],
)
def test_scoring_strictly_rejects_incomplete_invalid_or_changed_packets(
    tmp_path: Path, mutation, message: str
) -> None:
    candidates = tmp_path / "candidates.csv"
    _write(candidates, FIELDS, _candidates())
    output = tmp_path / "audit"
    write_corpus_relevance_audit(
        output, prepare_corpus_relevance_audit(candidates, included_limit=3, excluded_limit=3)
    )
    packet = output / "assessor_packet.csv"
    _complete(packet)
    rows = _rows(packet)
    mutation(rows[0])
    _write(packet, PACKET_FIELDS, rows)

    with pytest.raises(ValueError, match=message):
        score_corpus_relevance_audit(
            output / "private_key.csv", packet, output / "audit_manifest.json"
        )


def test_score_reports_point_rates_wilson_intervals_and_gate(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.csv"
    _write(candidates, FIELDS, _candidates())
    audit_dir = tmp_path / "audit"
    write_corpus_relevance_audit(
        audit_dir,
        prepare_corpus_relevance_audit(candidates, included_limit=10, excluded_limit=10),
    )
    key_by_id = {row["audit_item_id"]: row for row in _rows(audit_dir / "private_key.csv")}
    packet = audit_dir / "assessor_packet.csv"
    labels = {
        item_id: (
            "not_relevant"
            if key["inclusion_decision"] == "excluded"
            else "relevant"
        )
        for item_id, key in key_by_id.items()
    }
    _complete(packet, labels)

    score = score_corpus_relevance_audit(
        audit_dir / "private_key.csv", packet, audit_dir / "audit_manifest.json"
    )
    scores_dir = tmp_path / "scores"
    write_corpus_relevance_scores(scores_dir, score)

    assert score.status == "pass"
    overall = {
        row["metric"]: row
        for row in score.score_rows
        if row["scope_dimension"] == "overall"
    }
    assert overall["included_passage_relevance"]["point_rate"] == "1.000000"
    assert overall["excluded_candidate_missed_content"]["point_rate"] == "0.000000"
    assert float(str(overall["included_passage_relevance"]["wilson_lower"])) < 1
    assert float(str(overall["excluded_candidate_missed_content"]["wilson_upper"])) > 0
    manifest = json.loads((scores_dir / "score_manifest.json").read_text())
    assert manifest["gate_status"] == "pass"
    assert manifest["labels_are_human_attested"] is True
    assert manifest["completed_item_count"] == 20
    assert manifest["sample_counts"] == {"included": 10, "excluded": 10}


def test_score_fails_strict_excluded_threshold(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.csv"
    _write(candidates, FIELDS, _candidates())
    audit_dir = tmp_path / "audit"
    write_corpus_relevance_audit(
        audit_dir,
        prepare_corpus_relevance_audit(candidates, included_limit=10, excluded_limit=10),
    )
    key_by_id = {row["audit_item_id"]: row for row in _rows(audit_dir / "private_key.csv")}
    labels = {
        item_id: "relevant" if key["inclusion_decision"] == "included" else "not_relevant"
        for item_id, key in key_by_id.items()
    }
    excluded_id = next(
        item_id for item_id, key in key_by_id.items() if key["inclusion_decision"] == "excluded"
    )
    labels[excluded_id] = "relevant"
    _complete(audit_dir / "assessor_packet.csv", labels)

    score = score_corpus_relevance_audit(
        audit_dir / "private_key.csv",
        audit_dir / "assessor_packet.csv",
        audit_dir / "audit_manifest.json",
        maximum_excluded_miss_rate=0.10,
    )

    assert score.status == "fail"
    gate_results = score.manifest["gate_results"]
    assert isinstance(gate_results, dict)
    assert gate_results["excluded_candidate_missed_content"]["point_rate"] == 0.1


def test_score_rejects_a_private_key_changed_after_preparation(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.csv"
    _write(candidates, FIELDS, _candidates())
    audit_dir = tmp_path / "audit"
    write_corpus_relevance_audit(
        audit_dir,
        prepare_corpus_relevance_audit(candidates, included_limit=3, excluded_limit=3),
    )
    packet = audit_dir / "assessor_packet.csv"
    _complete(packet)
    key_path = audit_dir / "private_key.csv"
    key_rows = _rows(key_path)
    key_rows[0]["inclusion_decision"] = "excluded"
    _write(key_path, list(key_rows[0]), key_rows)

    with pytest.raises(ValueError, match="Private key SHA-256"):
        score_corpus_relevance_audit(key_path, packet, audit_dir / "audit_manifest.json")


def test_corpus_relevance_audit_commands_are_exposed() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "prepare-corpus-relevance-audit" in result.stdout
    assert "score-corpus-relevance-audit" in result.stdout
