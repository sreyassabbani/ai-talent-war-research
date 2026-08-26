"""Document-type baseline adjustment for standardized legal language.

Dr. Singh's method request: remove or control for standardized legal-document language
before comparing deals. This module computes corpus-level per-lexicon means within each
document family (merger agreements, proxies, press-release exhibits, employment/plan
documents, and so on). A family baseline is used only when the family has at least
``min_group_size`` passages; smaller families fall back to the corpus-wide mean, and the
fallback is recorded on every row so no adjusted number is ever unexplained.

Adjusted values are reported as ``raw - family_mean`` in lexicon-rate points (per 100
tokens) and interpreted only as higher/lower disclosure salience relative to the
document-type baseline.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BaselineConfig:
    min_group_size: int = 5
    rate_prefix: str = "rate_"
    rate_suffix: str = "_per100"


@dataclass(frozen=True)
class FamilyBaseline:
    document_family: str
    metric: str
    mean_rate: float
    group_size: int
    fallback_to_global: bool


def _to_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"Expected a numeric value, got {type(value).__name__}.")


def _metric_names(rows: Sequence[Mapping[str, object]], config: BaselineConfig) -> list[str]:
    names = [
        str(key)[len(config.rate_prefix) : -len(config.rate_suffix)]
        for key in rows[0]
        if str(key).startswith(config.rate_prefix) and str(key).endswith(config.rate_suffix)
    ]
    return sorted(names)


def compute_family_baselines(
    passage_rows: Sequence[Mapping[str, object]],
    *,
    config: BaselineConfig | None = None,
) -> tuple[list[FamilyBaseline], dict[str, float]]:
    """Return per-family baseline rows plus the effective mean applied to each metric."""
    cfg = config or BaselineConfig()
    metrics = _metric_names(passage_rows, cfg)
    by_family: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in passage_rows:
        by_family[str(row["document_family"])].append(row)

    global_means: dict[str, float] = {}
    for metric in metrics:
        key = f"{cfg.rate_prefix}{metric}{cfg.rate_suffix}"
        values = [_to_float(row[key]) for row in passage_rows]
        global_means[metric] = sum(values) / len(values) if values else 0.0

    baselines: list[FamilyBaseline] = []
    for family in sorted(by_family):
        members = by_family[family]
        for metric in metrics:
            key = f"{cfg.rate_prefix}{metric}{cfg.rate_suffix}"
            values = [_to_float(row[key]) for row in members]
            use_family = len(members) >= cfg.min_group_size
            mean = sum(values) / len(values) if use_family and values else global_means[metric]
            baselines.append(
                FamilyBaseline(
                    document_family=family,
                    metric=metric,
                    mean_rate=round(mean, 4),
                    group_size=len(members),
                    fallback_to_global=not use_family,
                )
            )

    return baselines, global_means


def apply_baselines(
    passage_rows: Sequence[Mapping[str, object]],
    baselines: Sequence[FamilyBaseline],
    *,
    config: BaselineConfig | None = None,
) -> list[dict[str, object]]:
    """Add adjusted rates and baseline metadata to every passage row."""
    cfg = config or BaselineConfig()
    lookup: dict[tuple[str, str], FamilyBaseline] = {
        (baseline.document_family, baseline.metric): baseline for baseline in baselines
    }
    adjusted_rows: list[dict[str, object]] = []
    for row in passage_rows:
        family = str(row["document_family"])
        updated = dict(row)
        for metric in _metric_names([row], cfg):
            key = f"{cfg.rate_prefix}{metric}{cfg.rate_suffix}"
            entry = lookup.get((family, metric))
            if entry is None:
                continue
            raw = _to_float(row[key])
            updated[f"{key}_adjusted"] = round(raw - entry.mean_rate, 4)
            updated[f"baseline_mean_{metric}"] = entry.mean_rate
            updated[f"baseline_fallback_{metric}"] = int(entry.fallback_to_global)
        updated["raw_or_adjusted"] = "raw_and_baseline_adjusted"
        adjusted_rows.append(updated)
    return adjusted_rows


__all__ = [
    "BaselineConfig",
    "FamilyBaseline",
    "apply_baselines",
    "compute_family_baselines",
]
