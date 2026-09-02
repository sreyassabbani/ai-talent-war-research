from __future__ import annotations

import csv
import hashlib
import itertools
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from sklearn.cluster import HDBSCAN, AgglomerativeClustering
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import normalize

FIT_BALANCE_MODES = ("deal", "source_family", "none")

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

# Fixed before inspecting model output. These terms describe contract structure or transaction
# parties rather than employee substance. Employee-domain terms intentionally do not appear here.
_LEGAL_BOILERPLATE_STOP_WORDS = frozenset(
    {
        "agreement",
        "agreements",
        "applicable",
        "article",
        "articles",
        "business",
        "businesses",
        "buyer",
        "buyers",
        "closing",
        "closings",
        "companies",
        "company",
        "course",
        "date",
        "dates",
        "entities",
        "entity",
        "herein",
        "hereof",
        "hereunder",
        "including",
        "law",
        "laws",
        "material",
        "materially",
        "ordinary",
        "parent",
        "parties",
        "party",
        "person",
        "persons",
        "provided",
        "provision",
        "provisions",
        "purchaser",
        "purchasers",
        "pursuant",
        "representations",
        "respect",
        "section",
        "sections",
        "seller",
        "sellers",
        "shall",
        "subsidiaries",
        "subsidiary",
        "target",
        "thereof",
        "thereto",
        "thereunder",
        "warranties",
    }
)

_MODEL_MARKER_TOKEN = re.compile(
    r"(?:date|entity|money|number|percent|person|url)tokens?\Z",
    re.IGNORECASE,
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
    source_document_family_id: str = ""


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
    bootstrap_replicates: int = 100
    bootstrap_iterations: int = 12
    embedding_svd_components: int = 50
    embedding_hdbscan_min_cluster_size: int = 5
    embedding_min_fit_rows: int = 100
    reconstruction_tolerance: float = 0.25
    coherence_tolerance: float = 0.15
    min_topic_coherence: float = 0.0
    max_generic_top_term_ratio: float = 0.50
    min_agglomerative_ari: float = 0.20
    stability_threshold: float = 0.70
    min_topic_recovery_rate: float = 0.80
    # How the bounded fit universe is spread: round-robin across deals (default), across
    # source-document families, or plain stable-rank truncation with no balancing.
    fit_balance: str = "deal"


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
    assignment_specificity: float = 0.0
    top_positive_residual_terms: tuple[str, ...] = ()
    top_positive_residual_scores: tuple[float, ...] = ()


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
class BootstrapStabilityRow:
    replicate_id: int
    topic_id: str
    aligned_topic_id: str
    cosine_similarity: float
    recovered: bool


@dataclass(frozen=True)
class BootstrapSummaryRow:
    topic_id: str
    replicate_count: int
    recurrence_count: int
    recovery_rate: float
    median_cosine_similarity: float


@dataclass(frozen=True)
class EmbeddingRobustnessAssignmentRow:
    passage_id: str
    deal_id: str
    method: str
    cluster_id: str
    noise: bool


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
    bootstrap_stability: tuple[BootstrapStabilityRow, ...] = ()
    bootstrap_summary: tuple[BootstrapSummaryRow, ...] = ()
    embedding_robustness_assignments: tuple[EmbeddingRobustnessAssignmentRow, ...] = ()


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
    rows = [
        row if isinstance(row, PassageRow) else _passage_from_mapping(row) for row in source_rows
    ]
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
    return tuple(sorted(output, key=lambda row: (row.deal_id, row.passage_id, row.topic_id)))


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

    fit_indices = _balanced_fit_indices(
        prepared, config.max_fit_passages, config.seed, config.fit_balance
    )
    fit_rows = tuple(prepared[index] for index in fit_indices)
    fit_deal_counts = Counter(row.deal_id for row in fit_rows)
    fit_family_count = len({(row.deal_id, _family_key(row)) for row in fit_rows})
    fit_source_family_counts = Counter(_source_family_key(row) for row in fit_rows)
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
                f"Deterministic passage families used to fit candidate models "
                f"(fit_balance={config.fit_balance}).",
            ),
            DiagnosticRow(
                "sampling",
                "fit_balance_mode",
                config.fit_balance,
                "pass",
                "deal: round-robin across deals; source_family: round-robin across "
                "source-document families; none: stable-rank truncation only.",
            ),
            DiagnosticRow(
                "sampling",
                "fit_source_family_count",
                len(fit_source_family_counts),
                "pass",
                "Distinct source-document families represented in model fitting.",
            ),
            DiagnosticRow(
                "sampling",
                "maximum_fit_source_family_share",
                round(max(fit_source_family_counts.values()) / len(fit_rows), 4),
                "pass",
                "Largest single source-document family share of the fit sample.",
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

    projected_weights, reconstruction_weights = _project_weights_with_raw(
        full_corpus.matrix,
        selected.components,
        config.projection_iterations,
    )
    full_fit = replace(selected, weights=projected_weights)
    canonical_assignments = _assignment_rows(full_corpus.rows, projected_weights)
    assignments = propagate_duplicate_assignments(materialized_rows, canonical_assignments)
    deal_rows, deal_weights = _deal_group_rows(materialized_rows, prepared, projected_weights)
    deal_topics = _deal_topic_rows(deal_rows, deal_weights)
    fitted_sensitivity = _agglomerative_assignments(corpus, selected.k)
    sensitivity = _agglomerative_fit_predict(
        corpus,
        full_corpus,
        selected.k,
        fitted_labels=fitted_sensitivity,
    )
    sensitivity_rows = tuple(
        SensitivityAssignmentRow(
            row.passage_id,
            row.deal_id,
            f"cluster_{cluster + 1}" if cluster >= 0 else "cluster_unassigned",
        )
        for row, cluster in zip(full_corpus.rows, sensitivity, strict=True)
    )
    sensitivity_indices = [
        index
        for index, (weights, label) in enumerate(
            zip(selected.weights, fitted_sensitivity, strict=True)
        )
        if sum(weights) and label >= 0
    ]
    fitted_primary_topics = [_argmax(selected.weights[index]) for index in sensitivity_indices]
    fitted_cluster_labels = [fitted_sensitivity[index] for index in sensitivity_indices]
    nmf_sizes = Counter(fitted_primary_topics)
    agglomerative_sizes = Counter(fitted_cluster_labels)
    agglomerative_ari = (
        float(adjusted_rand_score(fitted_primary_topics, fitted_cluster_labels))
        if len(sensitivity_indices) >= 2
        else 0.0
    )
    diagnostics.extend(
        (
            DiagnosticRow(
                "sensitivity",
                "agglomerative_fit_passages",
                len(sensitivity_indices),
                "pass" if len(sensitivity_indices) == len(corpus.rows) else "warning",
                "Nonzero fit-sample rows shared identically by NMF and agglomerative comparison.",
            ),
            DiagnosticRow(
                "sensitivity",
                "nmf_fit_cluster_sizes",
                ",".join(f"topic_{topic + 1}:{nmf_sizes[topic]}" for topic in sorted(nmf_sizes)),
                "pass",
                "Primary NMF assignments on the shared sensitivity fit universe.",
            ),
            DiagnosticRow(
                "sensitivity",
                "agglomerative_fit_cluster_sizes",
                ",".join(
                    f"cluster_{cluster + 1}:{agglomerative_sizes[cluster]}"
                    for cluster in sorted(agglomerative_sizes)
                ),
                "pass",
                "Cosine/average agglomerative assignments on the shared fit universe.",
            ),
            DiagnosticRow(
                "sensitivity",
                "agglomerative_adjusted_rand",
                agglomerative_ari,
                "pass" if agglomerative_ari >= config.min_agglomerative_ari else "warning",
                "Identical fit universe; L2 word/bigram TF-IDF; sklearn cosine metric and "
                "average linkage; ARI is permutation-invariant, so label alignment is not "
                f"required; threshold={config.min_agglomerative_ari:.2f}.",
            ),
        )
    )

    stability = _leave_one_deal_out(corpus, selected, config)
    bootstrap_stability = _bootstrap_stability(corpus, selected, config)
    bootstrap_summary = _bootstrap_summary(bootstrap_stability, selected.k)
    topics = _topic_rows(
        full_corpus,
        full_fit,
        stability,
        reconstruction_weights=reconstruction_weights,
    )
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
    bootstrap_rates = [row.recovery_rate for row in bootstrap_summary]
    diagnostics.extend(
        DiagnosticRow(
            "bootstrap_stability",
            f"{row.topic_id}_recovery_rate",
            row.recovery_rate,
            "pass" if row.recovery_rate >= config.min_topic_recovery_rate else "warning",
            f"Fixed-seed within-deal family bootstrap; cosine >= "
            f"{config.stability_threshold:.2f}; {row.recurrence_count}/{row.replicate_count} "
            "replicates recovered the aligned component.",
        )
        for row in bootstrap_summary
    )
    diagnostics.append(
        DiagnosticRow(
            "bootstrap_stability",
            "overall_recovery_rate",
            sum(row.recurrence_count for row in bootstrap_summary)
            / sum(row.replicate_count for row in bootstrap_summary)
            if bootstrap_summary
            else 0.0,
            "pass"
            if bootstrap_rates
            and all(rate >= config.min_topic_recovery_rate for rate in bootstrap_rates)
            else "warning",
            "Complementary robustness diagnostic only, not a topic-selection or relabeling rule; "
            "family representatives are resampled with replacement within each deal while "
            "preserving every deal's fit-row count and the original fitted vocabulary.",
        )
    )
    embedding_assignments, embedding_diagnostics = _embedding_robustness(corpus, selected, config)
    diagnostics.extend(embedding_diagnostics)
    return EmployeeTopicResult(
        status="modeled",
        reason=None,
        assignments=assignments,
        topics=topics,
        deal_topics=deal_topics,
        diagnostics=tuple(diagnostics),
        sensitivity_assignments=sensitivity_rows,
        stability=stability,
        bootstrap_stability=bootstrap_stability,
        bootstrap_summary=bootstrap_summary,
        embedding_robustness_assignments=embedding_assignments,
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
    if (
        min(
            config.nmf_iterations,
            config.projection_iterations,
            config.stability_iterations,
            config.bootstrap_replicates,
            config.bootstrap_iterations,
            config.embedding_svd_components,
            config.embedding_min_fit_rows,
            config.max_fit_passages,
        )
        < 1
    ):
        raise ValueError("Iteration and fit-sample limits must be positive.")
    if config.embedding_hdbscan_min_cluster_size < 2:
        raise ValueError("embedding_hdbscan_min_cluster_size must be at least 2.")
    if config.fit_balance not in FIT_BALANCE_MODES:
        raise ValueError(f"fit_balance must be one of {FIT_BALANCE_MODES}.")


def _passage_from_mapping(row: Mapping[str, str]) -> PassageRow:
    missing = sorted(_REQUIRED_COLUMNS - row.keys())
    if missing:
        raise ValueError(f"Passage row is missing required fields: {', '.join(missing)}")
    return PassageRow(
        **{field: str(row[field]) for field in _REQUIRED_COLUMNS},
        source_document_family_id=str(row.get("source_document_family_id", "")),
    )


def _prepare_passages(
    source_rows: Iterable[PassageRow | Mapping[str, str]],
) -> tuple[tuple[PassageRow, ...], int, int, int]:
    rows = [
        row if isinstance(row, PassageRow) else _passage_from_mapping(row) for row in source_rows
    ]
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


def _source_family_key(row: PassageRow) -> str:
    return row.source_document_family_id.strip() or f"document:{row.document_id}"


def _balanced_fit_indices(
    rows: Sequence[PassageRow], limit: int, seed: int, balance: str = "deal"
) -> tuple[int, ...]:
    """Choose a bounded, deterministic fit universe.

    One representative per (deal, provision family) is always taken first so repeated legal
    boilerplate cannot dominate. When more representatives remain than ``limit``, ``balance``
    decides how the cap is spread: round-robin over deals, round-robin over source-document
    families, or no balancing beyond the stable hash order.
    """
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
    if balance == "none":
        ordered = sorted(
            representatives,
            key=lambda index: (
                _stable_rank(seed, rows[index].deal_id, rows[index].passage_id),
                rows[index].passage_id,
            ),
        )
        return tuple(sorted(ordered[:limit]))
    group_of = _source_family_key if balance == "source_family" else (lambda row: row.deal_id)
    by_deal: dict[str, list[int]] = defaultdict(list)
    for index in representatives:
        row = rows[index]
        by_deal[group_of(row)].append(index)
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
    """Tokenize for the model, dropping single letters.

    Agreements print headings letter-spaced ("W I T N E S S E T H"), which tokenizes into bare
    letters. They are rare, so inverse-document-frequency weighting pushes them to the top of a
    component and they read as if the model found something. They carry no meaning, so they are
    dropped here rather than explained away in the report.
    """
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) > 1
        and token not in _STOP_WORDS
        and token not in _LEGAL_BOILERPLATE_STOP_WORDS
        and not _MODEL_MARKER_TOKEN.fullmatch(token)
    ]


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
            -(
                corpus_frequency[term]
                * (math.log((1 + n_rows) / (1 + document_frequency[term])) + 1)
            ),
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
            inverse_document_frequency = math.log((1 + n_rows) / (1 + document_frequency[term])) + 1
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


def _transform(rows: Sequence[PassageRow], fitted: _VectorizedCorpus) -> _VectorizedCorpus:
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
        matrix.append({index: value / norm for index, value in vector.items()} if norm else {})
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
                    weight_gram[topic][other] * components[other][feature] for other in range(k)
                )
                components[topic][feature] *= weight_cross[topic][feature] / (denominator + epsilon)
                components[topic][feature] = max(components[topic][feature], epsilon)

        component_gram = _gram(components, k, rows_are_topics=True)
        for row_index, sparse_row in enumerate(matrix):
            numerator = [0.0] * k
            for feature, value in sparse_row.items():
                for topic in range(k):
                    numerator[topic] += value * components[topic][feature]
            for topic in range(k):
                denominator = sum(
                    weights[row_index][other] * component_gram[other][topic] for other in range(k)
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
    normalized, _ = _project_weights_with_raw(matrix, components, iterations)
    return normalized


def _project_weights_with_raw(
    matrix: Sequence[Mapping[int, float]],
    components: Sequence[Sequence[float]],
    iterations: int,
) -> tuple[tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...]]:
    """Return normalized assignment weights and scale-preserving reconstruction weights."""
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
    weights = [[max(value, epsilon) for value in numerator] for numerator in numerators]
    for _ in range(iterations):
        for row_index, numerator in enumerate(numerators):
            for topic in range(k):
                denominator = sum(
                    weights[row_index][other] * component_gram[other][topic] for other in range(k)
                )
                weights[row_index][topic] *= numerator[topic] / (denominator + epsilon)
                weights[row_index][topic] = max(weights[row_index][topic], epsilon)
    raw = tuple(tuple(row) for row in weights)
    normalized = tuple(
        _normalize(row) if any(numerator) else tuple(0.0 for _ in range(k))
        for row, numerator in zip(weights, numerators, strict=True)
    )
    return normalized, raw


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


def _model_coherence(components: Sequence[Sequence[float]], corpus: _VectorizedCorpus) -> float:
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


def _candidate_diagnostics(fit: _NmfFit, config: TopicModelConfig) -> list[DiagnosticRow]:
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
    corpus: _VectorizedCorpus,
    fit: _NmfFit,
    stability: Sequence[StabilityRow],
    *,
    reconstruction_weights: Sequence[Sequence[float]] | None = None,
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
        margins = [_top_runner_up_margin(fit.weights[index]) for index in selected]
        residual_terms = _positive_residual_terms(
            corpus,
            reconstruction_weights or fit.weights,
            fit.components,
            selected,
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
                assignment_specificity=(sum(margins) / len(margins) if margins else 0.0),
                top_positive_residual_terms=tuple(term for term, _ in residual_terms),
                top_positive_residual_scores=tuple(score for _, score in residual_terms),
            )
        )
    return tuple(output)


def _top_runner_up_margin(weights: Sequence[float]) -> float:
    """Return the normalized top-topic minus runner-up assignment margin."""
    ordered = sorted(weights, reverse=True)
    if not ordered:
        return 0.0
    return ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)


def _positive_residual_terms(
    corpus: _VectorizedCorpus,
    weights: Sequence[Sequence[float]],
    components: Sequence[Sequence[float]],
    selected: Sequence[int],
    *,
    limit: int = 10,
) -> tuple[tuple[str, float], ...]:
    """Rank mean positive ``X - WH`` residuals for primary passages in one topic."""
    if not selected or not components:
        return ()
    totals = [0.0] * len(corpus.vocabulary)
    for row_index in selected:
        for feature in range(len(corpus.vocabulary)):
            prediction = sum(
                weights[row_index][topic] * components[topic][feature]
                for topic in range(len(components))
            )
            totals[feature] += max(corpus.matrix[row_index].get(feature, 0.0) - prediction, 0.0)
    means = [value / len(selected) for value in totals]
    ranked = sorted(
        (index for index, value in enumerate(means) if value > 0.0),
        key=lambda index: (-means[index], corpus.vocabulary[index]),
    )[:limit]
    return tuple((corpus.vocabulary[index], means[index]) for index in ranked)


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
                "pass" if generic_ratio <= config.max_generic_top_term_ratio else "warning",
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
    nonzero = [index for index, row in enumerate(corpus.matrix) if row]
    labels = [-1] * len(corpus.matrix)
    if len(nonzero) < k:
        return labels
    dense = _dense_rows(corpus, nonzero)
    fitted = AgglomerativeClustering(
        n_clusters=k,
        metric="cosine",
        linkage="average",
    ).fit_predict(dense)
    for index, label in zip(nonzero, fitted.tolist(), strict=True):
        labels[index] = int(label)
    return labels


def _embedding_robustness(
    corpus: _VectorizedCorpus, fit: _NmfFit, config: TopicModelConfig
) -> tuple[tuple[EmbeddingRobustnessAssignmentRow, ...], tuple[DiagnosticRow, ...]]:
    """Compare the NMF fit to deterministic local LSA clustering on the same fit rows.

    These are TF-IDF latent-semantic-analysis embeddings, not transformer embeddings. The slice
    is descriptive and cannot change the selected topic count, components, or labels.
    """
    if len(corpus.rows) < config.embedding_min_fit_rows:
        return (), (
            DiagnosticRow(
                "embedding_robustness",
                "lsa_status",
                "not_applicable",
                "pass",
                f"Prespecified only for fit universes with at least "
                f"{config.embedding_min_fit_rows} family-level rows; found {len(corpus.rows)}.",
            ),
        )

    component_count = min(
        config.embedding_svd_components,
        len(corpus.rows) - 1,
        len(corpus.vocabulary) - 1,
    )
    if component_count < 1:
        return (), (
            DiagnosticRow(
                "embedding_robustness",
                "lsa_status",
                "not_computable",
                "warning",
                "Need at least two fit rows and two vocabulary terms for truncated SVD.",
            ),
        )

    dense = _dense_rows(corpus, range(len(corpus.rows)))
    embedding = np.asarray(
        normalize(
            TruncatedSVD(
                n_components=component_count,
                algorithm="randomized",
                n_iter=7,
                random_state=config.seed,
            ).fit_transform(dense),
            norm="l2",
        ),
        dtype=float,
    )
    nonzero = np.linalg.norm(embedding, axis=1) > 0
    nonzero_indices = [index for index, value in enumerate(nonzero.tolist()) if value]
    nonzero_embedding = np.asarray([embedding[index] for index in nonzero_indices])

    hdbscan_labels = np.full(len(corpus.rows), -1, dtype=np.int64)
    if len(nonzero_indices) >= config.embedding_hdbscan_min_cluster_size:
        fitted_hdbscan = HDBSCAN(
            min_cluster_size=config.embedding_hdbscan_min_cluster_size,
            min_samples=None,
            metric="euclidean",
            cluster_selection_method="eom",
            allow_single_cluster=False,
        ).set_params(copy=False)
        for index, label in zip(
            nonzero_indices,
            fitted_hdbscan.fit_predict(nonzero_embedding).tolist(),
            strict=True,
        ):
            hdbscan_labels[index] = label

    agglomerative_labels = np.full(len(corpus.rows), -1, dtype=np.int64)
    if len(nonzero_indices) >= fit.k:
        fitted_agglomerative = AgglomerativeClustering(
            n_clusters=fit.k,
            metric="cosine",
            linkage="average",
        ).fit_predict(nonzero_embedding)
        for index, label in zip(nonzero_indices, fitted_agglomerative.tolist(), strict=True):
            agglomerative_labels[index] = label

    assignments: list[EmbeddingRobustnessAssignmentRow] = []
    for method, labels in (
        ("lsa_hdbscan", hdbscan_labels),
        ("lsa_agglomerative", agglomerative_labels),
    ):
        for row, label in zip(corpus.rows, labels.tolist(), strict=True):
            is_noise = label < 0
            assignments.append(
                EmbeddingRobustnessAssignmentRow(
                    passage_id=row.passage_id,
                    deal_id=row.deal_id,
                    method=method,
                    cluster_id="noise" if is_noise else f"cluster_{label + 1}",
                    noise=is_noise,
                )
            )

    primary = [_argmax(weights) for weights in fit.weights]
    hdbscan_comparable = [index for index, label in enumerate(hdbscan_labels) if label >= 0]
    hdbscan_clusters = {int(hdbscan_labels[index]) for index in hdbscan_comparable}
    hdbscan_ari: float | str = (
        float(
            adjusted_rand_score(
                [primary[index] for index in hdbscan_comparable],
                [int(hdbscan_labels[index]) for index in hdbscan_comparable],
            )
        )
        if len(hdbscan_comparable) >= 2 and len(hdbscan_clusters) >= 2
        else "not_comparable"
    )
    agglomerative_comparable = [
        index for index, label in enumerate(agglomerative_labels) if label >= 0
    ]
    agglomerative_ari: float | str = (
        float(
            adjusted_rand_score(
                [primary[index] for index in agglomerative_comparable],
                [int(agglomerative_labels[index]) for index in agglomerative_comparable],
            )
        )
        if len(agglomerative_comparable) >= 2
        else "not_comparable"
    )
    diagnostics = (
        DiagnosticRow(
            "embedding_robustness",
            "lsa_components",
            component_count,
            "pass",
            "Fixed-seed randomized TruncatedSVD of word/bigram TF-IDF; these are local LSA "
            "embeddings, not transformer semantic embeddings.",
        ),
        DiagnosticRow(
            "embedding_robustness",
            "lsa_fit_coverage_rate",
            float(nonzero.mean()),
            "pass" if bool(nonzero.all()) else "warning",
            "Nonzero LSA rows from the exact NMF fit universe; projected passages are excluded.",
        ),
        DiagnosticRow(
            "embedding_robustness",
            "hdbscan_min_cluster_size",
            config.embedding_hdbscan_min_cluster_size,
            "pass",
            "Prespecified sklearn HDBSCAN parameter; min_samples=None, Euclidean metric, "
            "EOM selection, and single-cluster solutions disabled.",
        ),
        DiagnosticRow(
            "embedding_robustness",
            "hdbscan_noise_count",
            int((hdbscan_labels < 0).sum()),
            "pass",
            "Fit-universe passages HDBSCAN marked as noise, including any zero LSA rows.",
        ),
        DiagnosticRow(
            "embedding_robustness",
            "hdbscan_cluster_count",
            len(hdbscan_clusters),
            "pass" if len(hdbscan_clusters) >= 2 else "warning",
            "Non-noise HDBSCAN clusters; cluster count is discovered, not set to selected NMF k.",
        ),
        DiagnosticRow(
            "embedding_robustness",
            "hdbscan_nmf_adjusted_rand",
            hdbscan_ari,
            "pass" if isinstance(hdbscan_ari, float) else "warning",
            f"ARI on {len(hdbscan_comparable)} non-noise shared fit rows only; no recovery "
            "threshold and no role in model selection.",
        ),
        DiagnosticRow(
            "embedding_robustness",
            "agglomerative_nmf_adjusted_rand",
            agglomerative_ari,
            "pass" if isinstance(agglomerative_ari, float) else "warning",
            "Cosine/average agglomerative clustering of normalized LSA rows with selected NMF k; "
            "ARI uses the same nonzero fit rows and has no role in model selection.",
        ),
    )
    return tuple(assignments), diagnostics


def _agglomerative_fit_predict(
    fitted: _VectorizedCorpus,
    full: _VectorizedCorpus,
    k: int,
    *,
    fitted_labels: Sequence[int] | None = None,
) -> list[int]:
    labels = (
        list(fitted_labels) if fitted_labels is not None else _agglomerative_assignments(fitted, k)
    )
    centroid_sums: list[defaultdict[int, float]] = [defaultdict(float) for _ in range(k)]
    cluster_sizes = Counter(label for label in labels if label >= 0)
    for sparse_row, label in zip(fitted.matrix, labels, strict=True):
        if label < 0:
            continue
        for feature, value in sparse_row.items():
            centroid_sums[label][feature] += value
    centroids: list[dict[int, float]] = []
    for label, values in enumerate(centroid_sums):
        centroid = {feature: value / cluster_sizes[label] for feature, value in values.items()}
        norm = math.sqrt(sum(value * value for value in centroid.values()))
        centroids.append(
            {feature: value / norm for feature, value in centroid.items()} if norm else {}
        )
    fitted_by_passage = {
        row.passage_id: label for row, label in zip(fitted.rows, labels, strict=True)
    }
    output: list[int] = []
    for row, sparse_row in zip(full.rows, full.matrix, strict=True):
        if row.passage_id in fitted_by_passage:
            output.append(fitted_by_passage[row.passage_id])
            continue
        if not sparse_row:
            output.append(-1)
            continue
        output.append(
            max(
                range(k),
                key=lambda label: (_sparse_dot(sparse_row, centroids[label]), -label),
            )
        )
    return output


def _dense_rows(corpus: _VectorizedCorpus, indices: Sequence[int]) -> np.ndarray:
    dense = np.zeros((len(indices), len(corpus.vocabulary)), dtype=np.float64)
    for dense_index, corpus_index in enumerate(indices):
        for feature, value in corpus.matrix[corpus_index].items():
            dense[dense_index, feature] = value
    return dense


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


def _bootstrap_stability(
    corpus: _VectorizedCorpus, full_fit: _NmfFit, config: TopicModelConfig
) -> tuple[BootstrapStabilityRow, ...]:
    """Refit NMF on within-deal bootstrap samples of the fixed family-level fit universe.

    ``corpus`` contains at most one passage per deal/provision family. Each replicate samples
    exactly the original number of rows for every deal, with replacement, so no large deal can
    gain share through the bootstrap and no projected or held-out passage can leak into fitting.
    The vocabulary and IDF weights remain those of the prespecified full fit.
    """
    by_deal: dict[str, tuple[int, ...]] = {}
    for deal_id in sorted({row.deal_id for row in corpus.rows}):
        by_deal[deal_id] = tuple(
            index for index, row in enumerate(corpus.rows) if row.deal_id == deal_id
        )

    output: list[BootstrapStabilityRow] = []
    bootstrap_config = replace(config, nmf_iterations=config.bootstrap_iterations)
    for replicate_id in range(1, config.bootstrap_replicates + 1):
        replicate_seed = config.seed + 1_700_003 + replicate_id
        generator = random.Random(replicate_seed)
        sampled_indices = [
            indices[generator.randrange(len(indices))]
            for deal_id in sorted(by_deal)
            for indices in (by_deal[deal_id],)
            for _ in range(len(indices))
        ]
        sampled_matrix = tuple(corpus.matrix[index] for index in sampled_indices)
        _, sampled_components, _ = _nmf(
            sampled_matrix,
            len(corpus.vocabulary),
            full_fit.k,
            replicate_seed + 10_000_019,
            bootstrap_config,
        )
        similarities = [
            [_cosine(full, sampled) for sampled in sampled_components]
            for full in full_fit.components
        ]
        alignment = _best_topic_alignment(similarities)
        for topic, aligned in enumerate(alignment):
            similarity = similarities[topic][aligned]
            output.append(
                BootstrapStabilityRow(
                    replicate_id=replicate_id,
                    topic_id=f"topic_{topic + 1}",
                    aligned_topic_id=f"bootstrap_topic_{aligned + 1}",
                    cosine_similarity=similarity,
                    recovered=similarity >= config.stability_threshold,
                )
            )
    return tuple(output)


def _bootstrap_summary(
    rows: Sequence[BootstrapStabilityRow], k: int
) -> tuple[BootstrapSummaryRow, ...]:
    output: list[BootstrapSummaryRow] = []
    for topic in range(k):
        topic_id = f"topic_{topic + 1}"
        selected = [row for row in rows if row.topic_id == topic_id]
        similarities = sorted(row.cosine_similarity for row in selected)
        recurrence_count = sum(row.recovered for row in selected)
        output.append(
            BootstrapSummaryRow(
                topic_id=topic_id,
                replicate_count=len(selected),
                recurrence_count=recurrence_count,
                recovery_rate=recurrence_count / len(selected) if selected else 0.0,
                median_cosine_similarity=_median(similarities) if similarities else 0.0,
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


def _sparse_dot(left: Mapping[int, float], right: Mapping[int, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(index, 0.0) for index, value in left.items())


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
        diagnostics=tuple(diagnostics) + (DiagnosticRow("fallback", reason, 1, "fail", detail),),
        sensitivity_assignments=(),
        stability=(),
    )
