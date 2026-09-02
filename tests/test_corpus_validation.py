import hashlib
import json
from pathlib import Path

from tag_edgar.corpus_validation import (
    STATUS_ABSENT,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_PENDING,
    corpus_validation_diagnostic,
    resolve_corpus_validation,
)

SHA = "a" * 64


def _audit_dir(tmp_path: Path, *, sha: str = SHA, attested: bool = False) -> Path:
    audit = tmp_path / "audit"
    audit.mkdir()
    (audit / "audit_manifest.json").write_text(
        json.dumps(
            {
                "audit_status": "pending_human_labels",
                "gate_status": "pending",
                "labels_present": attested,
                "labels_are_human_attested": attested,
                "candidate_csv_sha256": sha,
            }
        ),
        encoding="utf-8",
    )
    return audit


def _scores_dir(
    tmp_path: Path, gate: str, *, sha: str = SHA, audit_dir: Path | None = None
) -> Path:
    scores = tmp_path / "scores"
    scores.mkdir()
    audit_hash = (
        hashlib.sha256((audit_dir / "audit_manifest.json").read_bytes()).hexdigest()
        if audit_dir is not None
        else "c" * 64
    )
    (scores / "score_manifest.json").write_text(
        json.dumps(
            {
                "audit_status": "scored_human_labels",
                "gate_status": gate,
                "candidate_csv_sha256": sha,
                "labels_present": True,
                "labels_are_human_attested": True,
                "completed_item_count": 150,
                "sample_counts": {"included": 75, "excluded": 75},
                "audit_manifest_sha256": audit_hash,
            }
        ),
        encoding="utf-8",
    )
    return scores


def test_absent_evidence_is_an_unvalidated_corpus() -> None:
    state = resolve_corpus_validation(None, None, expected_candidate_sha256=SHA)
    assert state.status == STATUS_ABSENT
    assert state.accepted is False
    assert state.blocks_release is True
    assert corpus_validation_diagnostic(state)["status"] == "warning"


def test_prepared_packet_without_labels_is_pending(tmp_path: Path) -> None:
    state = resolve_corpus_validation(_audit_dir(tmp_path), expected_candidate_sha256=SHA)
    assert state.status == STATUS_PENDING
    assert state.candidate_csv_sha256 == SHA
    assert "no human labels" in state.detail
    assert corpus_validation_diagnostic(state)["status"] == "warning"


def test_attested_but_unscored_packet_is_still_pending(tmp_path: Path) -> None:
    state = resolve_corpus_validation(
        _audit_dir(tmp_path, attested=True), expected_candidate_sha256=SHA
    )
    assert state.status == STATUS_PENDING
    assert "not been scored" in state.detail


def test_scored_pass_is_accepted_only_for_the_matching_corpus(tmp_path: Path) -> None:
    scores = _scores_dir(tmp_path, "pass")
    accepted = resolve_corpus_validation(None, scores, expected_candidate_sha256=SHA)
    assert accepted.status == STATUS_PASSED
    assert accepted.accepted is True
    assert corpus_validation_diagnostic(accepted)["status"] == "pass"

    other_corpus = resolve_corpus_validation(None, scores, expected_candidate_sha256="b" * 64)
    assert other_corpus.status == STATUS_PENDING
    assert other_corpus.accepted is False
    assert "different passages.csv" in other_corpus.detail


def test_scored_fail_is_a_measured_failure(tmp_path: Path) -> None:
    state = resolve_corpus_validation(None, _scores_dir(tmp_path, "fail"))
    assert state.status == STATUS_FAILED
    assert corpus_validation_diagnostic(state)["status"] == "fail"


def test_scores_take_precedence_over_the_prepared_packet(tmp_path: Path) -> None:
    audit = _audit_dir(tmp_path)
    audit_manifest = json.loads((audit / "audit_manifest.json").read_text())
    audit_manifest["sample_counts"] = {"included": 75, "excluded": 75}
    (audit / "audit_manifest.json").write_text(json.dumps(audit_manifest), encoding="utf-8")
    scores = _scores_dir(tmp_path, "pass", audit_dir=audit)
    assert resolve_corpus_validation(audit, scores).status == STATUS_PASSED


def test_score_without_human_attestation_stays_pending(tmp_path: Path) -> None:
    scores = _scores_dir(tmp_path, "pass")
    manifest_path = scores / "score_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["labels_are_human_attested"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    state = resolve_corpus_validation(None, scores, expected_candidate_sha256=SHA)
    assert state.status == STATUS_PENDING
    assert state.accepted is False
    assert "human labels" in state.detail


def test_incomplete_or_inconsistent_score_counts_stay_pending(tmp_path: Path) -> None:
    scores = _scores_dir(tmp_path, "pass")
    manifest_path = scores / "score_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["completed_item_count"] = 149
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    state = resolve_corpus_validation(None, scores, expected_candidate_sha256=SHA)
    assert state.status == STATUS_PENDING
    assert state.accepted is False
    assert "every sampled row" in state.detail


def test_score_must_be_hash_linked_to_supplied_audit_manifest(tmp_path: Path) -> None:
    audit = _audit_dir(tmp_path)
    audit_manifest = json.loads((audit / "audit_manifest.json").read_text())
    audit_manifest["sample_counts"] = {"included": 75, "excluded": 75}
    (audit / "audit_manifest.json").write_text(json.dumps(audit_manifest), encoding="utf-8")
    scores = _scores_dir(tmp_path, "pass", audit_dir=audit)
    audit_manifest["selection_seed"] = "tampered-after-scoring"
    (audit / "audit_manifest.json").write_text(json.dumps(audit_manifest), encoding="utf-8")

    state = resolve_corpus_validation(audit, scores, expected_candidate_sha256=SHA)
    assert state.status == STATUS_PENDING
    assert state.accepted is False
    assert "not hash-linked" in state.detail


def test_diagnostic_row_uses_the_report_schema() -> None:
    row = corpus_validation_diagnostic(resolve_corpus_validation(None))
    assert set(row) == {"stage", "name", "value", "status", "detail"}
    assert row["stage"] == "corpus_validation"
    assert row["value"] == STATUS_ABSENT


def test_manifest_view_exposes_acceptance_explicitly(tmp_path: Path) -> None:
    manifest = resolve_corpus_validation(None, _scores_dir(tmp_path, "pass")).as_manifest()
    assert manifest["accepted"] is True
    assert manifest["status"] == STATUS_PASSED
    assert manifest["candidate_csv_sha256"] == SHA
