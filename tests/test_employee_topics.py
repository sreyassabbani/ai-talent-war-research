from dataclasses import replace
from pathlib import Path

import pytest

from tag_edgar import employee_topics
from tag_edgar.employee_topics import (
    AssignmentRow,
    StabilityRow,
    TopicModelConfig,
    analyze_employee_topics,
    load_passages_csv,
    propagate_duplicate_assignments,
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


def test_fit_sample_is_bounded_but_all_passages_receive_assignments() -> None:
    corpus = _synthetic_corpus()
    config = TopicModelConfig(
        min_passages=12,
        min_deals=3,
        k_min=3,
        k_max=3,
        min_topic_families=2,
        min_topic_deals=2,
        max_fit_passages=24,
        nmf_iterations=30,
    )

    result = analyze_employee_topics(corpus, config)

    assert result.status == "modeled"
    fit_count = next(row.value for row in result.diagnostics if row.name == "fit_passages")
    projected = next(
        row.value for row in result.diagnostics if row.name == "projected_passages"
    )
    assert fit_count == 24
    assert projected == 12
    assert len(result.assignments) == len(corpus) * 3
    assert len(result.sensitivity_assignments) == len(corpus)


def test_fit_sampling_uses_one_passage_per_deal_provision_family() -> None:
    corpus = _synthetic_corpus()
    corpus[1]["document_family_id"] = corpus[0]["document_family_id"]

    result = analyze_employee_topics(corpus, _model_config())

    assert result.status == "modeled"
    fit_count = next(row.value for row in result.diagnostics if row.name == "fit_passages")
    fit_families = next(
        row.value for row in result.diagnostics if row.name == "fit_family_count"
    )
    assert fit_count == len(corpus) - 1
    assert fit_families == fit_count
    assert len(result.assignments) == len(corpus) * 3


def test_duplicate_assignments_propagate_across_deals() -> None:
    source = [
        _row("p1", "deal_1", "retention bonus employee", duplicate_group="shared"),
        _row("p2", "deal_2", "retention bonus employee", duplicate_group="shared"),
    ]
    canonical = (
        AssignmentRow(
            "p1", "deal_1", "document_p1", "family_p1", "https://example.test/p1",
            "topic_1", 0.8, True,
        ),
        AssignmentRow(
            "p1", "deal_1", "document_p1", "family_p1", "https://example.test/p1",
            "topic_2", 0.2, False,
        ),
    )

    propagated = propagate_duplicate_assignments(source, canonical)

    assert {(row.passage_id, row.deal_id) for row in propagated} == {
        ("p1", "deal_1"),
        ("p2", "deal_2"),
    }
    assert [row.topic_weight for row in propagated if row.passage_id == "p2"] == [0.8, 0.2]
    assert all(row.document_id == "document_p2" for row in propagated if row.passage_id == "p2")


def test_modeled_cross_deal_duplicate_is_fit_once_but_reported_in_both_deals() -> None:
    corpus = _synthetic_corpus()
    duplicate = dict(corpus[0])
    duplicate.update(
        passage_id="cross_deal_copy",
        deal_id="deal_2",
        document_id="document_cross_deal_copy",
        document_family_id="family_cross_deal_copy",
        source_url="https://example.test/cross_deal_copy",
        duplicate_group=corpus[0]["duplicate_group"],
    )
    corpus.append(duplicate)

    result = analyze_employee_topics(corpus, _model_config())

    assert result.status == "modeled"
    assert any(row.passage_id == "cross_deal_copy" for row in result.assignments)
    canonical_count = next(
        row.value for row in result.diagnostics if row.name == "canonical_passages"
    )
    assert canonical_count == len(corpus) - 1
    assert any(row.deal_id == "deal_2" for row in result.deal_topics)


def test_document_frequency_counts_documents_not_repeated_tokens() -> None:
    rows = [
        _row("p1", "deal_1", "alphaword alphaword alphaword alphaword"),
        _row("p2", "deal_2", "betaword betaword betaword betaword"),
        _row("p3", "deal_3", "gammaword gammaword gammaword gammaword"),
    ]
    config = TopicModelConfig(
        min_passages=3,
        min_deals=3,
        k_min=2,
        k_max=2,
        min_df=2,
        max_df_ratio=1.0,
    )

    result = analyze_employee_topics(rows, config)

    assert result.status == "qualitative_only"
    assert result.reason == "insufficient_vocabulary"
    vocabulary = next(row for row in result.diagnostics if row.name == "vocabulary_size")
    assert vocabulary.value == 0


def test_low_agglomerative_agreement_is_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        employee_topics,
        "_agglomerative_fit_predict",
        lambda fitted, full, k: [0] * len(full.rows),
    )

    result = analyze_employee_topics(_synthetic_corpus(), _model_config())

    diagnostic = next(
        row for row in result.diagnostics if row.name == "agglomerative_adjusted_rand"
    )
    assert float(diagnostic.value) == pytest.approx(0.0)
    assert diagnostic.status == "warning"


def test_each_unstable_topic_is_provisional_and_overall_gate_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unstable(corpus, fit, config):  # type: ignore[no-untyped-def]
        output = []
        for deal_id in sorted({row.deal_id for row in corpus.rows}):
            for topic in range(fit.k):
                similarity = 0.10 if topic == 0 else 0.99
                output.append(
                    StabilityRow(
                        left_out_deal_id=deal_id,
                        topic_id=f"topic_{topic + 1}",
                        aligned_topic_id=f"held_topic_{topic + 1}",
                        cosine_similarity=similarity,
                        recovered=similarity >= config.stability_threshold,
                    )
                )
        return tuple(output)

    monkeypatch.setattr(employee_topics, "_leave_one_deal_out", unstable)

    result = analyze_employee_topics(_synthetic_corpus(), _model_config())

    topic_one = next(row for row in result.diagnostics if row.name == "topic_1_recovery_rate")
    topic_two = next(row for row in result.diagnostics if row.name == "topic_2_recovery_rate")
    overall = next(row for row in result.diagnostics if row.name == "overall_recovery_rate")
    assert topic_one.status == "warning"
    assert topic_two.status == "pass"
    assert overall.status == "warning"


def test_generic_legal_topic_terms_cannot_pass_quality_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = employee_topics._topic_rows

    def generic_first_topic(*args, **kwargs):  # type: ignore[no-untyped-def]
        topics = list(original(*args, **kwargs))
        topics[0] = replace(
            topics[0],
            top_terms=(
                "agreement",
                "section",
                "company",
                "parent",
                "party",
                "purchaser",
                "seller",
                "shall",
                "pursuant",
                "thereof",
            ),
        )
        return tuple(topics)

    monkeypatch.setattr(employee_topics, "_topic_rows", generic_first_topic)

    result = analyze_employee_topics(_synthetic_corpus(), _model_config())

    diagnostic = next(
        row for row in result.diagnostics if row.name == "topic_1_generic_top_term_ratio"
    )
    assert diagnostic.value == 1.0
    assert diagnostic.status == "warning"


def test_load_passages_csv_requires_the_full_contract(tmp_path: Path) -> None:
    source = tmp_path / "passages.csv"
    source.write_text("passage_id,deal_id\np1,d1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        load_passages_csv(source)
