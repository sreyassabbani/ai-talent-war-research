from __future__ import annotations

import csv
import hashlib
import heapq
import itertools
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

_REQUIRED_COLUMNS = frozenset(
    {
        "passage_id",
        "deal_id",
        "document_id",
        "document_family_id",
        "source_url",
        "raw_text",
        "model_text",
        "duplicate_group",
        "inclusion_status",
    }
)

_TOKEN = re.compile(r"[a-z][a-z0-9]*(?:[-'][a-z0-9]+)*")

# This deliberately excludes employee-domain words. Common legal terms can be substantive in this
# corpus, so boilerplate removal belongs upstream at the provision level rather than in this list.
_STOP_WORDS = frozenset(
    _TOKEN.findall(
        """
    a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not now of off on once only or other our ours ourselves out
    over own same she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when where which while
    who whom why will with would you your yours yourself yourselves
    """
    )
)

_GENERIC_TOPIC_TOKENS = frozenset(
    {
        "agreement",
        "applicable",
        "article",
        "business",
        "closing",
        "company",
        "date",
        "hereof",
        "merger",
        "parent",
        "parties",
        "party",
        "purchaser",
        "pursuant",
        "section",
        "seller",
        "shall",
        "thereof",
    }
)


@dataclass(frozen=True)
class PassageRow:
    passage_id: str
    deal_id: str
    document_id: str
    document_family_id: str
    source_url: str
    raw_text: str
    model_text: str
    duplicate_group: str
    inclusion_status: str


@dataclass(frozen=True)
class TopicModelConfig:
    seed: int = 1729
    min_passages: int = 75
    min_deals: int = 3
    k_min: int = 3
    k_max: int = 7
    min_topic_families: int = 5
    min_topic_deals: int = 2
    min_df: int = 2
    max_df_ratio: float = 0.90
    max_features: int = 750
    max_fit_passages: int = 240
    top_terms: int = 10
    nmf_iterations: int = 20
    projection_iterations: int = 6
    stability_iterations: int = 12
    reconstruction_tolerance: float = 0.25
    coherence_tolerance: float = 0.15
    min_topic_coherence: float = 0.0
    max_generic_top_term_ratio: float = 0.50
    min_agglomerative_ari: float = 0.20
    stability_threshold: float = 0.70
    min_topic_recovery_rate: float = 0.80


@dataclass(frozen=True)
class AssignmentRow:
    passage_id: str
    deal_id: str
    document_id: str
    document_family_id: str
    source_url: str
    topic_id: str
    topic_weight: float
    primary_topic: bool


@dataclass(frozen=True)
class TopicRow:
    topic_id: str
    top_terms: tuple[str, ...]
    primary_passage_count: int
    document_family_count: int
    deal_count: int
    coherence: float
    stability_median_cosine: float | None
    stability_recovery_rate: float | None


@dataclass(frozen=True)
class DealTopicRow:
    deal_id: str
    topic_id: str
    weight_sum: float
    normalized_weight: float
    primary_passage_count: int


@dataclass(frozen=True)
class DiagnosticRow:
    stage: str
    name: str
    value: float | int | str
    status: str
    detail: str


@dataclass(frozen=True)
class SensitivityAssignmentRow:
    passage_id: str
    deal_id: str
    cluster_id: str


@dataclass(frozen=True)
class StabilityRow:
    left_out_deal_id: str
    topic_id: str
    aligned_topic_id: str
    cosine_similarity: float
    recovered: bool


@dataclass(frozen=True)
class EmployeeTopicResult:
    status: str
    reason: str | None
    assignments: tuple[AssignmentRow, ...]
    topics: tuple[TopicRow, ...]
    deal_topics: tuple[DealTopicRow, ...]
    diagnostics: tuple[DiagnosticRow, ...]
    sensitivity_assignments: tuple[SensitivityAssignmentRow, ...]
    stability: tuple[StabilityRow, ...]


@dataclass(frozen=True)
class _VectorizedCorpus:
    rows: tuple[PassageRow, ...]
    matrix: tuple[dict[int, float], ...]
    vocabulary: tuple[str, ...]
    document_frequency: tuple[int, ...]


@dataclass(frozen=True)
class _NmfFit:
    k: int
    weights: tuple[tuple[float, ...], ...]
    components: tuple[tuple[float, ...], ...]
    reconstruction_error: float
    coherence: float
    min_family_support: int
    min_deal_support: int
    support_valid: bool


def load_passages_csv(path: Path) -> list[PassageRow]:
    """Load the passage contract and fail early when a required field is absent."""
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        columns = frozenset(reader.fieldnames or ())
        missing = sorted(_REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"Passage CSV is missing required columns: {', '.join(missing)}")
        return [_passage_from_mapping(row) for row in reader]


def analyze_employee_topics_csv(
    path: Path, config: TopicModelConfig = TopicModelConfig()
) -> EmployeeTopicResult:
    return analyze_employee_topics(load_passages_csv(path), config)


def propagate_duplicate_assignments(
    source_rows: Iterable[PassageRow | Mapping[str, str]],
    canonical_assignments: Iterable[AssignmentRow],
) -> tuple[AssignmentRow, ...]:
    """Copy canonical topic weights to every included source occurrence in its duplicate group.

    Model fitting still sees one row per global duplicate group. Propagation prevents an exact
    passage whose canonical row belongs to one deal from disappearing from another deal's
    source-linked output. Input passage IDs must be unique because they are report join keys.
    """
    rows = [row if isinstance(row, PassageRow) else _passage_from_mapping(row) for row in source_rows]
    eligible = [
        row
        for row in rows
        if row.inclusion_status.strip().lower() == "included" and row.model_text.strip()
    ]
    passage_ids = [row.passage_id for row in eligible]
    if len(passage_ids) != len(set(passage_ids)):
        raise ValueError("Included passage_id values must be unique for assignment propagation.")

    grouped: dict[str, list[PassageRow]] = defaultdict(list)
    for row in eligible:
        grouped[_duplicate_key(row)].append(row)
    assignments_by_passage: dict[str, list[AssignmentRow]] = defaultdict(list)
    for assignment in canonical_assignments:
        assignments_by_passage[assignment.passage_id].append(assignment)

    output: list[AssignmentRow] = []
    for group_key in sorted(grouped):
        canonical = min(grouped[group_key], key=_passage_order_key)
        source_assignments = assignments_by_passage.get(canonical.passage_id)
        if not source_assignments:
            raise ValueError(
                f"Canonical passage {canonical.passage_id!r} has no topic assignments to propagate."
            )
        for row in sorted(grouped[group_key], key=_passage_order_key):
            for assignment in sorted(source_assignments, key=lambda item: item.topic_id):
                output.append(
                    replace(
                        assignment,
                        passage_id=row.passage_id,
                        deal_id=row.deal_id,
                        document_id=row.document_id,
                        document_family_id=row.document_family_id,
                        source_url=row.source_url,
                    )
                )
    return tuple(
        sorted(output, key=lambda row: (row.deal_id, row.passage_id, row.topic_id))
    )


def analyze_employee_topics(
    source_rows: Iterable[PassageRow | Mapping[str, str]],
    config: TopicModelConfig = TopicModelConfig(),
) -> EmployeeTopicResult:
    """Fit the passage topic model and its deterministic sensitivity diagnostics.

    Passages are filtered to ``inclusion_status == "included"`` and reduced to the first
    deterministic row in each duplicate group before any statistics are computed.
    """
    _validate_config(config)
    materialized_rows = [
        row if isinstance(row, PassageRow) else _passage_from_mapping(row) for row in source_rows
    ]
    prepared, input_count, included_count, empty_count = _prepare_passages(materialized_rows)
    diagnostics: list[DiagnosticRow] = [
        DiagnosticRow("input", "input_rows", input_count, "pass", "Rows supplied."),
        DiagnosticRow(
            "input", "included_rows", included_count, "pass", "Rows marked included before dedupe."
        ),
        DiagnosticRow(
            "input",
            "canonical_passages",
            len(prepared),
            "pass",
            "One non-empty model passage per duplicate group.",
        ),
        DiagnosticRow(
            "input",
            "empty_model_text_rows",
            empty_count,
            "warning" if empty_count else "pass",
            "Included canonical rows omitted because model_text was empty.",
        ),
    ]
    deal_count = len({row.deal_id for row in prepared})
    duplicate_deals: dict[str, set[str]] = defaultdict(set)
    for row in materialized_rows:
        if row.inclusion_status.strip().lower() == "included" and row.model_text.strip():
            duplicate_deals[_duplicate_key(row)].add(row.deal_id)
    cross_deal_duplicates = sum(len(deals) > 1 for deals in duplicate_deals.values())
    diagnostics.append(
        DiagnosticRow("input", "deal_count", deal_count, "pass", "Deals represented in corpus.")
    )
    diagnostics.append(
        DiagnosticRow(
            "input",
            "cross_deal_duplicate_groups",
            cross_deal_duplicates,
            "warning" if cross_deal_duplicates else "pass",
            "Exact groups spanning deals are propagated, but make leave-one-deal-out stability less independent.",
        )
    )

    if len(prepared) < config.min_passages:
        return _qualitative_result(
            "too_few_unique_passages",
            diagnostics,
            f"Need at least {config.min_passages} canonical included passages; found {len(prepared)}.",
        )
    if deal_count < config.min_deals:
        return _qualitative_result(
            "too_few_deals",
            diagnostics,
            f"Need at least {config.min_deals} deals; found {deal_count}.",
        )

    fit_indices = _balanced_fit_indices(prepared, config.max_fit_passages, config.seed)
    fit_rows = tuple(prepared[index] for index in fit_indices)
    fit_deal_counts = Counter(row.deal_id for row in fit_rows)
    fit_family_count = len({(row.deal_id, _family_key(row)) for row in fit_rows})
    corpus = _vectorize(fit_rows, config)
    full_corpus = _transform(prepared, corpus)
    zero_vectors = sum(not row for row in full_corpus.matrix)
    diagnostics.extend(
        (
            DiagnosticRow(
                "sampling",
                "fit_passages",
                len(fit_rows),
                "pass",
                "Deterministic deal-balanced passage families used to fit candidate models.",
            ),
            DiagnosticRow(
                "sampling",
                "projected_passages",
                len(prepared) - len(fit_rows),
                "pass",
                "Remaining canonical passages assigned with fixed-component NMF projection.",
            ),
            DiagnosticRow(
                "sampling",
                "fit_family_count",
                fit_family_count,
                "pass",
                "Unique deal/provision families represented in model fitting.",
            ),
            DiagnosticRow(
                "sampling",
                "minimum_fit_passages_per_deal",
                min(fit_deal_counts.values()),
                "pass",
                "Smallest deal contribution to the balanced fit sample.",
            ),
            DiagnosticRow(
                "sampling",
                "maximum_fit_passages_per_deal",
                max(fit_deal_counts.values()),
                "pass",
                "Largest deal contribution to the balanced fit sample.",
            ),
            DiagnosticRow(
                "vectorize",
                "zero_vector_passages",
                zero_vectors,
                "warning" if zero_vectors else "pass",
                "Canonical passages with no terms in the fitted vocabulary.",
            ),
        )
    )
    diagnostics.append(
        DiagnosticRow(
            "vectorize",
            "vocabulary_size",
            len(corpus.vocabulary),
            "pass" if len(corpus.vocabulary) >= config.k_min else "fail",
            "Word and bigram TF-IDF vocabulary after document-frequency filters.",
        )
    )
    if len(corpus.vocabulary) < config.k_min:
        return _qualitative_result(
            "insufficient_vocabulary",
            diagnostics,
            "TF-IDF vocabulary is too small for the requested topic range.",
        )

    fits: list[_NmfFit] = []
    upper_k = min(config.k_max, len(fit_rows) - 1, len(corpus.vocabulary))
    for k in range(config.k_min, upper_k + 1):
        fit = _fit_and_describe(corpus, k, config.seed + (k * 10_007), config)
        fits.append(fit)
        diagnostics.extend(_candidate_diagnostics(fit, config))

    selected = _select_fit(fits, config)
    if selected is None:
        return _qualitative_result(
            "no_supported_topic_solution",
            diagnostics,
            "No candidate topic count met support plus reconstruction/coherence diagnostics.",
        )

    selected = _order_fit(selected, corpus)
    diagnostics.append(
        DiagnosticRow(
            "selection",
            "selected_k",
            selected.k,
            "pass",
            "Smallest supported k within reconstruction and coherence tolerances.",
        )
    )

    projected_weights = _project_weights(
        full_corpus.matrix,
        selected.components,
        config.projection_iterations,
    )
    full_fit = replace(selected, weights=projected_weights)
    canonical_assignments = _assignment_rows(full_corpus.rows, projected_weights)
    assignments = propagate_duplicate_assignments(materialized_rows, canonical_assignments)
    deal_rows, deal_weights = _deal_group_rows(materialized_rows, prepared, projected_weights)
    deal_topics = _deal_topic_rows(deal_rows, deal_weights)
    sensitivity = _agglomerative_fit_predict(corpus, full_corpus, selected.k)
    sensitivity_rows = tuple(
        SensitivityAssignmentRow(row.passage_id, row.deal_id, f"cluster_{cluster + 1}")
        for row, cluster in zip(full_corpus.rows, sensitivity, strict=True)
    )
    primary_topics = [_argmax(weight) if sum(weight) else -1 for weight in projected_weights]
    agglomerative_ari = _adjusted_rand_index(primary_topics, sensitivity)
    diagnostics.append(
        DiagnosticRow(
            "sensitivity",
            "agglomerative_adjusted_rand",
            agglomerative_ari,
            "pass" if agglomerative_ari >= config.min_agglomerative_ari else "warning",
            "Agreement between primary NMF topic and TF-IDF average-linkage clustering; "
            f"requires at least {config.min_agglomerative_ari:.2f}.",
        )
    )

    stability = _leave_one_deal_out(corpus, selected, config)
    topics = _topic_rows(full_corpus, full_fit, stability)
    diagnostics.extend(_topic_quality_diagnostics(topics, config))
    recovered = [row.recovered for row in stability]
    every_topic_stable = all(
        topic.stability_recovery_rate is not None
        and topic.stability_recovery_rate >= config.min_topic_recovery_rate
        for topic in topics
    )
    diagnostics.append(
        DiagnosticRow(
            "stability",
            "overall_recovery_rate",
            sum(recovered) / len(recovered) if recovered else 0.0,
            "pass" if every_topic_stable else "warning",
            f"Topic alignment at cosine >= {config.stability_threshold:.2f}; every topic must "
            f"recover in at least {config.min_topic_recovery_rate:.0%} of folds.",
        )
    )
    return EmployeeTopicResult(
        status="modeled",
        reason=None,
        assignments=assignments,
        topics=topics,
        deal_topics=deal_topics,
        diagnostics=tuple(diagnostics),
        sensitivity_assignments=sensitivity_rows,
        stability=stability,
    )


def _validate_config(config: TopicModelConfig) -> None:
    if config.k_min < 2 or config.k_max < config.k_min:
        raise ValueError("Topic range must satisfy 2 <= k_min <= k_max.")
    if config.min_passages < 1 or config.min_deals < 1:
        raise ValueError("Minimum passage and deal counts must be positive.")
    if not 0 < config.max_df_ratio <= 1:
        raise ValueError("max_df_ratio must be in (0, 1].")
    if not -1 <= config.min_topic_coherence <= 1:
        raise ValueError("min_topic_coherence must be between -1 and 1.")
    if not 0 <= config.max_generic_top_term_ratio <= 1:
        raise ValueError("max_generic_top_term_ratio must be between 0 and 1.")
    if not -1 <= config.min_agglomerative_ari <= 1:
        raise ValueError("min_agglomerative_ari must be between -1 and 1.")
    if not 0 <= config.stability_threshold <= 1:
        raise ValueError("stability_threshold must be between 0 and 1.")
    if not 0 <= config.min_topic_recovery_rate <= 1:
        raise ValueError("min_topic_recovery_rate must be between 0 and 1.")
    if min(
        config.nmf_iterations,
        config.projection_iterations,
        config.stability_iterations,
        config.max_fit_passages,
    ) < 1:
        raise ValueError("Iteration and fit-sample limits must be positive.")


def _passage_from_mapping(row: Mapping[str, str]) -> PassageRow:
    missing = sorted(_REQUIRED_COLUMNS - row.keys())
    if missing:
        raise ValueError(f"Passage row is missing required fields: {', '.join(missing)}")
    return PassageRow(**{field: str(row[field]) for field in _REQUIRED_COLUMNS})


def _prepare_passages(
    source_rows: Iterable[PassageRow | Mapping[str, str]],
) -> tuple[tuple[PassageRow, ...], int, int, int]:
    rows = [row if isinstance(row, PassageRow) else _passage_from_mapping(row) for row in source_rows]
    included = [row for row in rows if row.inclusion_status.strip().lower() == "included"]
    by_duplicate: dict[str, list[PassageRow]] = defaultdict(list)
    empty_count = 0
    for row in included:
        if not row.model_text.strip():
            empty_count += 1
            continue
        by_duplicate[_duplicate_key(row)].append(row)

    canonical: list[PassageRow] = []
    for group in sorted(by_duplicate):
        row = min(
            by_duplicate[group],
            key=_passage_order_key,
        )
        canonical.append(row)
    canonical.sort(key=lambda row: (row.deal_id, row.passage_id, row.document_id))
    return tuple(canonical), len(rows), len(included), empty_count


def _duplicate_key(row: PassageRow) -> str:
    return row.duplicate_group.strip() or f"passage:{row.passage_id}"


def _passage_order_key(row: PassageRow) -> tuple[str, str, str]:
    return row.passage_id, row.document_id, row.source_url


def _family_key(row: PassageRow) -> str:
    return row.document_family_id.strip() or f"passage:{row.passage_id}"


def _balanced_fit_indices(
    rows: Sequence[PassageRow], limit: int, seed: int
) -> tuple[int, ...]:
    by_deal_family: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_deal_family[(row.deal_id, _family_key(row))].append(index)
    representatives = [
        min(
            indices,
            key=lambda index: (
                _stable_rank(seed, deal_id, rows[index].passage_id),
                rows[index].passage_id,
            ),
        )
        for (deal_id, _), indices in sorted(by_deal_family.items())
    ]
    if len(representatives) <= limit:
        return tuple(sorted(representatives))
    by_deal: dict[str, list[int]] = defaultdict(list)
    for index in representatives:
        row = rows[index]
        by_deal[row.deal_id].append(index)
    for deal_id, indices in by_deal.items():
        indices.sort(
            key=lambda index: (
                _stable_rank(seed, deal_id, rows[index].passage_id),
                rows[index].passage_id,
            )
        )
    offsets = {deal_id: 0 for deal_id in by_deal}
    selected: list[int] = []
    while len(selected) < limit:
        advanced = False
        for deal_id in sorted(by_deal):
            offset = offsets[deal_id]
            if offset >= len(by_deal[deal_id]):
                continue
            selected.append(by_deal[deal_id][offset])
            offsets[deal_id] += 1
            advanced = True
            if len(selected) == limit:
                break
        if not advanced:
            break
    return tuple(sorted(selected))


def _stable_rank(seed: int, deal_id: str, passage_id: str) -> str:
    return hashlib.sha256(f"{seed}:{deal_id}:{passage_id}".encode()).hexdigest()


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(text.lower()) if token not in _STOP_WORDS]


def _terms(text: str) -> Counter[str]:
    tokens = _tokens(text)
    terms = Counter(tokens)
    terms.update(f"{left} {right}" for left, right in itertools.pairwise(tokens))
    return terms


def _vectorize(rows: Sequence[PassageRow], config: TopicModelConfig) -> _VectorizedCorpus:
    counts = [_terms(row.model_text) for row in rows]
    document_frequency: Counter[str] = Counter()
    corpus_frequency: Counter[str] = Counter()
    for row_counts in counts:
        document_frequency.update(row_counts.keys())
        corpus_frequency.update(row_counts)

    n_rows = len(rows)
    candidates = [
        term
        for term, frequency in document_frequency.items()
        if frequency >= config.min_df and frequency / n_rows <= config.max_df_ratio
    ]
    candidates.sort(
        key=lambda term: (
            -(corpus_frequency[term] * (math.log((1 + n_rows) / (1 + document_frequency[term])) + 1)),
            term,
        )
    )
    vocabulary = tuple(sorted(candidates[: config.max_features]))
    term_index = {term: index for index, term in enumerate(vocabulary)}
    matrix: list[dict[int, float]] = []
    for row_counts in counts:
        vector: dict[int, float] = {}
        for term, count in row_counts.items():
            index = term_index.get(term)
            if index is None:
                continue
            inverse_document_frequency = math.log(
                (1 + n_rows) / (1 + document_frequency[term])
            ) + 1
            vector[index] = (1 + math.log(count)) * inverse_document_frequency
        norm = math.sqrt(sum(value * value for value in vector.values()))
        if norm:
            vector = {index: value / norm for index, value in vector.items()}
        matrix.append(vector)
    return _VectorizedCorpus(
        rows=tuple(rows),
        matrix=tuple(matrix),
        vocabulary=vocabulary,
        document_frequency=tuple(document_frequency[term] for term in vocabulary),
    )


def _transform(
    rows: Sequence[PassageRow], fitted: _VectorizedCorpus
) -> _VectorizedCorpus:
    term_index = {term: index for index, term in enumerate(fitted.vocabulary)}
    training_count = len(fitted.rows)
    inverse_document_frequency = tuple(
        math.log((1 + training_count) / (1 + frequency)) + 1
        for frequency in fitted.document_frequency
    )
    matrix: list[dict[int, float]] = []
    for row in rows:
        vector: dict[int, float] = {}
        for term, count in _terms(row.model_text).items():
            index = term_index.get(term)
            if index is not None:
                vector[index] = (1 + math.log(count)) * inverse_document_frequency[index]
        norm = math.sqrt(sum(value * value for value in vector.values()))
        matrix.append(
            {index: value / norm for index, value in vector.items()} if norm else {}
        )
    return _VectorizedCorpus(
        rows=tuple(rows),
        matrix=tuple(matrix),
        vocabulary=fitted.vocabulary,
        document_frequency=fitted.document_frequency,
    )


def _fit_and_describe(
    corpus: _VectorizedCorpus, k: int, seed: int, config: TopicModelConfig
) -> _NmfFit:
    weights, components, error = _nmf(corpus.matrix, len(corpus.vocabulary), k, seed, config)
    normalized_weights = tuple(_normalize(row) for row in weights)
    primary = [_argmax(row) for row in normalized_weights]
    family_support = [set() for _ in range(k)]
    deal_support = [set() for _ in range(k)]
    for passage, topic in zip(corpus.rows, primary, strict=True):
        family_support[topic].add(passage.document_family_id)
        deal_support[topic].add(passage.deal_id)
    min_family_support = min(map(len, family_support))
    min_deal_support = min(map(len, deal_support))
    coherence = _model_coherence(components, corpus)
    return _NmfFit(
        k=k,
        weights=normalized_weights,
        components=components,
        reconstruction_error=error,
        coherence=coherence,
        min_family_support=min_family_support,
        min_deal_support=min_deal_support,
        support_valid=(
            min_family_support >= config.min_topic_families
            and min_deal_support >= config.min_topic_deals
        ),
    )


def _nmf(
    matrix: Sequence[Mapping[int, float]],
    feature_count: int,
    k: int,
    seed: int,
    config: TopicModelConfig,
) -> tuple[tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...], float]:
    rng = random.Random(seed)
    row_count = len(matrix)
    epsilon = 1e-12
    weights = [[0.1 + rng.random() for _ in range(k)] for _ in range(row_count)]
    components = [[0.1 + rng.random() for _ in range(feature_count)] for _ in range(k)]

    for _ in range(config.nmf_iterations):
        weight_cross = [[0.0] * feature_count for _ in range(k)]
        for row_index, sparse_row in enumerate(matrix):
            for feature, value in sparse_row.items():
                for topic in range(k):
                    weight_cross[topic][feature] += weights[row_index][topic] * value
        weight_gram = _gram(weights, k)
        for topic in range(k):
            for feature in range(feature_count):
                denominator = sum(
                    weight_gram[topic][other] * components[other][feature]
                    for other in range(k)
                )
                components[topic][feature] *= weight_cross[topic][feature] / (
                    denominator + epsilon
                )
                components[topic][feature] = max(components[topic][feature], epsilon)

        component_gram = _gram(components, k, rows_are_topics=True)
        for row_index, sparse_row in enumerate(matrix):
            numerator = [0.0] * k
            for feature, value in sparse_row.items():
                for topic in range(k):
                    numerator[topic] += value * components[topic][feature]
            for topic in range(k):
                denominator = sum(
                    weights[row_index][other] * component_gram[other][topic]
                    for other in range(k)
                )
                weights[row_index][topic] *= numerator[topic] / (denominator + epsilon)
                weights[row_index][topic] = max(weights[row_index][topic], epsilon)

    error = _reconstruction_error(matrix, weights, components)
    return (
        tuple(tuple(value for value in row) for row in weights),
        tuple(tuple(value for value in row) for row in components),
        error,
    )


def _project_weights(
    matrix: Sequence[Mapping[int, float]],
    components: Sequence[Sequence[float]],
    iterations: int,
) -> tuple[tuple[float, ...], ...]:
    """Infer nonnegative passage weights while keeping fitted topic components fixed."""
    k = len(components)
    epsilon = 1e-12
    component_gram = _gram(components, k, rows_are_topics=True)
    numerators: list[list[float]] = []
    for sparse_row in matrix:
        numerator = [0.0] * k
        for feature, value in sparse_row.items():
            for topic in range(k):
                numerator[topic] += value * components[topic][feature]
        numerators.append(numerator)
    weights = [
        [max(value, epsilon) for value in numerator] for numerator in numerators
    ]
    for _ in range(iterations):
        for row_index, numerator in enumerate(numerators):
            for topic in range(k):
                denominator = sum(
                    weights[row_index][other] * component_gram[other][topic]
                    for other in range(k)
                )
                weights[row_index][topic] *= numerator[topic] / (denominator + epsilon)
                weights[row_index][topic] = max(weights[row_index][topic], epsilon)
    return tuple(
        _normalize(row) if any(numerator) else tuple(0.0 for _ in range(k))
        for row, numerator in zip(weights, numerators, strict=True)
    )


def _gram(
    values: Sequence[Sequence[float]], k: int, *, rows_are_topics: bool = False
) -> list[list[float]]:
    gram = [[0.0] * k for _ in range(k)]
    if rows_are_topics:
        for left in range(k):
            for right in range(left, k):
                value = sum(
                    values[left][column] * values[right][column]
                    for column in range(len(values[left]))
                )
                gram[left][right] = value
                gram[right][left] = value
        return gram
    for row in values:
        for left in range(k):
            for right in range(left, k):
                gram[left][right] += row[left] * row[right]
                if left != right:
                    gram[right][left] = gram[left][right]
    return gram


def _reconstruction_error(
    matrix: Sequence[Mapping[int, float]],
    weights: Sequence[Sequence[float]],
    components: Sequence[Sequence[float]],
) -> float:
    squared_error = 0.0
    squared_input = 0.0
    for row_index, sparse_row in enumerate(matrix):
        for value in sparse_row.values():
            squared_input += value * value
        for feature in range(len(components[0])):
            prediction = sum(
                weights[row_index][topic] * components[topic][feature]
                for topic in range(len(components))
            )
            difference = sparse_row.get(feature, 0.0) - prediction
            squared_error += difference * difference
    return math.sqrt(squared_error / squared_input) if squared_input else math.inf


def _model_coherence(
    components: Sequence[Sequence[float]], corpus: _VectorizedCorpus
) -> float:
    topic_scores: list[float] = []
    n_rows = len(corpus.matrix)
    incidence = [
        {row_index for row_index, row in enumerate(corpus.matrix) if feature in row}
        for feature in range(len(corpus.vocabulary))
    ]
    for component in components:
        top = sorted(range(len(component)), key=lambda index: (-component[index], index))[:10]
        pair_scores: list[float] = []
        for left, right in itertools.combinations(top, 2):
            shared = len(incidence[left] & incidence[right])
            if shared == 0:
                pair_scores.append(-1.0)
                continue
            left_frequency = len(incidence[left])
            right_frequency = len(incidence[right])
            pointwise = math.log((shared * n_rows) / (left_frequency * right_frequency))
            denominator = -math.log(shared / n_rows)
            pair_scores.append(pointwise / denominator if denominator else 0.0)
        topic_scores.append(sum(pair_scores) / len(pair_scores) if pair_scores else -1.0)
    return sum(topic_scores) / len(topic_scores)


def _candidate_diagnostics(
    fit: _NmfFit, config: TopicModelConfig
) -> list[DiagnosticRow]:
    prefix = f"k_{fit.k}"
    return [
        DiagnosticRow(
            "candidate",
            f"{prefix}_reconstruction_error",
            fit.reconstruction_error,
            "pass",
            "Relative Frobenius reconstruction error; lower is better.",
        ),
        DiagnosticRow(
            "candidate",
            f"{prefix}_npmi_coherence",
            fit.coherence,
            "pass",
            "Mean top-term normalized pointwise mutual information; higher is better.",
        ),
        DiagnosticRow(
            "candidate",
            f"{prefix}_absolute_coherence_valid",
            int(fit.coherence >= config.min_topic_coherence),
            "pass",
            f"One when mean NPMI meets the absolute {config.min_topic_coherence:.2f} floor.",
        ),
        DiagnosticRow(
            "candidate",
            f"{prefix}_minimum_family_support",
            fit.min_family_support,
            "pass",
            "Smallest primary-topic document-family support.",
        ),
        DiagnosticRow(
            "candidate",
            f"{prefix}_minimum_deal_support",
            fit.min_deal_support,
            "pass",
            "Smallest primary-topic deal support.",
        ),
        DiagnosticRow(
            "candidate",
            f"{prefix}_support_valid",
            int(fit.support_valid),
            "pass",
            "One when both configured minimum-support constraints are satisfied.",
        ),
    ]


def _select_fit(fits: Sequence[_NmfFit], config: TopicModelConfig) -> _NmfFit | None:
    supported = [
        fit
        for fit in fits
        if fit.support_valid
        and fit.coherence >= config.min_topic_coherence
        and math.isfinite(fit.reconstruction_error)
    ]
    if not supported:
        return None
    best_error = min(fit.reconstruction_error for fit in supported)
    best_coherence = max(fit.coherence for fit in supported)
    diagnostically_valid = [
        fit
        for fit in supported
        if fit.reconstruction_error <= best_error * (1 + config.reconstruction_tolerance)
        and fit.coherence >= best_coherence - config.coherence_tolerance
    ]
    return min(diagnostically_valid, key=lambda fit: fit.k) if diagnostically_valid else None


def _order_fit(fit: _NmfFit, corpus: _VectorizedCorpus) -> _NmfFit:
    primary = [_argmax(row) for row in fit.weights]
    support = Counter(primary)
    topic_order = sorted(
        range(fit.k),
        key=lambda topic: (
            -support[topic],
            tuple(
                corpus.vocabulary[index]
                for index in sorted(
                    range(len(fit.components[topic])),
                    key=lambda index: (-fit.components[topic][index], index),
                )[:5]
            ),
        ),
    )
    return replace(
        fit,
        weights=tuple(tuple(row[topic] for topic in topic_order) for row in fit.weights),
        components=tuple(fit.components[topic] for topic in topic_order),
    )


def _assignment_rows(
    passages: Sequence[PassageRow], weights: Sequence[Sequence[float]]
) -> tuple[AssignmentRow, ...]:
    output: list[AssignmentRow] = []
    for passage, row_weights in zip(passages, weights, strict=True):
        primary = _argmax(row_weights) if sum(row_weights) else None
        for topic, weight in enumerate(row_weights):
            output.append(
                AssignmentRow(
                    passage_id=passage.passage_id,
                    deal_id=passage.deal_id,
                    document_id=passage.document_id,
                    document_family_id=passage.document_family_id,
                    source_url=passage.source_url,
                    topic_id=f"topic_{topic + 1}",
                    topic_weight=weight,
                    primary_topic=primary is not None and topic == primary,
                )
            )
    return tuple(output)


def _deal_topic_rows(
    passages: Sequence[PassageRow], weights: Sequence[Sequence[float]]
) -> tuple[DealTopicRow, ...]:
    sums: dict[str, list[float]] = {}
    primary_counts: dict[str, Counter[int]] = defaultdict(Counter)
    for passage, row_weights in zip(passages, weights, strict=True):
        sums.setdefault(passage.deal_id, [0.0] * len(row_weights))
        for topic, weight in enumerate(row_weights):
            sums[passage.deal_id][topic] += weight
        if sum(row_weights):
            primary_counts[passage.deal_id][_argmax(row_weights)] += 1

    output: list[DealTopicRow] = []
    for deal_id in sorted(sums):
        denominator = sum(sums[deal_id])
        for topic, weight_sum in enumerate(sums[deal_id]):
            output.append(
                DealTopicRow(
                    deal_id=deal_id,
                    topic_id=f"topic_{topic + 1}",
                    weight_sum=weight_sum,
                    normalized_weight=weight_sum / denominator if denominator else 0.0,
                    primary_passage_count=primary_counts[deal_id][topic],
                )
            )
    return tuple(output)


def _deal_group_rows(
    source_rows: Sequence[PassageRow],
    canonical_rows: Sequence[PassageRow],
    canonical_weights: Sequence[Sequence[float]],
) -> tuple[tuple[PassageRow, ...], tuple[tuple[float, ...], ...]]:
    weights_by_group = {
        _duplicate_key(row): tuple(weights)
        for row, weights in zip(canonical_rows, canonical_weights, strict=True)
    }
    by_deal_group: dict[tuple[str, str], list[PassageRow]] = defaultdict(list)
    for row in source_rows:
        if row.inclusion_status.strip().lower() != "included" or not row.model_text.strip():
            continue
        group = _duplicate_key(row)
        if group in weights_by_group:
            by_deal_group[(row.deal_id, group)].append(row)
    selected: list[tuple[PassageRow, tuple[float, ...]]] = []
    for deal_group in sorted(by_deal_group):
        row = min(by_deal_group[deal_group], key=_passage_order_key)
        selected.append((row, weights_by_group[deal_group[1]]))
    return (
        tuple(row for row, _ in selected),
        tuple(weights for _, weights in selected),
    )


def _topic_rows(
    corpus: _VectorizedCorpus, fit: _NmfFit, stability: Sequence[StabilityRow]
) -> tuple[TopicRow, ...]:
    primary = [_argmax(row) if sum(row) else None for row in fit.weights]
    output: list[TopicRow] = []
    for topic in range(fit.k):
        selected = [index for index, value in enumerate(primary) if value == topic]
        topic_stability = [row for row in stability if row.topic_id == f"topic_{topic + 1}"]
        similarities = sorted(row.cosine_similarity for row in topic_stability)
        recovery_rate = (
            sum(row.recovered for row in topic_stability) / len(topic_stability)
            if topic_stability
            else None
        )
        output.append(
            TopicRow(
                topic_id=f"topic_{topic + 1}",
                top_terms=tuple(
                    corpus.vocabulary[index]
                    for index in sorted(
                        range(len(fit.components[topic])),
                        key=lambda index: (-fit.components[topic][index], index),
                    )[:10]
                ),
                primary_passage_count=len(selected),
                document_family_count=len(
                    {corpus.rows[index].document_family_id for index in selected}
                ),
                deal_count=len({corpus.rows[index].deal_id for index in selected}),
                coherence=_topic_coherence(fit.components[topic], corpus),
                stability_median_cosine=_median(similarities) if similarities else None,
                stability_recovery_rate=recovery_rate,
            )
        )
    return tuple(output)


def _topic_quality_diagnostics(
    topics: Sequence[TopicRow], config: TopicModelConfig
) -> tuple[DiagnosticRow, ...]:
    diagnostics: list[DiagnosticRow] = []
    for topic in topics:
        recovery = topic.stability_recovery_rate
        diagnostics.append(
            DiagnosticRow(
                "stability",
                f"{topic.topic_id}_recovery_rate",
                recovery if recovery is not None else 0.0,
                "pass"
                if recovery is not None and recovery >= config.min_topic_recovery_rate
                else "warning",
                f"Requires recovery in at least {config.min_topic_recovery_rate:.0%} of "
                "leave-one-deal-out folds.",
            )
        )
        diagnostics.append(
            DiagnosticRow(
                "topic_quality",
                f"{topic.topic_id}_npmi_coherence",
                topic.coherence,
                "pass" if topic.coherence >= config.min_topic_coherence else "warning",
                f"Requires NPMI coherence of at least {config.min_topic_coherence:.2f}.",
            )
        )
        generic_ratio = _generic_top_term_ratio(topic.top_terms)
        diagnostics.append(
            DiagnosticRow(
                "topic_quality",
                f"{topic.topic_id}_generic_top_term_ratio",
                generic_ratio,
                "pass"
                if generic_ratio <= config.max_generic_top_term_ratio
                else "warning",
                "Share of top terms composed only of generic legal tokens; requires at most "
                f"{config.max_generic_top_term_ratio:.0%}.",
            )
        )
    return tuple(diagnostics)


def _generic_top_term_ratio(terms: Sequence[str]) -> float:
    if not terms:
        return 1.0
    generic = sum(
        bool(tokens) and all(token in _GENERIC_TOPIC_TOKENS for token in tokens)
        for term in terms
        if (tokens := _TOKEN.findall(term.lower()))
    )
    return generic / len(terms)


def _topic_coherence(component: Sequence[float], corpus: _VectorizedCorpus) -> float:
    top = sorted(range(len(component)), key=lambda index: (-component[index], index))[:10]
    n_rows = len(corpus.matrix)
    pair_scores: list[float] = []
    for left, right in itertools.combinations(top, 2):
        left_rows = {index for index, row in enumerate(corpus.matrix) if left in row}
        right_rows = {index for index, row in enumerate(corpus.matrix) if right in row}
        shared = len(left_rows & right_rows)
        if shared == 0:
            pair_scores.append(-1.0)
            continue
        pointwise = math.log((shared * n_rows) / (len(left_rows) * len(right_rows)))
        denominator = -math.log(shared / n_rows)
        pair_scores.append(pointwise / denominator if denominator else 0.0)
    return sum(pair_scores) / len(pair_scores) if pair_scores else -1.0


def _agglomerative_assignments(corpus: _VectorizedCorpus, k: int) -> list[int]:
    target = min(k, len(corpus.rows))
    count = len(corpus.matrix)
    active = set(range(count))
    sizes = {index: 1 for index in range(count)}
    members = {index: [index] for index in range(count)}
    distances: dict[tuple[int, int], float] = {}
    heap: list[tuple[float, int, int]] = []
    for left in range(count):
        for right in range(left + 1, count):
            distance = 1.0 - _sparse_dot(corpus.matrix[left], corpus.matrix[right])
            distances[(left, right)] = distance
            heapq.heappush(heap, (distance, left, right))

    next_cluster = count
    while len(active) > target:
        while True:
            _, left, right = heapq.heappop(heap)
            if left in active and right in active:
                break
        active.remove(left)
        active.remove(right)
        others = sorted(active)
        active.add(next_cluster)
        sizes[next_cluster] = sizes[left] + sizes[right]
        members[next_cluster] = members[left] + members[right]
        for other in others:
            left_key = _pair(left, other)
            right_key = _pair(right, other)
            distance = (
                sizes[left] * distances[left_key] + sizes[right] * distances[right_key]
            ) / sizes[next_cluster]
            key = _pair(next_cluster, other)
            distances[key] = distance
            heapq.heappush(heap, (distance, key[0], key[1]))
        next_cluster += 1

    ordered = sorted(active, key=lambda cluster: min(members[cluster]))
    labels = [0] * count
    for label, cluster in enumerate(ordered):
        for member in members[cluster]:
            labels[member] = label
    return labels


def _agglomerative_fit_predict(
    fitted: _VectorizedCorpus, full: _VectorizedCorpus, k: int
) -> list[int]:
    fitted_labels = _agglomerative_assignments(fitted, k)
    centroid_sums: list[defaultdict[int, float]] = [defaultdict(float) for _ in range(k)]
    cluster_sizes = Counter(fitted_labels)
    for sparse_row, label in zip(fitted.matrix, fitted_labels, strict=True):
        for feature, value in sparse_row.items():
            centroid_sums[label][feature] += value
    centroids: list[dict[int, float]] = []
    for label, values in enumerate(centroid_sums):
        centroid = {
            feature: value / cluster_sizes[label] for feature, value in values.items()
        }
        norm = math.sqrt(sum(value * value for value in centroid.values()))
        centroids.append(
            {feature: value / norm for feature, value in centroid.items()} if norm else {}
        )
    fitted_by_passage = {
        row.passage_id: label
        for row, label in zip(fitted.rows, fitted_labels, strict=True)
    }
    output: list[int] = []
    for row, sparse_row in zip(full.rows, full.matrix, strict=True):
        if row.passage_id in fitted_by_passage:
            output.append(fitted_by_passage[row.passage_id])
            continue
        output.append(
            max(
                range(k),
                key=lambda label: (_sparse_dot(sparse_row, centroids[label]), -label),
            )
        )
    return output


def _leave_one_deal_out(
    corpus: _VectorizedCorpus, full_fit: _NmfFit, config: TopicModelConfig
) -> tuple[StabilityRow, ...]:
    output: list[StabilityRow] = []
    deals = sorted({row.deal_id for row in corpus.rows})
    for deal_index, deal_id in enumerate(deals):
        kept = [index for index, row in enumerate(corpus.rows) if row.deal_id != deal_id]
        if len(kept) < full_fit.k:
            continue
        held_matrix = tuple(corpus.matrix[index] for index in kept)
        stability_config = replace(config, nmf_iterations=config.stability_iterations)
        _, held_components, _ = _nmf(
            held_matrix,
            len(corpus.vocabulary),
            full_fit.k,
            config.seed + 900_001 + deal_index,
            stability_config,
        )
        similarities = [
            [_cosine(full, held) for held in held_components] for full in full_fit.components
        ]
        alignment = _best_topic_alignment(similarities)
        for topic, aligned in enumerate(alignment):
            similarity = similarities[topic][aligned]
            output.append(
                StabilityRow(
                    left_out_deal_id=deal_id,
                    topic_id=f"topic_{topic + 1}",
                    aligned_topic_id=f"held_topic_{aligned + 1}",
                    cosine_similarity=similarity,
                    recovered=similarity >= config.stability_threshold,
                )
            )
    return tuple(output)


def _best_topic_alignment(similarities: Sequence[Sequence[float]]) -> tuple[int, ...]:
    k = len(similarities)
    return max(
        itertools.permutations(range(k)),
        key=lambda permutation: (
            sum(similarities[topic][permutation[topic]] for topic in range(k)),
            tuple(-value for value in permutation),
        ),
    )


def _adjusted_rand_index(left: Sequence[int], right: Sequence[int]) -> float:
    if len(left) != len(right):
        raise ValueError("Cluster label arrays must have equal length.")
    if len(left) < 2:
        return 1.0
    contingency: Counter[tuple[int, int]] = Counter(zip(left, right, strict=True))
    left_counts = Counter(left)
    right_counts = Counter(right)
    combinations = lambda value: value * (value - 1) / 2
    observed = sum(combinations(value) for value in contingency.values())
    left_sum = sum(combinations(value) for value in left_counts.values())
    right_sum = sum(combinations(value) for value in right_counts.values())
    total = combinations(len(left))
    expected = (left_sum * right_sum / total) if total else 0.0
    maximum = (left_sum + right_sum) / 2
    denominator = maximum - expected
    return (observed - expected) / denominator if denominator else 1.0


def _sparse_dot(left: Mapping[int, float], right: Mapping[int, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(index, 0.0) for index, value in left.items())


def _pair(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left < right else (right, left)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _normalize(values: Sequence[float]) -> tuple[float, ...]:
    total = sum(values)
    if not total:
        return tuple(1 / len(values) for _ in values)
    return tuple(value / total for value in values)


def _argmax(values: Sequence[float]) -> int:
    return max(range(len(values)), key=lambda index: (values[index], -index))


def _median(values: Sequence[float]) -> float:
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def _qualitative_result(
    reason: str, diagnostics: Sequence[DiagnosticRow], detail: str
) -> EmployeeTopicResult:
    return EmployeeTopicResult(
        status="qualitative_only",
        reason=reason,
        assignments=(),
        topics=(),
        deal_topics=(),
        diagnostics=tuple(diagnostics)
        + (DiagnosticRow("fallback", reason, 1, "fail", detail),),
        sensitivity_assignments=(),
        stability=(),
    )
