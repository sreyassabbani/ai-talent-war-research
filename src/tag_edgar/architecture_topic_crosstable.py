"""Provisional cross-table joining deal architecture to deal-level topic weights.

This is a descriptive join of two separately produced layers: the rule-coded transaction
attributes (``deal_architecture.csv``, pending human review) and the deal-topic matrix from the
unsupervised employee-language model (``deal_topic_matrix.csv``). With ten deals it can only
describe patterns. It performs no inference, no significance testing, and no outcome claims, and
it carries the validation label of every input forward so a reader cannot mistake it for a result.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .corpus_validation import CorpusValidationState
from .source_links import text_fragment_url
from .storage import write_dict_csv

__all__ = ["CROSSTABLE_FIELDS", "CrossTable", "build_crosstable", "write_crosstable"]

CROSSTABLE_FIELDS = [
    "deal_id",
    "deal_name",
    "legal_transaction_form",
    "scope_and_control",
    "workforce_movement",
    "talent_motive_explicit",
    "machine_suggested_archetypes",
    "archetype_ambiguity",
    "architecture_review_status",
    "topic_id",
    "normalized_weight",
    "primary_passage_count",
    "zero_state",
    "example_passage_id",
    "example_source_url",
    "example_source_highlight_url",
    "corpus_validation_status",
    "interpretation",
]

_INTERPRETATION = (
    "exploratory description of ten deals; not a population estimate, not causal, "
    "and not an employee outcome"
)


@dataclass(frozen=True)
class CrossTable:
    rows: tuple[dict[str, str], ...]
    manifest: dict[str, object]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(file)]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_crosstable(
    architecture_csv: Path,
    deal_topic_matrix_csv: Path,
    topic_assignments_csv: Path | None,
    corpus_validation: CorpusValidationState,
) -> CrossTable:
    """Join one architecture row per deal to every (deal, topic) weight row.

    Deals present in the architecture layer but absent from the topic matrix are kept with an
    explicit ``zero_state`` so unknown or zero-passage cases stay visible. Each topic cell carries
    the highest-weight primary passage for that deal and topic as a source-linked example.
    """
    architecture = {row["deal_id"]: row for row in _read(architecture_csv)}
    if not architecture:
        raise ValueError("deal_architecture.csv contains no deals.")
    topic_rows = _read(deal_topic_matrix_csv)
    by_deal: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in topic_rows:
        by_deal[row["deal_id"]].append(row)

    examples: dict[tuple[str, str], dict[str, str]] = {}
    if topic_assignments_csv is not None and topic_assignments_csv.exists():
        for row in _read(topic_assignments_csv):
            if row.get("primary_topic", "").lower() not in {"true", "1", "yes"}:
                continue
            key = (row["deal_id"], row["topic_id"])
            weight = float(row.get("topic_weight") or 0.0)
            current = examples.get(key)
            if current is None or weight > float(current.get("topic_weight") or 0.0):
                examples[key] = row

    output: list[dict[str, str]] = []
    unmatched_topic_deals = sorted(set(by_deal) - set(architecture))
    for deal_id in sorted(architecture):
        arch = architecture[deal_id]
        base = {
            "deal_id": deal_id,
            "deal_name": arch.get("deal_name", ""),
            "legal_transaction_form": arch.get("legal_transaction_form", ""),
            "scope_and_control": arch.get("scope_and_control", ""),
            "workforce_movement": arch.get("workforce_movement", ""),
            "talent_motive_explicit": arch.get("talent_motive_explicit", ""),
            "machine_suggested_archetypes": arch.get("machine_suggested_archetypes", ""),
            "archetype_ambiguity": arch.get("archetype_ambiguity", ""),
            "architecture_review_status": arch.get("review_status", ""),
            "corpus_validation_status": corpus_validation.status,
            "interpretation": _INTERPRETATION,
        }
        cells = sorted(by_deal.get(deal_id, ()), key=lambda row: row["topic_id"])
        if not cells:
            output.append(
                {
                    **base,
                    "topic_id": "",
                    "normalized_weight": "",
                    "primary_passage_count": "0",
                    "zero_state": "deal_absent_from_topic_matrix",
                    "example_passage_id": "",
                    "example_source_url": "",
                    "example_source_highlight_url": "",
                }
            )
            continue
        for cell in cells:
            example = examples.get((deal_id, cell["topic_id"]), {})
            highlight = example.get("source_highlight_url", "") or text_fragment_url(
                example.get("source_url", ""), example.get("text", "")
            )
            output.append(
                {
                    **base,
                    "topic_id": cell["topic_id"],
                    "normalized_weight": cell.get("normalized_weight", ""),
                    "primary_passage_count": cell.get("primary_passage_count", ""),
                    "zero_state": cell.get("zero_state", ""),
                    "example_passage_id": example.get("passage_id", ""),
                    "example_source_url": example.get("source_url", ""),
                    "example_source_highlight_url": highlight,
                }
            )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "deal_count": len(architecture),
        "row_count": len(output),
        "deals_without_topic_rows": [
            deal_id for deal_id in sorted(architecture) if not by_deal.get(deal_id)
        ],
        "topic_deals_without_architecture": unmatched_topic_deals,
        "architecture_review_status": sorted(
            {row.get("review_status", "") for row in architecture.values()}
        ),
        "corpus_validation": corpus_validation.as_manifest(),
        "architecture_csv_sha256": _sha(architecture_csv),
        "deal_topic_matrix_sha256": _sha(deal_topic_matrix_csv),
        "topic_assignments_sha256": (
            _sha(topic_assignments_csv)
            if topic_assignments_csv is not None and topic_assignments_csv.exists()
            else ""
        ),
        "interpretation": _INTERPRETATION,
    }
    return CrossTable(tuple(output), manifest)


def write_crosstable(output_dir: Path, table: CrossTable) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dict_csv(
        output_dir / "architecture_topic_crosstable.csv", table.rows, CROSSTABLE_FIELDS
    )
    (output_dir / "crosstable_manifest.json").write_text(
        json.dumps(table.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
