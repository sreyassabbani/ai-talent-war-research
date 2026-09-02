"""Tests for the cycle-5 additions: fit-balance modes, the architecture/topic cross-table, and the
corpus-validation label on tone output."""

import csv
import json
from pathlib import Path

import pytest

from tag_edgar.architecture_topic_crosstable import (
    CROSSTABLE_FIELDS,
    build_crosstable,
    write_crosstable,
)
from tag_edgar.corpus_validation import STATUS_PENDING, CorpusValidationState
from tag_edgar.employee_tone import analyze_employee_tone
from tag_edgar.employee_topics import (
    FIT_BALANCE_MODES,
    PassageRow,
    TopicModelConfig,
    _balanced_fit_indices,
)

PENDING = CorpusValidationState(STATUS_PENDING, "pending", "c" * 64, "no labels yet", "x")


def _passage(index: int, deal: str, family: str, source_family: str) -> PassageRow:
    return PassageRow(
        passage_id=f"p{index:03d}",
        deal_id=deal,
        document_id=f"doc-{deal}",
        document_family_id=family,
        source_url=f"https://www.sec.gov/Archives/{deal}/{index}.htm",
        raw_text="Continuing employees receive base salary and benefits for twelve months.",
        model_text="continuing employees receive base salary and benefits for twelve months",
        duplicate_group=f"g{index}",
        inclusion_status="included",
        source_document_family_id=source_family,
    )


def test_fit_balance_modes_are_validated() -> None:
    assert FIT_BALANCE_MODES == ("deal", "source_family", "none")
    with pytest.raises(ValueError, match="fit_balance"):
        from tag_edgar.employee_topics import _validate_config

        _validate_config(TopicModelConfig(fit_balance="random"))


def test_source_family_balance_spreads_the_cap_across_document_families() -> None:
    # Deal A dominates with 20 unique families, all from one source family (merger agreements);
    # deals B and C contribute a few passages each from press releases and proxies.
    rows: list[PassageRow] = []
    index = 0
    for family in range(20):
        rows.append(_passage(index, "deal-a", f"fam-a-{family}", "ex-2.1"))
        index += 1
    for family in range(3):
        rows.append(_passage(index, "deal-b", f"fam-b-{family}", "ex-99.1"))
        index += 1
    for family in range(3):
        rows.append(_passage(index, "deal-c", f"fam-c-{family}", "defm14a"))
        index += 1

    limit = 9
    by_deal = _balanced_fit_indices(rows, limit, seed=7, balance="deal")
    by_source = _balanced_fit_indices(rows, limit, seed=7, balance="source_family")
    unbalanced = _balanced_fit_indices(rows, limit, seed=7, balance="none")

    assert len(by_deal) == len(by_source) == len(unbalanced) == limit

    def source_shares(indices: tuple[int, ...]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in indices:
            counts[rows[i].source_document_family_id] = (
                counts.get(rows[i].source_document_family_id, 0) + 1
            )
        return counts

    # Round-robin over source families gives each of the three families three slots.
    assert source_shares(by_source) == {"ex-2.1": 3, "ex-99.1": 3, "defm14a": 3}
    # Deal balancing also caps deal A, but does so by deal, not by document family.
    assert source_shares(by_deal)["ex-2.1"] == 3
    # Plain truncation keeps whatever the stable hash order yields; it is deterministic.
    assert unbalanced == _balanced_fit_indices(rows, limit, seed=7, balance="none")
    assert by_source == _balanced_fit_indices(rows, limit, seed=7, balance="source_family")


def test_passage_rows_without_a_source_family_still_parse() -> None:
    from tag_edgar.employee_topics import _passage_from_mapping

    row = _passage_from_mapping(
        {
            "passage_id": "p1",
            "deal_id": "d",
            "document_id": "doc",
            "document_family_id": "f",
            "source_url": "https://www.sec.gov/x.htm",
            "raw_text": "t",
            "model_text": "t",
            "duplicate_group": "g",
            "inclusion_status": "included",
        }
    )
    assert row.source_document_family_id == ""


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_crosstable_keeps_zero_and_unknown_deals_visible_and_links_examples(
    tmp_path: Path,
) -> None:
    architecture = _write(
        tmp_path / "deal_architecture.csv",
        [
            "deal_id",
            "deal_name",
            "legal_transaction_form",
            "scope_and_control",
            "workforce_movement",
            "talent_motive_explicit",
            "machine_suggested_archetypes",
            "archetype_ambiguity",
            "review_status",
        ],
        [
            {
                "deal_id": "deal-1",
                "deal_name": "A–B",
                "legal_transaction_form": "statutory_merger",
                "scope_and_control": "entity_equity|control_transferred",
                "workforce_movement": "group_continuing_employees",
                "talent_motive_explicit": "unknown",
                "machine_suggested_archetypes": "full_acquisition",
                "archetype_ambiguity": "medium",
                "review_status": "machine_suggested_pending_human_review",
            },
            {
                "deal_id": "deal-2",
                "deal_name": "C–D",
                "legal_transaction_form": "unknown",
                "scope_and_control": "unknown",
                "workforce_movement": "unknown",
                "talent_motive_explicit": "unknown",
                "machine_suggested_archetypes": "unknown",
                "archetype_ambiguity": "high",
                "review_status": "machine_suggested_pending_human_review",
            },
        ],
    )
    matrix = _write(
        tmp_path / "deal_topic_matrix.csv",
        ["deal_id", "topic_id", "weight_sum", "normalized_weight", "primary_passage_count", "zero_state"],
        [
            {
                "deal_id": "deal-1",
                "topic_id": "topic_1",
                "weight_sum": "2.0",
                "normalized_weight": "0.7",
                "primary_passage_count": "2",
                "zero_state": "",
            },
            {
                "deal_id": "deal-1",
                "topic_id": "topic_2",
                "weight_sum": "0.5",
                "normalized_weight": "0.3",
                "primary_passage_count": "1",
                "zero_state": "",
            },
        ],
    )
    url = "https://www.sec.gov/Archives/deal-1/ex21.htm"
    assignments = _write(
        tmp_path / "topic_assignments.csv",
        ["passage_id", "deal_id", "topic_id", "topic_weight", "primary_topic", "source_url", "source_highlight_url"],
        [
            {
                "passage_id": "p1",
                "deal_id": "deal-1",
                "topic_id": "topic_1",
                "topic_weight": "0.9",
                "primary_topic": "true",
                "source_url": url,
                "source_highlight_url": url + "#:~:text=Continuing%20employees",
            },
            {
                "passage_id": "p2",
                "deal_id": "deal-1",
                "topic_id": "topic_1",
                "topic_weight": "0.4",
                "primary_topic": "true",
                "source_url": url,
                "source_highlight_url": url + "#:~:text=Other",
            },
        ],
    )

    table = build_crosstable(architecture, matrix, assignments, PENDING)
    write_crosstable(tmp_path / "out", table)

    rows = table.rows
    assert all(set(row) == set(CROSSTABLE_FIELDS) for row in rows)
    written = (tmp_path / "out" / "architecture_topic_crosstable.csv").read_text(encoding="utf-8")
    assert written.splitlines()[0] == ",".join(CROSSTABLE_FIELDS)
    deal1 = [row for row in rows if row["deal_id"] == "deal-1"]
    assert [row["topic_id"] for row in deal1] == ["topic_1", "topic_2"]
    # The highest-weight primary passage is the linked example, with its paragraph highlight.
    assert deal1[0]["example_passage_id"] == "p1"
    assert deal1[0]["example_source_highlight_url"].endswith("#:~:text=Continuing%20employees")
    # A deal with no topic rows stays visible with an explicit zero state.
    deal2 = [row for row in rows if row["deal_id"] == "deal-2"]
    assert len(deal2) == 1
    assert deal2[0]["zero_state"] == "deal_absent_from_topic_matrix"
    assert deal2[0]["machine_suggested_archetypes"] == "unknown"
    # Every row carries both layers' validation labels and the descriptive boundary.
    for row in rows:
        assert row["corpus_validation_status"] == STATUS_PENDING
        assert row["architecture_review_status"] == "machine_suggested_pending_human_review"
        assert "not causal" in row["interpretation"]
    manifest = json.loads((tmp_path / "out" / "crosstable_manifest.json").read_text())
    assert manifest["deals_without_topic_rows"] == ["deal-2"]
    assert manifest["corpus_validation"]["accepted"] is False


def test_tone_manifest_records_corpus_validation_state(tmp_path: Path) -> None:
    passages = _write(
        tmp_path / "passages.csv",
        ["passage_id", "deal_id", "document_family_id", "document_type", "text", "inclusion_status"],
        [
            {
                "passage_id": f"p{i}",
                "deal_id": f"deal-{i % 2}",
                "document_family_id": f"f{i}",
                "document_type": "EX-2.1",
                "text": (
                    "Continuing employees shall receive base salary, benefits, and severance "
                    "protection for twelve months following the closing."
                ),
                "inclusion_status": "included",
            }
            for i in range(6)
        ],
    )
    unlabelled = analyze_employee_tone(passages)
    assert unlabelled.manifest["corpus_validation"] == {
        "status": "no_corpus_validation_evidence",
        "accepted": False,
    }
    assert unlabelled.manifest["interpretation_status"] == (
        "secondary_diagnostic_corpus_not_validated"
    )

    pending = analyze_employee_tone(passages, corpus_validation=PENDING)
    assert pending.manifest["corpus_validation"]["status"] == STATUS_PENDING
    assert pending.manifest["interpretation_status"] == "secondary_diagnostic_corpus_not_validated"
