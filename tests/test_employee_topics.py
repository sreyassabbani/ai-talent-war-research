from pathlib import Path

import pytest

from tag_edgar.employee_topics import (
    TopicModelConfig,
    analyze_employee_topics,
    load_passages_csv,
)


def _row(
    passage_id: str,
    deal_id: str,
    text: str,
    *,
    duplicate_group: str | None = None,
    inclusion_status: str = "included",
) -> dict[str, str]:
    return {
        "passage_id": passage_id,
        "deal_id": deal_id,
        "document_id": f"document_{passage_id}",
        "document_family_id": f"family_{passage_id}",
        "source_url": f"https://example.test/{passage_id}",
        "raw_text": text,
        "model_text": text,
        "duplicate_group": duplicate_group or f"duplicate_{passage_id}",
        "inclusion_status": inclusion_status,
    }


def _synthetic_corpus() -> list[dict[str, str]]:
    themes = (
        "retention bonus cash incentive transaction award payment employee",
        "equity award stock option vesting continued service employee",
        "benefit plan health welfare compensation continuing employee",
    )
    rows: list[dict[str, str]] = []
    for deal in range(3):
        for theme, words in enumerate(themes):
            for example in range(4):
                passage_id = f"d{deal}_t{theme}_p{example}"
                rows.append(
                    _row(
                        passage_id,
                        f"deal_{deal}",
                        f"{words} provision mechanism clause {theme} example {example}",
                    )
                )
    return rows


def _model_config() -> TopicModelConfig:
    return TopicModelConfig(
        min_passages=12,
        min_deals=3,
        k_min=3,
        k_max=4,
        min_topic_families=2,
        min_topic_deals=2,
        nmf_iterations=50,
    )


def test_small_corpus_falls_back_after_filtering_and_deduplication() -> None:
    rows = [
        _row("p2", "deal_1", "retention bonus employee", duplicate_group="same"),
        _row("p1", "deal_1", "retention bonus employee", duplicate_group="same"),
        _row("p3", "deal_2", "equity vesting employee", inclusion_status="excluded"),
    ]

    result = analyze_employee_topics(rows, TopicModelConfig(min_passages=2))

    assert result.status == "qualitative_only"
    assert result.reason == "too_few_unique_passages"
    canonical = next(row for row in result.diagnostics if row.name == "canonical_passages")
    assert canonical.value == 1
    assert result.assignments == ()
    assert result.diagnostics[-1].status == "fail"


def test_topic_model_returns_long_assignments_deal_matrix_and_sensitivity() -> None:
    corpus = _synthetic_corpus()

    result = analyze_employee_topics(corpus, _model_config())

    assert result.status == "modeled"
    selected_k = int(next(row.value for row in result.diagnostics if row.name == "selected_k"))
    assert selected_k == 3
    assert len(result.topics) == selected_k
    assert len(result.assignments) == len(corpus) * selected_k
    assert len(result.sensitivity_assignments) == len(corpus)
    assert len({row.cluster_id for row in result.sensitivity_assignments}) == selected_k
    assert len(result.stability) == 3 * selected_k

    for passage_id in {row["passage_id"] for row in corpus}:
        weights = [row for row in result.assignments if row.passage_id == passage_id]
        assert sum(row.topic_weight for row in weights) == pytest.approx(1.0)
        assert sum(row.primary_topic for row in weights) == 1

    for deal_id in {row["deal_id"] for row in corpus}:
        weights = [row for row in result.deal_topics if row.deal_id == deal_id]
        assert sum(row.normalized_weight for row in weights) == pytest.approx(1.0)


def test_topic_model_is_deterministic() -> None:
    corpus = _synthetic_corpus()
    config = _model_config()

    first = analyze_employee_topics(corpus, config)
    second = analyze_employee_topics(reversed(corpus), config)

    assert first == second


def test_load_passages_csv_requires_the_full_contract(tmp_path: Path) -> None:
    source = tmp_path / "passages.csv"
    source.write_text("passage_id,deal_id\np1,d1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        load_passages_csv(source)
