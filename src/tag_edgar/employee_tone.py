"""Deterministic tone and word-usage analysis over included employee passages.

Implements the supervisor's August 21 request: after removing the standardized
legal-register baseline (demeaning each passage against the mean register of
its document type), characterize how
each deal writes about employees -- sentiment, hedging, obligation modality,
negative employment outcomes, and protection-program language -- and compare
word usage across deals with self-contained HTML word clouds.

Tone descriptors characterize drafting style only. They are not evidence of
actual employee outcomes and must not be presented as concern or importance
by themselves.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .corpus_validation import CorpusValidationState
from .storage import write_dict_csv

TONE_LEXICON_VERSION = "employee-tone-v1"
MIN_BASELINE_GROUP_PASSAGES = 2

PASSAGE_TONE_FIELDS = [
    "passage_id",
    "deal_id",
    "document_family_id",
    "baseline_document_type",
    "tokens",
    "pos_count",
    "neg_count",
    "net_tone_per100",
    "hedge_count",
    "hedge_per100",
    "shall_count",
    "may_count",
    "modality_shall_share",
    "negout_count",
    "negout_per100",
    "protect_count",
    "protect_per100",
    "net_tone_residual",
    "hedge_residual",
    "negout_residual",
    "protect_residual",
]

FAMILY_BASELINE_FIELDS = [
    "document_family_id",
    "passages",
    "mean_tokens",
    "mean_net_tone_per100",
    "mean_hedge_per100",
    "mean_negout_per100",
    "mean_protect_per100",
]

TYPE_BASELINE_FIELDS = [
    "document_type",
    "passages",
    "mean_tokens",
    "mean_net_tone_per100",
    "mean_hedge_per100",
    "mean_negout_per100",
    "mean_protect_per100",
]

DEAL_TONE_FIELDS = [
    "deal_id",
    "passages",
    "tokens",
    "mean_net_tone_per100",
    "mean_net_tone_residual",
    "mean_hedge_per100",
    "mean_hedge_residual",
    "mean_negout_per100",
    "mean_negout_residual",
    "mean_protect_per100",
    "mean_protect_residual",
    "mean_modality_shall_share",
]

TERM_USAGE_FIELDS = [
    "deal_id",
    "term",
    "count",
    "per_1000_tokens",
    "share_of_deal_mentions",
]

_POSITIVE_TERMS = (
    "accelerate",
    "accelerated",
    "enhance",
    "enhanced",
    "favorable",
    "improve",
    "improved",
    "incentive",
    "incentives",
    "preserve",
    "preserved",
    "protect",
    "protected",
    "safeguard",
    "safeguarded",
    "security",
    "strengthen",
    "strengthened",
    "support",
    "supported",
    "welfare",
    "well-being",
    "bonus",
    "bonuses",
    "benefit",
    "benefits",
    "opportunity",
    "opportunities",
    "reward",
    "rewards",
    "advantage",
    "valuable",
    "successful",
    "continue",
    "continued",
    "continuity",
    "comparable",
    "equivalent",
)

_NEGATIVE_TERMS = (
    "terminate",
    "terminated",
    "termination",
    "terminates",
    "forfeit",
    "forfeited",
    "forfeiture",
    "forfeits",
    "layoff",
    "layoffs",
    "discharge",
    "dismissed",
    "dismissal",
    "breach",
    "breaches",
    "violated",
    "violation",
    "violations",
    "liability",
    "liabilities",
    "loss",
    "losses",
    "failure",
    "fail",
    "adverse",
    "harm",
    "harmed",
    "impair",
    "impaired",
    "impairment",
    "risk",
    "risks",
    "threatened",
    "dispute",
    "disputes",
    "claim",
    "claims",
    "penalty",
    "penalties",
    "default",
    "divest",
    "divestiture",
    "discontinue",
    "discontinued",
    "reduce",
    "reduced",
    "reduction",
    "reductions",
    "eliminate",
    "eliminated",
    "conflict",
    "conflicts",
    "restrict",
    "restricted",
    "restriction",
    "restrictions",
    "prohibit",
    "prohibited",
    "noncompetition",
    "non-compete",
)

_HEDGE_PHRASES = (
    "may",
    "might",
    "could",
    "approximately",
    "generally",
    "typically",
    "subject to",
    "to the extent",
    "deemed",
    "if any",
    "as applicable",
    "where appropriate",
    "reasonable efforts",
    "commercially reasonable",
    "best efforts",
    "material adverse effect",
)

_NEGATIVE_OUTCOME_PHRASES = (
    "termination of employment",
    "loss of employment",
    "layoff",
    "layoffs",
    "reduction in force",
    "workforce reduction",
    "discharge",
    "dismissal",
    "separation from employment",
    "departure",
    "cease to be employed",
    "ceases to be employed",
)

_PROTECTION_PHRASES = (
    "retention",
    "retention bonus",
    "stay bonus",
    "transaction bonus",
    "severance",
    "continued employment",
    "continued service",
    "continuing employee",
    "continuing employees",
    "remain employed",
    "base salary",
    "welfare benefits",
    "employee benefit plan",
    "401(k)",
    "pension",
    "equity award",
    "restricted stock",
    "vesting",
    "acceleration",
    "outplacement",
    "transition assistance",
    "cobra",
)

_COMPARISON_VOCABULARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("retention", ("retention",)),
    ("stay bonus", ("stay bonus",)),
    ("transaction bonus", ("transaction bonus",)),
    ("severance", ("severance",)),
    ("vesting", ("vesting",)),
    ("equity award", ("equity award", "equity awards")),
    ("stock option", ("stock option", "stock options")),
    ("restricted stock", ("restricted stock",)),
    ("rsu", ("rsu", "rsus")),
    ("base salary", ("base salary",)),
    ("wages", ("wage", "wages")),
    ("bonus", ("bonus", "bonuses")),
    ("benefit plan", ("benefit plan", "benefit plans")),
    ("401(k)", ("401(k)",)),
    ("pension", ("pension", "pensions")),
    ("welfare", ("welfare",)),
    ("health", ("health",)),
    ("insurance", ("insurance",)),
    ("cobra", ("cobra",)),
    ("continued employment", ("continued employment",)),
    ("continued service", ("continued service", "continuing employee", "continuing employees")),
    ("termination of employment", ("termination of employment",)),
    ("layoff", ("layoff", "layoffs")),
    ("reduction in force", ("reduction in force",)),
    ("workforce", ("workforce",)),
    ("employees", ("employee", "employees")),
)

_CLOUD_STOPWORDS = frozenset(
    ["a", "all", "and", "any", "are", "as", "at", "be", "been", "by", "for", "from", "has", "have", "here", "hereby", "herein", "hereinabove", "hereinbelow", "hereto", "hereunder", "herewith", "if", "in", "into", "is", "it", "its", "of", "on", "or", "pursuant", "shall", "so", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "those", "to", "under", "until", "up", "upon", "was", "were", "will", "with", "within", "without", "would", "section", "subsection", "clause", "article", "paragraph", "agreement", "agreements", "party", "parties", "company", "corporation", "parent", "subsidiary", "subsidiaries", "purchaser", "seller", "buyer", "borrower", "lender", "provided", "however", "provided", "further", "means", "meaning", "respect", "respects", "pursuant", "foregoing"]
)

_WORD = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")
_CLOUD_PALETTE = ("#2b6cb0", "#2f855a", "#b7791f", "#9b2c2c", "#6b46c1", "#2c7a7b", "#d69e2e")


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


@dataclass(frozen=True)
class ToneAnalysis:
    """Deterministic tone and word-usage analysis of included passages."""

    passage_rows: tuple[dict[str, object], ...]
    family_rows: tuple[dict[str, object], ...]
    type_rows: tuple[dict[str, object], ...]
    deal_rows: tuple[dict[str, object], ...]
    term_rows: tuple[dict[str, object], ...]
    cloud_pages: tuple[tuple[str, str], ...]
    index_page: str
    manifest: dict[str, object]
    passage_count: int
    deal_count: int


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    tokens = [re.escape(token) for token in phrase.split()]
    return re.compile(r"(?<![a-z0-9])" + r"[\s-]+".join(tokens) + r"(?![a-z0-9])")


@dataclass(frozen=True)
class _Lexicon:
    positive: tuple[re.Pattern[str], ...]
    negative: tuple[re.Pattern[str], ...]
    hedges: tuple[re.Pattern[str], ...]
    negout: tuple[re.Pattern[str], ...]
    protections: tuple[re.Pattern[str], ...]
    shall: re.Pattern[str]
    may: re.Pattern[str]
    vocabulary: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]


@dataclass(frozen=True)
class _PassageTone:
    passage_id: str
    deal_id: str
    document_family_id: str
    tokens: int
    pos_count: int
    neg_count: int
    hedge_count: int
    shall_count: int
    may_count: int
    negout_count: int
    protect_count: int


def _build_lexicon() -> _Lexicon:
    return _Lexicon(
        positive=tuple(_phrase_pattern(term) for term in _POSITIVE_TERMS),
        negative=tuple(_phrase_pattern(term) for term in _NEGATIVE_TERMS),
        hedges=tuple(_phrase_pattern(term) for term in _HEDGE_PHRASES),
        negout=tuple(_phrase_pattern(term) for term in _NEGATIVE_OUTCOME_PHRASES),
        protections=tuple(_phrase_pattern(term) for term in _PROTECTION_PHRASES),
        shall=_phrase_pattern("shall"),
        may=re.compile(r"(?<![a-z0-9])may(?![a-z0-9])"),
        vocabulary=tuple(
            (term, tuple(_phrase_pattern(phrase) for phrase in phrases))
            for term, phrases in _COMPARISON_VOCABULARY
        ),
    )


_LEXICON = _build_lexicon()


def _count_matches(patterns: tuple[re.Pattern[str], ...], text: str) -> int:
    return sum(len(pattern.findall(text)) for pattern in patterns)


def _tone_features(passage: dict[str, str]) -> _PassageTone:
    text = _normalize(passage.get("text", ""))
    tokens = len(_WORD.findall(text))
    shall_count = len(_LEXICON.shall.findall(text))
    may_count = len(_LEXICON.may.findall(text))
    return _PassageTone(
        passage_id=passage["passage_id"],
        deal_id=passage["deal_id"],
        document_family_id=passage["document_family_id"],
        tokens=tokens,
        pos_count=_count_matches(_LEXICON.positive, text),
        neg_count=_count_matches(_LEXICON.negative, text),
        hedge_count=_count_matches(_LEXICON.hedges, text),
        shall_count=shall_count,
        may_count=may_count,
        negout_count=_count_matches(_LEXICON.negout, text),
        protect_count=_count_matches(_LEXICON.protections, text),
    )


def _per100(count: int, tokens: int) -> float:
    if tokens <= 0:
        return 0.0
    return count * 100.0 / tokens


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _fmt(value: float) -> str:
    return f"{value:.6f}"


def _cloud_html(deal_id: str, terms: list[tuple[str, int]]) -> str:
    if not terms:
        terms = [("no employee passages", 1)]
    max_count = max(count for _, count in terms)
    spans: list[str] = []
    for index, (term, count) in enumerate(terms):
        size = 12 + int(30 * (count / max_count) ** 0.5)
        color = _CLOUD_PALETTE[index % len(_CLOUD_PALETTE)]
        spans.append(
            f'<span style="font-size:{size}px;color:{color};margin:6px;display:inline-block;">'
            f"{html.escape(term)} <small>({count})</small></span>"
        )
    body = "".join(spans)
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Employee word cloud: "
        f"{html.escape(deal_id)}</title></head>"
        "<body style='font-family:-apple-system,Segoe UI,sans-serif;background:#fffdf5;'>"
        "<h2 style='font-weight:600;'>Employee-disclosure word cloud &mdash; deal "
        f"{html.escape(deal_id)}</h2>"
        "<p style='color:#555;'>Term counts across included employee passages "
        "(stopwords and legal boilerplate removed).</p>"
        f"<div style='line-height:1.6;max-width:900px;'>{body}</div>"
        "</body></html>"
    )


def _index_html(pages: tuple[tuple[str, list[tuple[str, int]]], ...]) -> str:
    items: list[str] = []
    for deal_id, terms in pages:
        top = ", ".join(f"{html.escape(term)} ({count})" for term, count in terms[:5])
        items.append(
            f"<li><a href='cloud_{html.escape(deal_id)}.html'>{html.escape(deal_id)}</a> "
            f"&mdash; top terms: {top}</li>"
        )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Employee word clouds by deal</title></head>"
        "<body style='font-family:-apple-system,Segoe UI,sans-serif;'>"
        "<h2>Employee-disclosure word clouds by deal</h2><ol>"
        + "".join(items)
        + "</ol></body></html>"
    )


def _deal_terms(texts: list[str]) -> list[tuple[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    for text in texts:
        for word in _WORD.findall(text):
            if word not in _CLOUD_STOPWORDS and len(word) > 2:
                counts[word] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:40]


def analyze_employee_tone(
    passages_csv: Path, *, corpus_validation: CorpusValidationState | None = None
) -> ToneAnalysis:
    """Analyze included passages and return deterministic tone/word-usage tables.

    ``corpus_validation`` is recorded in the manifest so every tone table names the corpus gate
    it was computed under; when omitted the manifest says so explicitly.
    """
    with passages_csv.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {"passage_id", "deal_id", "document_family_id", "text", "inclusion_status"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"Passages CSV missing required columns: {sorted(required)}")
        rows = [dict(row) for row in reader]

    included = [row for row in rows if row.get("inclusion_status", "") == "included"]
    if not included:
        raise ValueError("Passages CSV contains no included passages to analyze.")
    included.sort(key=lambda row: row["passage_id"])

    features = [_tone_features(row) for row in included]
    for feature, source in zip(features, included, strict=True):
        assert feature.passage_id == source["passage_id"]
    normalized_texts = {
        row["passage_id"]: _normalize(row.get("text", "")) for row in included
    }
    baseline_types = {
        row["passage_id"]: (row.get("document_type", "").strip() or "(untyped)")
        for row in included
    }

    family_groups: dict[str, list[_PassageTone]] = defaultdict(list)
    type_groups: dict[str, list[_PassageTone]] = defaultdict(list)
    deal_groups: dict[str, list[_PassageTone]] = defaultdict(list)
    for feature in features:
        family_groups[feature.document_family_id].append(feature)
        type_groups[baseline_types[feature.passage_id]].append(feature)
        deal_groups[feature.deal_id].append(feature)

    def _group_means(group: list[_PassageTone]) -> dict[str, float]:
        return {
            "net": _mean([_per100(f.pos_count - f.neg_count, f.tokens) for f in group]),
            "hedge": _mean([_per100(f.hedge_count, f.tokens) for f in group]),
            "negout": _mean([_per100(f.negout_count, f.tokens) for f in group]),
            "protect": _mean([_per100(f.protect_count, f.tokens) for f in group]),
        }

    family_means = {family_id: _group_means(group) for family_id, group in sorted(family_groups.items())}
    type_means = {type_id: _group_means(group) for type_id, group in sorted(type_groups.items())}
    corpus_means = _group_means(features)

    def _baseline(type_id: str) -> dict[str, float]:
        if len(type_groups[type_id]) >= MIN_BASELINE_GROUP_PASSAGES:
            return type_means[type_id]
        return corpus_means


    family_rows: list[dict[str, object]] = []
    for family_id, group in sorted(family_groups.items()):
        means = family_means[family_id]
        family_rows.append(
            {
                "document_family_id": family_id,
                "passages": len(group),
                "mean_tokens": _fmt(_mean([float(f.tokens) for f in group])),
                "mean_net_tone_per100": _fmt(means["net"]),
                "mean_hedge_per100": _fmt(means["hedge"]),
                "mean_negout_per100": _fmt(means["negout"]),
                "mean_protect_per100": _fmt(means["protect"]),
            }
        )

    type_rows: list[dict[str, object]] = []
    for type_id, group in sorted(type_groups.items()):
        means = type_means[type_id]
        type_rows.append(
            {
                "document_type": type_id,
                "passages": len(group),
                "mean_tokens": _fmt(_mean([float(f.tokens) for f in group])),
                "mean_net_tone_per100": _fmt(means["net"]),
                "mean_hedge_per100": _fmt(means["hedge"]),
                "mean_negout_per100": _fmt(means["negout"]),
                "mean_protect_per100": _fmt(means["protect"]),
            }
        )

    passage_rows: list[dict[str, object]] = []
    for feature in features:
        baseline_id = baseline_types[feature.passage_id]
        means = _baseline(baseline_id)
        net = _per100(feature.pos_count - feature.neg_count, feature.tokens)
        hedge = _per100(feature.hedge_count, feature.tokens)
        negout = _per100(feature.negout_count, feature.tokens)
        protect = _per100(feature.protect_count, feature.tokens)
        modality = (
            feature.shall_count / (feature.shall_count + feature.may_count)
            if (feature.shall_count + feature.may_count) > 0
            else None
        )
        passage_rows.append(
            {
                "passage_id": feature.passage_id,
                "deal_id": feature.deal_id,
                "document_family_id": feature.document_family_id,
                "baseline_document_type": baseline_id,
                "tokens": feature.tokens,
                "pos_count": feature.pos_count,
                "neg_count": feature.neg_count,
                "net_tone_per100": _fmt(net),
                "hedge_count": feature.hedge_count,
                "hedge_per100": _fmt(hedge),
                "shall_count": feature.shall_count,
                "may_count": feature.may_count,
                "modality_shall_share": "" if modality is None else _fmt(modality),
                "negout_count": feature.negout_count,
                "negout_per100": _fmt(negout),
                "protect_count": feature.protect_count,
                "protect_per100": _fmt(protect),
                "net_tone_residual": _fmt(net - means["net"]),
                "hedge_residual": _fmt(hedge - means["hedge"]),
                "negout_residual": _fmt(negout - means["negout"]),
                "protect_residual": _fmt(protect - means["protect"]),
            }
        )

    deal_rows: list[dict[str, object]] = []
    for deal_id, group in sorted(deal_groups.items()):
        deal_rows.append(
            {
                "deal_id": deal_id,
                "passages": len(group),
                "tokens": sum(f.tokens for f in group),
                "mean_net_tone_per100": _fmt(_mean([_per100(f.pos_count - f.neg_count, f.tokens) for f in group])),
                "mean_net_tone_residual": _fmt(
                    _mean(
                        [
                            _per100(f.pos_count - f.neg_count, f.tokens)
                            - _baseline(baseline_types[f.passage_id])["net"]
                            for f in group
                        ]
                    )
                ),
                "mean_hedge_per100": _fmt(_mean([_per100(f.hedge_count, f.tokens) for f in group])),
                "mean_hedge_residual": _fmt(
                    _mean(
                        [
                            _per100(f.hedge_count, f.tokens)
                            - _baseline(baseline_types[f.passage_id])["hedge"]
                            for f in group
                        ]
                    )
                ),
                "mean_negout_per100": _fmt(_mean([_per100(f.negout_count, f.tokens) for f in group])),
                "mean_negout_residual": _fmt(
                    _mean(
                        [
                            _per100(f.negout_count, f.tokens)
                            - _baseline(baseline_types[f.passage_id])["negout"]
                            for f in group
                        ]
                    )
                ),
                "mean_protect_per100": _fmt(_mean([_per100(f.protect_count, f.tokens) for f in group])),
                "mean_protect_residual": _fmt(
                    _mean(
                        [
                            _per100(f.protect_count, f.tokens)
                            - _baseline(baseline_types[f.passage_id])["protect"]
                            for f in group
                        ]
                    )
                ),
                "mean_modality_shall_share": _fmt(
                    _mean(
                        [
                            f.shall_count / (f.shall_count + f.may_count)
                            if (f.shall_count + f.may_count) > 0
                            else 0.0
                            for f in group
                        ]
                    )
                ),
            }
        )

    texts_by_deal: dict[str, list[str]] = defaultdict(list)
    for row in included:
        texts_by_deal[row["deal_id"]].append(normalized_texts[row["passage_id"]])

    term_rows: list[dict[str, object]] = []
    cloud_data: list[tuple[str, list[tuple[str, int]]]] = []
    for deal_id in sorted(deal_groups):
        texts = texts_by_deal[deal_id]
        deal_tokens = sum(len(_WORD.findall(text)) for text in texts)
        mention_counts: dict[str, int] = {}
        total_mentions = 0
        for term, patterns in _LEXICON.vocabulary:
            count = sum(_count_matches(patterns, text) for text in texts)
            mention_counts[term] = count
            total_mentions += count
        for term in sorted(mention_counts):
            count = mention_counts[term]
            share = count / total_mentions if total_mentions > 0 else 0.0
            term_rows.append(
                {
                    "deal_id": deal_id,
                    "term": term,
                    "count": count,
                    "per_1000_tokens": _fmt(count * 1000.0 / deal_tokens if deal_tokens else 0.0),
                    "share_of_deal_mentions": _fmt(share),
                }
            )
        cloud_data.append((deal_id, _deal_terms(texts)))

    cloud_pages = tuple((deal_id, _cloud_html(deal_id, terms)) for deal_id, terms in cloud_data)
    index_page = _index_html(tuple(cloud_data))
    manifest: dict[str, object] = {
        "schema_version": 1,
        "lexicon_version": TONE_LEXICON_VERSION,
        "method": (
            "deterministic embedded lexicons; per-100-token rates; demeaning subtracts "
            "the mean legal-register baseline per document type (corpus fallback for "
            "untyped passages, or corpus means for document types with fewer than "
            f"{MIN_BASELINE_GROUP_PASSAGES} passages) so deals are comparable against average "
            "legal language; "
            "tone describes drafting style only and is not evidence of employee outcomes"
        ),
        "passages_csv_sha256": hashlib.sha256(passages_csv.read_bytes()).hexdigest(),
        "corpus_validation": (
            corpus_validation.as_manifest()
            if corpus_validation is not None
            else {"status": "no_corpus_validation_evidence", "accepted": False}
        ),
        "interpretation_status": (
            "secondary_diagnostic_on_validated_corpus"
            if corpus_validation is not None and corpus_validation.accepted
            else "secondary_diagnostic_corpus_not_validated"
        ),
        "included_passages": len(included),
        "deals": len(deal_groups),
        "document_families": len(family_groups),
        "comparison_vocabulary": [term for term, _ in _COMPARISON_VOCABULARY],
    }
    return ToneAnalysis(
        passage_rows=tuple(passage_rows),
        family_rows=tuple(family_rows),
        type_rows=tuple(type_rows),
        deal_rows=tuple(deal_rows),
        term_rows=tuple(term_rows),
        cloud_pages=cloud_pages,
        index_page=index_page,
        manifest=manifest,
        passage_count=len(included),
        deal_count=len(deal_groups),
    )


def write_employee_tone(output_dir: Path, analysis: ToneAnalysis) -> None:
    """Write tone tables, word-cloud pages, and the manifest deterministically."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dict_csv(output_dir / "passage_tone.csv", analysis.passage_rows, PASSAGE_TONE_FIELDS)
    write_dict_csv(output_dir / "family_baseline.csv", analysis.family_rows, FAMILY_BASELINE_FIELDS)
    write_dict_csv(output_dir / "type_baseline.csv", analysis.type_rows, TYPE_BASELINE_FIELDS)
    write_dict_csv(output_dir / "deal_tone_summary.csv", analysis.deal_rows, DEAL_TONE_FIELDS)
    write_dict_csv(output_dir / "deal_term_usage.csv", analysis.term_rows, TERM_USAGE_FIELDS)
    clouds_dir = output_dir / "wordclouds"
    clouds_dir.mkdir(parents=True, exist_ok=True)
    for deal_id, page in analysis.cloud_pages:
        (clouds_dir / f"cloud_{deal_id}.html").write_text(page, encoding="utf-8")
    (clouds_dir / "index.html").write_text(analysis.index_page, encoding="utf-8")
    (output_dir / "tone_manifest.json").write_text(
        json.dumps(analysis.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
