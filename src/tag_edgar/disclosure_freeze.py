"""Freeze the modelled deal sample and record why every other deal fell out.

The sample the report describes must be a file, not an idea. This module reads the built corpus,
applies the yield gate, and writes one row per candidate deal with the reason it is in, out, or
present-but-empty. Downstream commands run against that frozen list so the funnel in the report
adds up and no deal disappears silently.

A deal with no employee passages is kept as a ``zero_yield`` row rather than deleted. Absence of
employee language in a filed agreement is an observation about disclosure; it is not evidence
that the transaction lacked employee arrangements.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .disclosure_pool import DisclosurePoolConfig

__all__ = [
    "FROZEN_FIELDS",
    "FrozenSample",
    "build_frozen_sample",
    "write_frozen_sample",
]

FROZEN_FIELDS = [
    "deal_id",
    "acquirer_name",
    "target_name",
    "announcement_date",
    "effective_date",
    "transaction_value_mil",
    "target_public_status",
    "probe_status",
    "agreement_exhibit_types",
    "target_name_hit",
    "cik_confirmation_basis",
    "documents_retrieved",
    "included_passages",
    "source_documents_with_passages",
    "sample_status",
    "sample_reason",
]

_MODELLED = "modelled"
_ZERO_YIELD = "zero_yield_reported_not_modelled"
_BELOW_GATE = "below_yield_gate"
_NOT_RETRIEVED = "not_retrieved"


@dataclass(frozen=True)
class FrozenSample:
    rows: tuple[dict[str, str], ...]
    manifest: dict[str, object]

    @property
    def modelled_deal_ids(self) -> tuple[str, ...]:
        return tuple(row["deal_id"] for row in self.rows if row["sample_status"] == _MODELLED)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(file)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_frozen_sample(
    queue_csv: Path,
    passages_csv: Path,
    runs_dir: Path,
    config: DisclosurePoolConfig,
    *,
    probe_csv: Path | None = None,
) -> FrozenSample:
    """Apply the yield gate to every queued deal and record the outcome for each."""
    queue = _read(queue_csv)
    probe_by_deal = {row["deal_id"]: row for row in _read(probe_csv)} if probe_csv else {}

    passage_counts: Counter[str] = Counter()
    documents_with_passages: defaultdict[str, set[str]] = defaultdict(set)
    for row in _read(passages_csv):
        if row.get("inclusion_status", "") != "included":
            continue
        deal_id = row.get("deal_id", "")
        passage_counts[deal_id] += 1
        documents_with_passages[deal_id].add(
            row.get("source_document_family_id") or row.get("document_id", "")
        )

    rows: list[dict[str, str]] = []
    for entry in queue:
        deal_id = entry["deal_id"]
        probe = probe_by_deal.get(deal_id, {})
        documents_csv = runs_dir / deal_id / "documents.csv"
        retrieved = len(_read(documents_csv)) if documents_csv.exists() else 0
        included = passage_counts.get(deal_id, 0)
        sources = len(documents_with_passages.get(deal_id, ()))

        if retrieved == 0:
            status, reason = _NOT_RETRIEVED, "no documents retrieved for this deal"
        elif included == 0:
            status, reason = (
                _ZERO_YIELD,
                "documents retrieved but no passage passed the employee screen",
            )
        elif included < config.minimum_passages or sources < config.minimum_documents:
            gate = (
                f"{config.minimum_passages} passages from {config.minimum_documents} documents"
            )
            status, reason = (
                _BELOW_GATE,
                f"{included} passages from {sources} source documents is below the gate ({gate})",
            )
        else:
            status, reason = _MODELLED, "meets the prespecified yield gate"

        rows.append(
            {
                "deal_id": deal_id,
                "acquirer_name": entry.get("acquirer_name", ""),
                "target_name": entry.get("target_name", ""),
                "announcement_date": entry.get("announcement_date", ""),
                "effective_date": entry.get("effective_date", ""),
                "transaction_value_mil": entry.get("transaction_value_mil", ""),
                "target_public_status": entry.get("target_public_status", ""),
                "probe_status": probe.get("probe_status", ""),
                "agreement_exhibit_types": probe.get("agreement_exhibit_types", ""),
                "target_name_hit": probe.get("target_name_hit", ""),
                "cik_confirmation_basis": entry.get("cik_match_method", ""),
                "documents_retrieved": str(retrieved),
                "included_passages": str(included),
                "source_documents_with_passages": str(sources),
                "sample_status": status,
                "sample_reason": reason,
            }
        )

    rows.sort(key=lambda row: (-int(row["included_passages"]), row["deal_id"]))
    status_counts = Counter(row["sample_status"] for row in rows)
    modelled = [row for row in rows if row["sample_status"] == _MODELLED]
    manifest: dict[str, object] = {
        "schema_version": 1,
        "pool_rule_version": config.version,
        "queue_csv_sha256": _sha256(queue_csv),
        "passages_csv_sha256": _sha256(passages_csv),
        "yield_gate": {
            "minimum_passages": config.minimum_passages,
            "minimum_source_documents": config.minimum_documents,
        },
        "queued_deals": len(rows),
        "status_counts": dict(status_counts),
        "modelled_deals": len(modelled),
        "modelled_passages": sum(int(row["included_passages"]) for row in modelled),
        "largest_deal_share": (
            round(
                max((int(row["included_passages"]) for row in modelled), default=0)
                / max(sum(int(row["included_passages"]) for row in modelled), 1),
                4,
            )
        ),
        "evidence_boundary": (
            "zero_yield rows record that no employee passage survived the screen in the retrieved "
            "documents; that is a disclosure observation, not evidence that the transaction "
            "lacked employee arrangements"
        ),
    }
    return FrozenSample(tuple(rows), manifest)


def write_frozen_sample(output_dir: Path, sample: FrozenSample) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "frozen_sample.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FROZEN_FIELDS)
        writer.writeheader()
        writer.writerows(sample.rows)
    (output_dir / "frozen_sample_manifest.json").write_text(
        json.dumps(sample.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
