"""Offline tests for deterministic topic modeling."""

from __future__ import annotations

import numpy as np
import pytest

from tag_edgar.topics100 import (
    TopicsConfig,
    agglomerative_sensitivity,
    deal_topic_matrix,
    fit_topics,
    leave_one_deal_out_stability,
)

# Two clearly separated synthetic passage families, repeated across deals.
RETENTION_TEXTS = [
    "employees receive retention bonus and continued employment through the protected period",
    "unvested stock options will vest upon a change in control with severance benefits",
    "retention awards remain payable if the employee remains employed through closing",
    "the merger agreement provides employee severance and benefit continuation terms",
]
TECHNOLOGY_TEXTS = [
    "the machine learning platform team will join our artificial intelligence division",
    "founders and research engineers bring deep neural network expertise to the company",
    "the acquisition adds computer vision scientists and data infrastructure engineers",
    "artificial intelligence researchers will continue building foundation models",
]


def _corpus() -> tuple[list[tuple[str, str]], list[str]]:
    texts: list[tuple[str, str]] = []
    deals: list[str] = []
    for deal_index in range(4):
        for repeat in range(2):
            for offset, template in enumerate(RETENTION_TEXTS + TECHNOLOGY_TEXTS):
                variation = f" deal{deal_index} item{repeat}{offset} clause"
                texts.append((f"p_{deal_index}_{repeat}_{offset}", template + variation))
                deals.append(f"deal_{deal_index}")
    return texts, deals


CONFIG = TopicsConfig(k_range=(3, 4), seed=7, max_features=2000, min_df=1, max_iter=400)


def test_fit_topics_is_deterministic_and_selects_k() -> None:
    texts, _ = _corpus()
    solution_a, diagnostics_a = fit_topics(texts, config=CONFIG)
    solution_b, diagnostics_b = fit_topics(texts, config=CONFIG)
    assert solution_a.k in {3, 4}
    assert np.array_equal(solution_a.labels, solution_b.labels)
    assert diagnostics_a == diagnostics_b
    assert all(terms for terms in solution_a.top_terms.values())


def test_topic_terms_separate_the_synthetic_families() -> None:
    texts, _ = _corpus()
    solution, _ = fit_topics(texts, config=CONFIG)
    joined = {" ".join(terms) for terms in solution.top_terms.values()}
    retention_hits = sum("retention" in text or "vesting" in text for text in joined)
    tech_hits = sum("machine" in text or "intelligence" in text for text in joined)
    assert retention_hits >= 1
    assert tech_hits >= 1


def test_weights_are_row_normalized_for_within_deal_comparison() -> None:
    texts, _ = _corpus()
    solution, _ = fit_topics(texts, config=CONFIG)
    sums = solution.weights.sum(axis=1)
    assert np.allclose(sums, 1.0, atol=0.01)


def test_deal_topic_matrix_rows_and_dominant_topic() -> None:
    texts, deals = _corpus()
    solution, _ = fit_topics(texts, config=CONFIG)
    matrix, label_map = deal_topic_matrix(texts, deals, solution)
    assert len(matrix) == 4
    assert set(label_map) == set(range(solution.k))
    for row in matrix:
        assert row["dominant_topic"] in label_map.values()
        total = sum(float(row[label_map[topic]]) for topic in range(solution.k))
        assert abs(total - 1.0) < 0.05


def test_agglomerative_sensitivity_returns_finite_ari() -> None:
    texts, _ = _corpus()
    solution, _ = fit_topics(texts, config=CONFIG)
    ari = agglomerative_sensitivity(texts, solution, config=CONFIG)
    assert -1.0 <= ari <= 1.0


def test_leave_one_deal_out_reports_jaccard() -> None:
    texts, deals = _corpus()
    rows = leave_one_deal_out_stability(texts, deals, config=CONFIG)
    assert len(rows) == 4
    assert all(row["status"] == "ok" for row in rows)
    assert all(0.0 <= float(row["mean_top_term_jaccard"]) <= 1.0 for row in rows)


def test_fit_topics_rejects_tiny_corpora() -> None:
    with pytest.raises(ValueError):
        fit_topics([("a", "text one"), ("b", "text two")], config=CONFIG)
