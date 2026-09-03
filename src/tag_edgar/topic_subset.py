"""Build a corpus restricted to one parent topic, so the topic can be modelled again.

The 133-deal model found three broad themes. A theme is not an answer on its own: "stock and
equity awards" covers accelerated vesting, plan assumption, cash-out, and rollover, and those are
different promises to different people. Answering what sits inside a theme means fitting the model
again on that theme's passages alone.

Why a corpus subset rather than a ``--restrict-to-topic`` flag inside the fitter: the analysis
pipeline already computes leave-one-deal-out stability, bootstrap replicates, fit-balance
sensitivity, and an independent embedding cross-check. Restricting the *input* and re-running that
pipeline unchanged means a second-level diagnostic means exactly what a first-level diagnostic
means. A flag threaded through the fitter would fork the code path that produces the numbers we
report, and every comparison between levels would then rest on the claim that the two paths agree.

Selection uses ``primary_topic``: a passage joins the sub-corpus of the single topic that best
explains it, so the three sub-corpora partition the parent corpus and no passage is modelled
twice. Passages are already deduplicated by ``duplicate_group`` upstream -- each canonical passage
is the only included row of its group -- so restricting to canonical passage IDs leaves the
deduplication structure intact and the second fit sees one row per distinct passage, as the first
did.

Source occurrences are carried across for every retained passage. Deal-level attribution in the
sub-model is then computed from the same occurrence rows the parent model used, not from a
narrowed subset that would silently drop deals.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "TopicSubsetResult",
    "build_topic_subset_corpus",
    "read_primary_passage_ids",
]

# SEC passages routinely exceed the default field limit, and a truncated read would silently drop
# text rather than fail. Raise it once, at import, for every reader in this module.
csv.field_size_limit(2**31 - 1)

_INCLUDED = "included"


@dataclass(frozen=True)
class TopicSubsetResult:
    """What the subset contains, and what it was cut from."""

    parent_topic_id: str
    output_dir: Path
    passage_count: int
    source_occurrence_count: int
    deal_count: int
    parent_passage_count: int
    document_type_counts: dict[str, int] = field(default_factory=dict)
    excluded_document_types: tuple[str, ...] = ()
    excluded_document_type_count: int = 0

    @property
    def share_of_parent(self) -> float:
        if self.parent_passage_count == 0:
            return 0.0
        return self.passage_count / self.parent_passage_count


def _read_rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        yield from csv.DictReader(file)


def _fieldnames(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file).fieldnames or ())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_primary_passage_ids(assignments_csv: Path, parent_topic_id: str) -> frozenset[str]:
    """Passage IDs whose best-explaining topic is ``parent_topic_id``.

    Raises when the topic is absent, because an empty subset caused by a typo is
    indistinguishable from an empty subset that is a real result, and only one of those
    should be allowed to pass quietly.
    """
    seen_topics: set[str] = set()
    selected: set[str] = set()
    for row in _read_rows(assignments_csv):
        topic = row.get("topic_id", "").strip()
        seen_topics.add(topic)
        if topic == parent_topic_id and row.get("primary_topic", "").strip().lower() == "true":
            selected.add(row["passage_id"])
    if parent_topic_id not in seen_topics:
        known = ", ".join(sorted(seen_topics))
        raise ValueError(f"Topic {parent_topic_id!r} is not in the assignments. Found: {known}")
    return frozenset(selected)


def build_topic_subset_corpus(
    assignments_csv: Path,
    corpus_dir: Path,
    output_dir: Path,
    *,
    parent_topic_id: str,
    parent_topics_dir: Path | None = None,
    exclude_document_type_prefixes: Sequence[str] = (),
) -> TopicSubsetResult:
    """Write a corpus directory holding only the passages a parent topic best explains.

    The output is a drop-in ``corpus_dir`` for ``analyze-employee-topics``: it carries
    ``passages.csv`` and ``passage_sources.csv`` with the same columns as the source corpus,
    plus a manifest recording the parent topic and the hashes of the inputs it was cut from.

    ``exclude_document_type_prefixes`` drops passages by document type before fitting, which is
    how a "does this theme survive without X" sensitivity check is run. Prefix matching is
    case-insensitive, so ``EX-99`` covers ``EX-99.1``, ``EX-99.2``, and the rest of the family.
    The count of dropped passages is recorded in the manifest, because a sensitivity result is
    unreadable without knowing how much was removed to produce it.
    """
    passages_path = corpus_dir / "passages.csv"
    sources_path = corpus_dir / "passage_sources.csv"
    for path in (assignments_csv, passages_path, sources_path):
        if not path.exists():
            raise FileNotFoundError(f"Required input is missing: {path}")

    selected = read_primary_passage_ids(assignments_csv, parent_topic_id)
    if not selected:
        raise ValueError(f"Topic {parent_topic_id!r} has no primary passages to model.")

    output_dir.mkdir(parents=True, exist_ok=True)

    prefixes = tuple(
        prefix.strip().upper() for prefix in exclude_document_type_prefixes if prefix.strip()
    )

    passage_fields = _fieldnames(passages_path)
    kept_passages: list[dict[str, str]] = []
    parent_included = 0
    excluded_by_type = 0
    document_types: dict[str, int] = {}
    deals: set[str] = set()
    seen_ids: set[str] = set()
    for row in _read_rows(passages_path):
        if row.get("inclusion_status", "").strip().lower() == _INCLUDED:
            parent_included += 1
        if row["passage_id"] not in selected:
            continue
        seen_ids.add(row["passage_id"])
        if prefixes and (row.get("document_type", "") or "").strip().upper().startswith(prefixes):
            excluded_by_type += 1
            continue
        kept_passages.append(row)
        deals.add(row.get("deal_id", ""))
        document_type = row.get("document_type", "") or "unknown"
        document_types[document_type] = document_types.get(document_type, 0) + 1

    kept_ids = {row["passage_id"] for row in kept_passages}
    # Checked against what the corpus contained, not what survived the type filter: a passage
    # dropped for its document type was still found, and only a passage that was never there at
    # all means the assignments and the corpus came from different runs.
    missing = selected - seen_ids
    if missing:
        # The assignments must describe the corpus they were fitted on. A gap means the two
        # inputs came from different runs, which would produce a quietly wrong sub-model.
        sample = ", ".join(sorted(missing)[:3])
        raise ValueError(
            f"{len(missing)} assigned passages are absent from {passages_path.name} "
            f"(for example {sample}). The assignments and corpus are from different runs."
        )

    _write_rows(output_dir / "passages.csv", passage_fields, kept_passages)

    source_fields = _fieldnames(sources_path)
    kept_sources = [row for row in _read_rows(sources_path) if row["passage_id"] in kept_ids]
    _write_rows(output_dir / "passage_sources.csv", source_fields, kept_sources)

    result = TopicSubsetResult(
        parent_topic_id=parent_topic_id,
        output_dir=output_dir,
        passage_count=len(kept_passages),
        source_occurrence_count=len(kept_sources),
        deal_count=len({deal for deal in deals if deal}),
        parent_passage_count=parent_included,
        document_type_counts=dict(
            sorted(document_types.items(), key=lambda item: (-item[1], item[0]))
        ),
        excluded_document_types=prefixes,
        excluded_document_type_count=excluded_by_type,
    )
    _write_manifest(
        output_dir, result, assignments_csv, passages_path, sources_path, parent_topics_dir
    )
    return result


def _write_rows(path: Path, fields: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def _write_manifest(
    output_dir: Path,
    result: TopicSubsetResult,
    assignments_csv: Path,
    passages_path: Path,
    sources_path: Path,
    parent_topics_dir: Path | None,
) -> None:
    manifest = {
        "schema_version": 1,
        "written": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "parent_topic_id": result.parent_topic_id,
        "parent_topics_dir": str(parent_topics_dir) if parent_topics_dir else None,
        "selection_rule": "primary_topic == true for the parent topic",
        "passage_count": result.passage_count,
        "source_occurrence_count": result.source_occurrence_count,
        "deal_count": result.deal_count,
        "parent_included_passage_count": result.parent_passage_count,
        "share_of_parent_corpus": round(result.share_of_parent, 6),
        "document_type_counts": result.document_type_counts,
        "excluded_document_type_prefixes": list(result.excluded_document_types),
        "excluded_by_document_type": result.excluded_document_type_count,
        "inputs": {
            "assignments_csv": {
                "path": str(assignments_csv),
                "sha256": _sha256(assignments_csv),
            },
            "passages_csv": {"path": str(passages_path), "sha256": _sha256(passages_path)},
            "passage_sources_csv": {"path": str(sources_path), "sha256": _sha256(sources_path)},
        },
        "evidence_boundary": (
            "A second-level topic describes how a first-level theme's language divides. It is "
            "not a validated category, and it inherits every selection property of the parent "
            "corpus, including that the sample is chosen by whether a buyer filed with the SEC."
        ),
    }
    (output_dir / "subset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
