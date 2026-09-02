"""Label retrieved deals for AI and talent language, after selection rather than before it.

Selecting deals by an AI keyword was what produced a 13-deal sample: the screen picked companies
whose acquirers do not file with the SEC. Applying the same screen *after* a disclosure-first
selection asks a different and answerable question — among transactions whose employee terms are
on the public record, which ones describe the target in AI terms, and which use explicit
team-acquisition language.

Every label here is machine-derived from the filing text and carries
``machine_suggested_pending_human_review``. Evidence is quoted with its source URL so a reviewer
can confirm or overturn each one. A deal labelled ``none`` is a deal whose retrieved filings do
not describe it in AI terms; that is a statement about disclosure, not about the technology.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .ai_screening import (
    detect_talent_signals,
    screen_ai_text_for_target,
)
from .source_links import text_fragment_url

__all__ = [
    "AI_LABEL_FIELDS",
    "DealAiLabel",
    "label_deal",
    "write_deal_ai_labels",
]

AI_LABEL_FIELDS = [
    "deal_id",
    "acquirer_name",
    "target_name",
    "ai_label",
    "ai_evidence_weight",
    "ai_terms",
    "ai_excerpt",
    "ai_source_url",
    "ai_source_highlight_url",
    "talent_join_language",
    "talent_acquihire_explicit",
    "talent_license_and_hire_explicit",
    "talent_excerpt",
    "documents_screened",
    "review_status",
]

# Weight thresholds. ``screen_ai_text_for_target`` already requires evidence to sit near a
# distinctive target-name anchor, so these separate a confident description from a passing one.
_EXPLICIT_WEIGHT = 5
_ADJACENT_WEIGHT = 3

_REVIEW_STATUS = "machine_suggested_pending_human_review"


@dataclass(frozen=True)
class DealAiLabel:
    deal_id: str
    label: str
    weight: int
    terms: tuple[str, ...]
    excerpt: str
    source_url: str
    documents_screened: int
    join_language: bool
    acquihire_explicit: bool
    license_and_hire_explicit: bool
    talent_excerpt: str


def label_deal(
    deal_id: str,
    target_name: str,
    documents: list[tuple[str, str]],
) -> DealAiLabel:
    """Label one deal from its retrieved document bodies.

    ``documents`` is a list of ``(source_url, text)`` pairs. The strongest evidence across the
    deal's documents wins, so a press release describing the target as an AI company counts even
    when the agreement itself never uses the word.
    """
    best_weight = 0
    best_terms: tuple[str, ...] = ()
    best_excerpt = ""
    best_url = ""
    join = acquihire = license_hire = False
    talent_excerpt = ""

    for url, text in documents:
        if not text:
            continue
        result = screen_ai_text_for_target(text, target_name)
        if result.total_weight > best_weight:
            best_weight = result.total_weight
            best_terms = result.distinct_terms
            best_excerpt = result.best_excerpt
            best_url = url
        signals = detect_talent_signals(text)
        join = join or signals.join_language
        acquihire = acquihire or signals.acquihire_explicit
        license_hire = license_hire or signals.license_and_hire_explicit
        if not talent_excerpt and signals.join_excerpts:
            talent_excerpt = signals.join_excerpts[0]

    if best_weight >= _EXPLICIT_WEIGHT:
        label = "ai_explicit"
    elif best_weight >= _ADJACENT_WEIGHT:
        label = "ai_adjacent"
    else:
        label = "none"

    return DealAiLabel(
        deal_id=deal_id,
        label=label,
        weight=best_weight,
        terms=best_terms,
        excerpt=best_excerpt,
        source_url=best_url,
        documents_screened=len(documents),
        join_language=join,
        acquihire_explicit=acquihire,
        license_and_hire_explicit=license_hire,
        talent_excerpt=talent_excerpt,
    )


def label_row(label: DealAiLabel, acquirer_name: str, target_name: str) -> dict[str, str]:
    highlight = text_fragment_url(label.source_url, label.excerpt) if label.excerpt else ""
    return {
        "deal_id": label.deal_id,
        "acquirer_name": acquirer_name,
        "target_name": target_name,
        "ai_label": label.label,
        "ai_evidence_weight": str(label.weight),
        "ai_terms": "; ".join(label.terms),
        "ai_excerpt": label.excerpt,
        "ai_source_url": label.source_url,
        "ai_source_highlight_url": highlight,
        "talent_join_language": "yes" if label.join_language else "no",
        "talent_acquihire_explicit": "yes" if label.acquihire_explicit else "no",
        "talent_license_and_hire_explicit": "yes" if label.license_and_hire_explicit else "no",
        "talent_excerpt": label.talent_excerpt,
        "documents_screened": str(label.documents_screened),
        "review_status": _REVIEW_STATUS,
    }


def write_deal_ai_labels(
    output_dir: Path, rows: list[dict[str, str]], manifest: dict[str, object]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "deal_ai_labels.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=AI_LABEL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "ai_label_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
