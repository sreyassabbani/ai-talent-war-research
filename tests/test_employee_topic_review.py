import csv
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tag_edgar.cli import app
from tag_edgar.employee_topic_review import (
    REVIEW_KEY_FIELDS,
    REVIEW_PACKET_FIELDS,
    TopicReviewConfig,
    prepare_topic_review,
    score_topic_review,
)


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _model_inputs(tmp_path: Path) -> tuple[Path, Path]:
    passages = tmp_path / "passages.csv"
    assignments = tmp_path / "assignments.csv"
    passage_rows: list[dict[str, str]] = []
    assignment_rows: list[dict[str, str]] = []
    for topic_number in (1, 2):
        for passage_number in range(12):
            passage_id = f"topic-{topic_number}-passage-{passage_number:02d}"
            passage_rows.append(
                {
                    "passage_id": passage_id,
                    "canonical_passage_id": passage_id,
                    "deal_id": f"deal-{passage_number % 3}",
                    "document_id": f"document-{topic_number}-{passage_number}",
                    "document_family_id": f"family-{topic_number}-{passage_number}",
                    "source_url": f"https://example.test/{passage_id}",
                    "raw_text": (
                        f"Substantive employee passage {passage_number} for theme {topic_number}."
                    ),
                }
            )
            assignment_rows.append(
                {
                    "passage_id": passage_id,
                    "canonical_passage_id": passage_id,
                    "deal_id": f"deal-{passage_number % 3}",
                    "document_id": f"document-{topic_number}-{passage_number}",
                    "document_family_id": f"family-{topic_number}-{passage_number}",
                    "source_url": f"https://example.test/{passage_id}",
                    "topic_id": f"topic_{topic_number}",
                    "topic_weight": str((passage_number + 1) / 12),
                    "primary_topic": "true",
                    "top_terms": f"employee|theme{topic_number}|benefit",
                }
            )
    _write(passages, list(passage_rows[0]), passage_rows)
    _write(assignments, list(assignment_rows[0]), assignment_rows)
    return assignments, passages


def _coded_file(
    template: Path,
    output: Path,
    reviewer_id: str,
    codes: list[str],
) -> None:
    rows = _rows(template)
    assert len(rows) == len(codes)
    for row, code in zip(rows, codes, strict=True):
        row["fit_code"] = code
        row["reviewer_id"] = reviewer_id
    _write(output, REVIEW_PACKET_FIELDS, rows)


def _codes_per_topic(template: Path, pattern: list[str]) -> list[str]:
    indexes: dict[str, int] = {}
    output: list[str] = []
    for row in _rows(template):
        topic = row["blind_topic_id"]
        index = indexes.get(topic, 0)
        output.append(pattern[index])
        indexes[topic] = index + 1
    return output


def test_prepare_writes_deterministic_blinded_top_ten_packet(tmp_path: Path) -> None:
    assignments, passages = _model_inputs(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = prepare_topic_review(assignments, passages, first)
    second_result = prepare_topic_review(assignments, passages, second)

    packet = _rows(first / "topic_review_packet.csv")
    key = _rows(first / "topic_review_key.csv")
    assert first_result.review_item_count == 20
    assert first_result.topic_count == 2
    assert first_result.packet_sha256 == second_result.packet_sha256
    assert (first / "topic_review_packet.csv").read_bytes() == (
        second / "topic_review_packet.csv"
    ).read_bytes()
    assert len(packet) == 20
    assert len(key) == 20
    assert set(packet[0]) == set(REVIEW_PACKET_FIELDS)
    assert "topic_id" not in packet[0]
    assert "topic_weight" not in packet[0]
    assert "deal_id" not in packet[0]
    assert "source_url" not in packet[0]
    assert all(not row["fit_code"] and not row["reviewer_id"] for row in packet)
    assert {row["topic_id"] for row in key} == {"topic_1", "topic_2"}
    assert set(key[0]) == set(REVIEW_KEY_FIELDS)
    selected = {row["passage_id"] for row in key if row["topic_id"] == "topic_1"}
    assert "topic-1-passage-00" not in selected
    assert "topic-1-passage-01" not in selected


def test_prepare_seed_changes_order_without_changing_selected_passages(tmp_path: Path) -> None:
    assignments, passages = _model_inputs(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"

    prepare_topic_review(
        assignments, passages, first, config=TopicReviewConfig(seed=1)
    )
    prepare_topic_review(
        assignments, passages, second, config=TopicReviewConfig(seed=2)
    )

    first_key = _rows(first / "topic_review_key.csv")
    second_key = _rows(second / "topic_review_key.csv")
    assert [row["passage_id"] for row in first_key] != [
        row["passage_id"] for row in second_key
    ]
    assert {row["passage_id"] for row in first_key} == {
        row["passage_id"] for row in second_key
    }


def test_score_reports_reviewer_and_pooled_fit_and_passes_agreement(tmp_path: Path) -> None:
    assignments, passages = _model_inputs(tmp_path)
    prepared = tmp_path / "prepared"
    prepare_topic_review(assignments, passages, prepared)
    codes = _codes_per_topic(
        prepared / "reviewer_1.csv", ["fit"] * 8 + ["partial", "not_fit"]
    )
    reviewer_one = tmp_path / "reviewer-alex.csv"
    reviewer_two = tmp_path / "reviewer-blair.csv"
    _coded_file(prepared / "reviewer_1.csv", reviewer_one, "alex", codes)
    _coded_file(prepared / "reviewer_2.csv", reviewer_two, "blair", codes)

    result = score_topic_review(
        prepared / "topic_review_key.csv",
        reviewer_one,
        reviewer_two,
        tmp_path / "scored",
    )

    assert result.status == "pass"
    assert len(result.topic_scores) == 2
    for row in result.topic_scores:
        assert row["reviewer_1_fit_rate"] == "0.8"
        assert row["reviewer_2_fit_rate"] == "0.8"
        assert row["pooled_fit_rate"] == "0.8"
        assert row["pooled_partial_rate"] == "0.1"
        assert row["exact_agreement_rate"] == "1"
        assert row["cohen_kappa"] == "1"
        assert row["agreement_metric_used"] == "cohen_kappa"
    assert result.diagnostics[-1]["name"] == "topic_review_release_gate"
    assert result.diagnostics[-1]["status"] == "pass"


def test_score_discloses_ac1_fallback_when_kappa_is_undefined(tmp_path: Path) -> None:
    assignments, passages = _model_inputs(tmp_path)
    prepared = tmp_path / "prepared"
    prepare_topic_review(assignments, passages, prepared)
    codes = ["fit"] * 20
    reviewer_one = tmp_path / "reviewer-alex.csv"
    reviewer_two = tmp_path / "reviewer-blair.csv"
    _coded_file(prepared / "reviewer_1.csv", reviewer_one, "alex", codes)
    _coded_file(prepared / "reviewer_2.csv", reviewer_two, "blair", codes)

    result = score_topic_review(
        prepared / "topic_review_key.csv",
        reviewer_one,
        reviewer_two,
        tmp_path / "scored",
    )

    assert result.status == "pass"
    for row in result.topic_scores:
        assert row["cohen_kappa"] == ""
        assert row["cohen_kappa_status"] == "undefined_zero_denominator"
        assert row["gwet_ac1"] == "1"
        assert row["agreement_metric_used"] == "gwet_ac1"
    agreement = next(
        row
        for row in result.diagnostics
        if row["name"] == "overall_interrater_agreement"
    )
    assert "Cohen kappa=undefined" in agreement["detail"]
    assert "AC1 is used only" in agreement["detail"]


def test_score_fails_low_fit_and_low_agreement_without_changing_codes(tmp_path: Path) -> None:
    assignments, passages = _model_inputs(tmp_path)
    prepared = tmp_path / "prepared"
    prepare_topic_review(assignments, passages, prepared)
    reviewer_one = tmp_path / "reviewer-alex.csv"
    reviewer_two = tmp_path / "reviewer-blair.csv"
    _coded_file(
        prepared / "reviewer_1.csv",
        reviewer_one,
        "alex",
        _codes_per_topic(
            prepared / "reviewer_1.csv", ["fit"] * 8 + ["partial", "not_fit"]
        ),
    )
    _coded_file(
        prepared / "reviewer_2.csv",
        reviewer_two,
        "blair",
        _codes_per_topic(
            prepared / "reviewer_2.csv", ["not_fit"] * 3 + ["fit"] * 7
        ),
    )

    result = score_topic_review(
        prepared / "topic_review_key.csv",
        reviewer_one,
        reviewer_two,
        tmp_path / "scored",
    )

    assert result.status == "fail"
    assert any(
        row["name"].endswith("reviewer_2_fit_rate") and row["status"] == "fail"
        for row in result.diagnostics
    )
    assert any(
        row["name"].endswith("interrater_agreement") and row["status"] == "fail"
        for row in result.diagnostics
    )


@pytest.mark.parametrize("problem", ["missing", "bad_code", "same_reviewer"])
def test_score_rejects_invalid_or_non_independent_coding(
    tmp_path: Path, problem: str
) -> None:
    assignments, passages = _model_inputs(tmp_path)
    prepared = tmp_path / "prepared"
    prepare_topic_review(assignments, passages, prepared)
    codes = ["fit"] * 20
    reviewer_one = tmp_path / "reviewer-alex.csv"
    reviewer_two = tmp_path / "reviewer-blair.csv"
    _coded_file(prepared / "reviewer_1.csv", reviewer_one, "alex", codes)
    _coded_file(
        prepared / "reviewer_2.csv",
        reviewer_two,
        "alex" if problem == "same_reviewer" else "blair",
        codes,
    )
    if problem in {"missing", "bad_code"}:
        rows = _rows(reviewer_two)
        if problem == "missing":
            rows.pop()
        else:
            rows[0]["fit_code"] = "probably"
        _write(reviewer_two, REVIEW_PACKET_FIELDS, rows)

    with pytest.raises(ValueError):
        score_topic_review(
            prepared / "topic_review_key.csv",
            reviewer_one,
            reviewer_two,
            tmp_path / "scored",
        )


def test_review_cli_prepares_and_scores_offline(tmp_path: Path) -> None:
    assignments, passages = _model_inputs(tmp_path)
    prepared = tmp_path / "prepared"
    runner = CliRunner()

    prepare_result = runner.invoke(
        app,
        [
            "prepare-employee-topic-review",
            str(assignments),
            str(passages),
            "--output-dir",
            str(prepared),
        ],
    )

    assert prepare_result.exit_code == 0, prepare_result.output
    reviewer_one = tmp_path / "reviewer-alex.csv"
    reviewer_two = tmp_path / "reviewer-blair.csv"
    _coded_file(prepared / "reviewer_1.csv", reviewer_one, "alex", ["fit"] * 20)
    _coded_file(prepared / "reviewer_2.csv", reviewer_two, "blair", ["fit"] * 20)
    scored = tmp_path / "scored"

    score_result = runner.invoke(
        app,
        [
            "score-employee-topic-review",
            str(prepared / "topic_review_key.csv"),
            str(reviewer_one),
            str(reviewer_two),
            "--output-dir",
            str(scored),
        ],
    )

    assert score_result.exit_code == 0, score_result.output
    assert "Human review release gate: pass" in score_result.output
    assert (scored / "topic_review_scores.csv").exists()
    assert (scored / "topic_review_diagnostics.csv").exists()
