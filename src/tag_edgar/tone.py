"""Deterministic tone and word-use measurement over employee passages.

Every measure is a transparent lexical rate reported as drafting style or disclosure
salience, never as an employee mental state or retention outcome. Rates are computed per
100 tokens at the passage level and aggregated to deals by unweighted passage means so
that document volume alone cannot determine results.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

_WORD = re.compile(r"\b[\w'’-]+\b", re.UNICODE)

LEXICONS: dict[str, tuple[str, ...]] = {
    "positive": (
        "opportunity",
        "strength",
        "strengths",
        "success",
        "successful",
        "valuable",
        "innovation",
        "innovative",
        "growth",
        "support",
        "enhance",
        "leading",
    ),
    "negative": (
        "risk",
        "risks",
        "loss",
        "losses",
        "failure",
        "disruption",
        "uncertainty",
        "adverse",
        "difficulty",
        "attrition",
        "departure",
        "departures",
    ),
    "hedging": (
        "may",
        "might",
        "could",
        "approximately",
        "generally",
        "expected",
        "anticipated",
        "potential",
        "subject to",
    ),
    "modality": ("shall", "must", "may", "will"),
    "protection_program": (
        "change in control",
        "change-of-control",
        "severance",
        "good reason",
        "protective period",
        "protected period",
        "double trigger",
        "outplacement",
        "garden leave",
    ),
    "retention": (
        "retention",
        "retain",
        "retained",
        "remain employed",
        "continued employment",
        "continued service",
        "stay bonus",
        "transaction bonus",
        "retention award",
    ),
    "pay_wages": (
        "salary",
        "salaries",
        "wages",
        "compensation",
        "bonus",
        "bonuses",
        "incentive",
        "payroll",
        "base pay",
    ),
    "benefits": (
        "benefits",
        "health insurance",
        "pension",
        "401(k)",
        "welfare",
        "vacation",
        "severance benefits",
    ),
    "equity_vesting": (
        "stock option",
        "stock options",
        "restricted stock",
        "restricted stock unit",
        "rsu",
        "rsus",
        "vesting",
        "vested",
        "forfeiture",
        "forfeited",
        "equity award",
        "conversion",
    ),
    "termination_severance": (
        "termination",
        "terminated",
        "terminate",
        "without cause",
        "for cause",
        "resignation",
        "layoff",
        "layoffs",
        "reduction in force",
        "separation",
    ),
    "employee_workforce": (
        "employee",
        "employees",
        "workforce",
        "personnel",
        "team members",
        "staff",
        "headcount",
    ),
}

_COMPILED_LEXICONS: dict[str, list[re.Pattern[str]]] = {
    name: [re.compile(rf"(?<!\w){re.escape(term.strip())}(?!\w)", re.IGNORECASE) for term in terms]
    for name, terms in LEXICONS.items()
}


def _to_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"Expected a numeric value, got {type(value).__name__}.")


def _to_int(value: object) -> int:
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"Expected an integer value, got {type(value).__name__}.")


def token_count(text: str) -> int:
    return len(_WORD.findall(text))


def lexicon_rates(text: str) -> dict[str, float]:
    """Per-100-token rates for every configured lexicon on one text."""
    total = token_count(text)
    if total == 0:
        return {name: 0.0 for name in _COMPILED_LEXICONS}
    return {
        name: round(100.0 * sum(len(p.findall(text)) for p in patterns) / total, 4)
        for name, patterns in _COMPILED_LEXICONS.items()
    }


def lexicon_counts(text: str) -> dict[str, int]:
    return {
        name: sum(len(pattern.findall(text)) for pattern in patterns)
        for name, patterns in _COMPILED_LEXICONS.items()
    }


def passage_tone_rows(
    passages: Iterable[Mapping[str, object]],
    *,
    text_key: str = "text",
    id_key: str = "passage_id",
) -> list[dict[str, object]]:
    """Compute raw lexical rates for each passage row."""
    rows: list[dict[str, object]] = []
    for passage in passages:
        text = str(passage[text_key])
        counts = lexicon_counts(text)
        rates = lexicon_rates(text)
        rows.append(
            {
                id_key: passage[id_key],
                "deal_id": passage.get("deal_id", ""),
                "document_family": passage.get("document_family", "other"),
                "token_count": token_count(text),
                **{f"count_{name}": counts[name] for name in _COMPILED_LEXICONS},
                **{f"rate_{name}_per100": rates[name] for name in _COMPILED_LEXICONS},
                "raw_or_adjusted": "raw",
            }
        )
    return rows


def deal_tone_summary(
    passage_rows: Sequence[Mapping[str, object]],
    *,
    baseline_means: dict[str, float] | None = None,
) -> list[dict[str, object]]:
    """Aggregate passage-level rates into deals using unweighted passage means."""
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in passage_rows:
        grouped.setdefault(str(row["deal_id"]), []).append(row)

    summaries: list[dict[str, object]] = []
    for deal_id in sorted(grouped):
        rows = grouped[deal_id]
        summary: dict[str, object] = {
            "deal_id": deal_id,
            "passage_count": len(rows),
            "total_tokens": sum(_to_int(row["token_count"]) for row in rows),
        }
        for name in _COMPILED_LEXICONS:
            key = f"rate_{name}_per100"
            values = [_to_float(row[key]) for row in rows]
            summary[key] = round(sum(values) / len(values), 4)
            if baseline_means is not None and name in baseline_means:
                summary[f"{key}_adjusted"] = round(
                    _to_float(summary[key]) - baseline_means[name], 4
                )
        summaries.append(summary)
    return summaries


__all__ = [
    "LEXICONS",
    "deal_tone_summary",
    "lexicon_counts",
    "lexicon_rates",
    "passage_tone_rows",
    "token_count",
]
