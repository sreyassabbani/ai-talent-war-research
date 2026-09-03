import csv
import json
from pathlib import Path

import pytest

from tag_edgar.topic_subset import build_topic_subset_corpus, read_primary_passage_ids

PASSAGE_FIELDS = (
    "passage_id",
    "deal_id",
    "document_id",
    "document_family_id",
    "source_url",
    "document_type",
    "raw_text",
    "model_text",
    "duplicate_group",
    "inclusion_status",
)

SOURCE_FIELDS = ("occurrence_id", "passage_id", "deal_id", "source_url")


def _passage(
    passage_id: str, deal_id: str, document_type: str, status: str = "included"
) -> dict[str, str]:
    return {
        "passage_id": passage_id,
        "deal_id": deal_id,
        "document_id": f"doc_{passage_id}",
        "document_family_id": f"fam_{passage_id}",
        "source_url": f"https://example.test/{passage_id}",
        "document_type": document_type,
        "raw_text": f"raw {passage_id}",
        "model_text": f"model {passage_id}",
        "duplicate_group": f"grp_{passage_id}",
        "inclusion_status": status,
    }


def _assignment(passage_id: str, deal_id: str, topic_id: str, primary: bool) -> dict[str, str]:
    return {
        "passage_id": passage_id,
        "deal_id": deal_id,
        "topic_id": topic_id,
        "primary_topic": "true" if primary else "false",
        "topic_weight": "0.9" if primary else "0.1",
    }


def _write(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, Path]:
    """A three-passage corpus: two in topic_1 (one a press release), one in topic_2."""
    corpus_dir = tmp_path / "corpus"
    _write(
        corpus_dir / "passages.csv",
        PASSAGE_FIELDS,
        [
            _passage("p1", "d1", "EX-2.1"),
            _passage("p2", "d2", "EX-99.1"),
            _passage("p3", "d1", "EX-2.1"),
            _passage("p4", "d3", "EX-2.1", status="excluded"),
        ],
    )
    _write(
        corpus_dir / "passage_sources.csv",
        SOURCE_FIELDS,
        [
            {"occurrence_id": "o1", "passage_id": "p1", "deal_id": "d1", "source_url": "u1"},
            {"occurrence_id": "o2", "passage_id": "p1", "deal_id": "d9", "source_url": "u1"},
            {"occurrence_id": "o3", "passage_id": "p2", "deal_id": "d2", "source_url": "u2"},
            {"occurrence_id": "o4", "passage_id": "p3", "deal_id": "d1", "source_url": "u3"},
        ],
    )

    assignments = tmp_path / "canonical_topic_assignments.csv"
    _write(
        assignments,
        ("passage_id", "deal_id", "topic_id", "primary_topic", "topic_weight"),
        [
            _assignment("p1", "d1", "topic_1", True),
            _assignment("p1", "d1", "topic_2", False),
            _assignment("p2", "d2", "topic_1", True),
            _assignment("p2", "d2", "topic_2", False),
            _assignment("p3", "d1", "topic_2", True),
            _assignment("p3", "d1", "topic_1", False),
        ],
    )
    return assignments, corpus_dir


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def test_selects_only_the_parent_topic_primary_passages(corpus: tuple[Path, Path]) -> None:
    assignments, _ = corpus
    assert read_primary_passage_ids(assignments, "topic_1") == frozenset({"p1", "p2"})
    assert read_primary_passage_ids(assignments, "topic_2") == frozenset({"p3"})


def test_unknown_topic_raises_rather_than_returning_nothing(corpus: tuple[Path, Path]) -> None:
    assignments, _ = corpus
    with pytest.raises(ValueError, match="topic_9"):
        read_primary_passage_ids(assignments, "topic_9")


def test_subset_carries_passages_sources_and_manifest(
    corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    assignments, corpus_dir = corpus
    out = tmp_path / "subset"

    result = build_topic_subset_corpus(assignments, corpus_dir, out, parent_topic_id="topic_1")

    assert result.passage_count == 2
    assert {row["passage_id"] for row in _rows(out / "passages.csv")} == {"p1", "p2"}
    # Every occurrence of a retained passage travels, including the one filed under another deal.
    assert {row["occurrence_id"] for row in _rows(out / "passage_sources.csv")} == {
        "o1",
        "o2",
        "o3",
    }
    assert result.source_occurrence_count == 3

    manifest = json.loads((out / "subset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["parent_topic_id"] == "topic_1"
    assert manifest["passage_count"] == 2
    # The parent count is every included passage, not just the selected topic's.
    assert manifest["parent_included_passage_count"] == 3
    assert manifest["inputs"]["passages_csv"]["sha256"]


def test_subsets_partition_the_parent_corpus(corpus: tuple[Path, Path], tmp_path: Path) -> None:
    assignments, corpus_dir = corpus
    selected: list[set[str]] = []
    for topic in ("topic_1", "topic_2"):
        out = tmp_path / topic
        build_topic_subset_corpus(assignments, corpus_dir, out, parent_topic_id=topic)
        selected.append({row["passage_id"] for row in _rows(out / "passages.csv")})

    assert selected[0].isdisjoint(selected[1])
    assert selected[0] | selected[1] == {"p1", "p2", "p3"}


def test_document_type_exclusion_drops_press_releases(
    corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    assignments, corpus_dir = corpus
    out = tmp_path / "no_pr"

    result = build_topic_subset_corpus(
        assignments,
        corpus_dir,
        out,
        parent_topic_id="topic_1",
        exclude_document_type_prefixes=("ex-99",),
    )

    assert result.passage_count == 1
    assert result.excluded_document_type_count == 1
    assert {row["passage_id"] for row in _rows(out / "passages.csv")} == {"p1"}
    # Sources follow the passages that survived, not the ones originally selected.
    assert {row["occurrence_id"] for row in _rows(out / "passage_sources.csv")} == {"o1", "o2"}

    manifest = json.loads((out / "subset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["excluded_by_document_type"] == 1
    assert manifest["excluded_document_type_prefixes"] == ["EX-99"]


def test_assignments_from_a_different_run_are_rejected(
    corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    _, corpus_dir = corpus
    stale = tmp_path / "stale_assignments.csv"
    _write(
        stale,
        ("passage_id", "deal_id", "topic_id", "primary_topic", "topic_weight"),
        [_assignment("p_absent", "d1", "topic_1", True)],
    )

    with pytest.raises(ValueError, match="different runs"):
        build_topic_subset_corpus(stale, corpus_dir, tmp_path / "out", parent_topic_id="topic_1")


def test_excluding_every_passage_still_reports_the_exclusion(
    corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    assignments, corpus_dir = corpus
    result = build_topic_subset_corpus(
        assignments,
        corpus_dir,
        tmp_path / "empty",
        parent_topic_id="topic_2",
        exclude_document_type_prefixes=("EX-2",),
    )
    assert result.passage_count == 0
    assert result.excluded_document_type_count == 1
