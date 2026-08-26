"""Deterministic unsupervised employee-disclosure topic modeling for the AI-deal corpus.

Primary model: word/bigram TF-IDF followed by NMF over a prespecified K range with fixed
seeds. Model selection uses topic stability across two fixed deterministic half-samples,
not human-predefined categories or an arbitrary favorite K. Sensitivity checks use
agglomerative clustering and leave-one-deal-out refits. All outputs remain descriptive;
themes with weak stability are labeled exploratory/provisional.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import normalize

_TOPIC_STOP_WORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "numbertoken",
        "urltoken",
        "font",
        "style",
        "margin",
        "top",
        "bottom",
        "td",
        "tr",
        "valign",
        "width",
        "table",
        "align",
        "bgcolor",
        "collapse",
        "nbsp",
        "e8f0f8",
        "pt",
    ]
)


@dataclass(frozen=True)
class TopicsConfig:
    k_range: tuple[int, ...] = (3, 4, 5, 6, 7)
    seed: int = 20260826
    max_features: int = 5000
    min_df: int = 2
    ngram_range: tuple[int, int] = (1, 2)
    max_iter: int = 600
    stability_threshold: float = 0.55


@dataclass(frozen=True)
class TopicSolution:
    k: int
    stability: float
    labels: np.ndarray
    weights: np.ndarray
    vocabulary: list[str]
    top_terms: dict[int, tuple[str, ...]]


def _vectorizer(config: TopicsConfig) -> TfidfVectorizer:
    return TfidfVectorizer(
        max_features=config.max_features,
        min_df=config.min_df,
        ngram_range=config.ngram_range,
        sublinear_tf=True,
        norm="l2",
        stop_words=sorted(_TOPIC_STOP_WORDS),
    )


def _fit_nmf(matrix: Any, k: int, seed: int, max_iter: int) -> tuple[NMF, np.ndarray]:
    model = NMF(
        n_components=k,  # pyright: ignore[reportArgumentType]
        random_state=seed,
        init="nndsvda",
        l1_ratio=0.0,
        max_iter=max_iter,
    )
    weights = cast(np.ndarray, model.fit_transform(matrix))
    return model, weights


def top_terms_for(
    model: NMF, feature_names: np.ndarray, top_n: int = 12
) -> dict[int, tuple[str, ...]]:
    output: dict[int, tuple[str, ...]] = {}
    for topic_index, row in enumerate(model.components_):
        order = np.argsort(-row)[:top_n]
        output[topic_index] = tuple(feature_names[order])
    return output


def _half_split(texts: list[tuple[str, str]]) -> tuple[list[int], list[int]]:
    """Deterministic halves keyed by sha256 of the stable passage id."""
    left: list[int] = []
    right: list[int] = []
    for index, (passage_id, _) in enumerate(texts):
        digest = hashlib.sha256(passage_id.encode("utf-8")).hexdigest()
        (left if int(digest[:16], 16) % 2 == 0 else right).append(index)
    if not left or not right:
        indices = list(range(len(texts)))
        middle = len(indices) // 2
        return indices[:middle], indices[middle:]
    return left, right


def _half_stability(texts: list[tuple[str, str]], k: int, config: TopicsConfig) -> float:
    left_idx, right_idx = _half_split(texts)
    similarities: list[float] = []
    # Fit on each half with its own vectorizer, then compare term spaces via shared terms.
    models: list[tuple[NMF, TfidfVectorizer]] = []
    for subset in (left_idx, right_idx):
        sub_texts = [texts[i][1] for i in subset]
        vectorizer = _vectorizer(config)
        try:
            sub_matrix = vectorizer.fit_transform(sub_texts)
        except ValueError:
            return 0.0
        model, _ = _fit_nmf(sub_matrix, k, config.seed, config.max_iter)
        models.append((model, vectorizer))
    first_model, second_model = models[0][0], models[1][0]
    first_terms = [
        set(top_terms_for(first_model, np.array(models[0][1].get_feature_names_out()))[i])
        for i in range(k)
    ]
    second_terms = [
        set(top_terms_for(second_model, np.array(models[1][1].get_feature_names_out()))[i])
        for i in range(k)
    ]
    for a_terms in first_terms:
        best = 0.0
        for b_terms in second_terms:
            union = a_terms | b_terms
            score = len(a_terms & b_terms) / len(union) if union else 0.0
            best = max(best, score)
        similarities.append(best)
    return float(np.mean(similarities)) if similarities else 0.0


def fit_topics(
    texts: list[tuple[str, str]], *, config: TopicsConfig | None = None
) -> tuple[TopicSolution, list[dict[str, object]]]:
    """Fit the prespecified K range and select the most stable K deterministically."""
    cfg = config or TopicsConfig()
    if len(texts) < 6:
        raise ValueError("Topic modeling needs at least six passages.")
    vectorizer = _vectorizer(cfg)
    matrix = cast(Any, vectorizer.fit_transform([text for _, text in texts]))
    feature_names = np.array(vectorizer.get_feature_names_out())

    diagnostics: list[dict[str, object]] = []
    best_stability = -1.0
    best_k: int | None = None
    for k in sorted(set(cfg.k_range)):
        if k >= matrix.shape[0]:
            continue
        stability = _half_stability(texts, k, cfg)
        model, _ = _fit_nmf(matrix, k, cfg.seed, cfg.max_iter)
        diagnostics.append(
            {
                "k": k,
                "half_sample_stability": round(stability, 4),
                "reconstruction_error": round(float(model.reconstruction_err_), 4),
                "n_passages": matrix.shape[0],
                "n_features": matrix.shape[1],
            }
        )
        if stability > best_stability + 1e-12 or (
            abs(stability - best_stability) <= 1e-12 and (best_k is None or k < best_k)
        ):
            best_stability = stability
            best_k = k

    if best_k is None:
        raise ValueError("No feasible K in the configured range for this corpus size.")
    model, weights = _fit_nmf(matrix, best_k, cfg.seed, cfg.max_iter)
    labels = np.argmax(weights, axis=1)
    normalized_weights = cast(np.ndarray, normalize(weights, norm="l1", axis=1))
    solution = TopicSolution(
        k=best_k,
        stability=round(best_stability, 4),
        labels=labels,
        weights=normalized_weights,
        vocabulary=list(feature_names),
        top_terms=top_terms_for(model, feature_names),
    )
    return solution, diagnostics


def topic_label(top_terms: tuple[str, ...]) -> str:
    digest = hashlib.sha256(" ".join(top_terms).encode()).hexdigest()[:8]
    return f"topic_{digest}"


def deal_topic_matrix(
    texts: list[tuple[str, str]],
    passage_deals: list[str],
    solution: TopicSolution,
) -> tuple[list[dict[str, object]], dict[int, str]]:
    """Within-deal-normalized topic prevalence: mean row-normalized weight per deal."""
    grouped: dict[str, list[int]] = {}
    for index, deal_id in enumerate(passage_deals):
        grouped.setdefault(deal_id, []).append(index)
    label_map = {
        topic_index: topic_label(terms) for topic_index, terms in solution.top_terms.items()
    }
    rows: list[dict[str, object]] = []
    for deal_id in sorted(grouped):
        indices = grouped[deal_id]
        row: dict[str, object] = {"deal_id": deal_id, "passage_count": len(indices)}
        dominant_counts: dict[int, int] = {}
        for topic_index in range(solution.k):
            values = [float(solution.weights[i, topic_index]) for i in indices]
            row[label_map[topic_index]] = round(sum(values) / len(values), 4)
        for i in indices:
            dominant = int(solution.labels[i])
            dominant_counts[dominant] = dominant_counts.get(dominant, 0) + 1
        row["dominant_topic"] = label_map[
            max(dominant_counts, key=lambda key_value: dominant_counts[key_value])
        ]
        rows.append(row)
    return rows, label_map


def agglomerative_sensitivity(
    texts: list[tuple[str, str]], solution: TopicSolution, *, config: TopicsConfig | None = None
) -> float:
    """ARI between NMF assignments and fixed-seed agglomerative clustering."""
    cfg = config or TopicsConfig()
    vectorizer = _vectorizer(cfg)
    matrix = cast(Any, vectorizer.fit_transform([text for _, text in texts]))
    clusterer = AgglomerativeClustering(n_clusters=solution.k, metric="cosine", linkage="average")
    alt_labels = clusterer.fit_predict(matrix.toarray())
    return round(float(adjusted_rand_score(solution.labels, alt_labels)), 4)


def leave_one_deal_out_stability(
    texts: list[tuple[str, str]],
    passage_deals: list[str],
    *,
    config: TopicsConfig | None = None,
    max_deals: int = 10,
) -> list[dict[str, object]]:
    """Refit without each sampled deal's passages and record top-term overlap."""
    cfg = config or TopicsConfig()
    baseline_vectorizer = _vectorizer(cfg)
    baseline_matrix = cast(Any, baseline_vectorizer.fit_transform([text for _, text in texts]))
    baseline_model, _ = _fit_nmf(baseline_matrix, cfg.k_range[0], cfg.seed, cfg.max_iter)
    baseline_terms = [
        set(terms)
        for terms in top_terms_for(
            baseline_model, np.array(baseline_vectorizer.get_feature_names_out())
        ).values()
    ]

    deals = sorted(set(passage_deals))[:max_deals]
    rows: list[dict[str, object]] = []
    for held_out in deals:
        keep = [i for i, deal_id in enumerate(passage_deals) if deal_id != held_out]
        sub_texts = [texts[i][1] for i in keep]
        vectorizer = _vectorizer(cfg)
        try:
            matrix = cast(Any, vectorizer.fit_transform(sub_texts))
        except ValueError:
            rows.append({"held_out_deal": held_out, "status": "insufficient_passages"})
            continue
        model, _ = _fit_nmf(matrix, cfg.k_range[0], cfg.seed, cfg.max_iter)
        refit_terms = [
            set(terms)
            for terms in top_terms_for(model, np.array(vectorizer.get_feature_names_out())).values()
        ]
        jaccards = []
        for a_terms in baseline_terms:
            best = 0.0
            for b_terms in refit_terms:
                union = a_terms | b_terms
                score = len(a_terms & b_terms) / len(union) if union else 0.0
                best = max(best, score)
            jaccards.append(best)
        rows.append(
            {
                "held_out_deal": held_out,
                "status": "ok",
                "mean_top_term_jaccard": round(float(np.mean(jaccards)), 4),
            }
        )
    return rows


__all__ = [
    "TopicSolution",
    "TopicsConfig",
    "agglomerative_sensitivity",
    "deal_topic_matrix",
    "fit_topics",
    "leave_one_deal_out_stability",
    "top_terms_for",
    "topic_label",
]
