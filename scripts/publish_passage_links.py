"""Publish the passage-level table with clickable SEC deep links.

Every count in the report is an aggregate over passages, and until now the passage table lived
only in the git-ignored `data/derived/`. In the 2026-09-03 advisor meeting four minutes went to
hunting for it and it was never found, so no claim in the report could be checked against the
filing text behind it. That is the gap this closes.

`source_highlight_url` is a `#:~:text=` fragment URL: opening it in a supporting browser scrolls
the SEC document to the passage and highlights it. The canonical `source_url` is kept beside it
because a fragment can fail to match after whitespace drift, and a link that always resolves to
the right document is worth more than a highlight that sometimes does not.

Two files are written because they answer two different needs:

- `08_passage_links.csv.gz` is the complete table, all included passages. It is gzipped because
  the uncompressed table is far past the size a repository should carry, and gzip keeps it one
  checkable artifact rather than a sharded one.
- `08_passage_links_sample.csv` is the highest-weight passages per deal and topic, uncompressed
  and small enough to open directly. This is the file to open in a meeting.

Usage:
    python scripts/publish_passage_links.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERIVED = PROJECT_ROOT / "data" / "derived"

csv.field_size_limit(2**31 - 1)

#: Enough of the passage to recognise it, not so much that the table becomes the corpus.
QUOTE_CHARS = 400

#: The frozen-sample status that means the model actually fitted on the deal.
MODELLED_STATUS = "modelled"

#: Highest-weight primary passages kept per deal and topic in the openable sample.
SAMPLE_PER_DEAL_TOPIC = 3

FIELDS = (
    "deal_id",
    "acquirer_name",
    "target_name",
    "topic_id",
    "topic_weight",
    "primary_topic",
    "document_type",
    "accession_number",
    "heading",
    "quote",
    "source_url",
    "source_highlight_url",
    "highlight_status",
    "passage_id",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clip(text: str, limit: int = QUOTE_CHARS) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def build_rows(
    assignments_csv: Path, passages_csv: Path, frozen_sample_csv: Path
) -> list[dict[str, str]]:
    """Join topic assignments to passage text and deal names, restricted to the frozen sample.

    The report's sample is the frozen deal list, so a passage from a retrieved-but-not-selected
    deal has no place in a table that is meant to back the report's numbers.
    """
    # "modelled" is the frozen sample the report describes. The other statuses were retrieved
    # and are reported in the funnel, but the model never saw them, so their passages must not
    # appear in a table that backs the model's numbers.
    names = {
        row["deal_id"]: (row.get("acquirer_name", ""), row.get("target_name", ""))
        for row in _read(frozen_sample_csv)
        if row.get("sample_status", "").strip() == MODELLED_STATUS
    }
    passages = {row["passage_id"]: row for row in _read(passages_csv)}

    rows: list[dict[str, str]] = []
    for assignment in _read(assignments_csv):
        deal_id = assignment.get("deal_id", "")
        if deal_id not in names:
            continue
        # One row per passage, carrying the topic that best explains it. The full weight
        # vector over all topics is the deal_topic_matrix's job, not this table's.
        if assignment.get("primary_topic", "").strip().lower() != "true":
            continue
        passage = passages.get(assignment["passage_id"])
        if passage is None:
            continue
        acquirer, target = names[deal_id]
        highlight = passage.get("source_highlight_url", "")
        rows.append(
            {
                "deal_id": deal_id,
                "acquirer_name": acquirer,
                "target_name": target,
                "topic_id": assignment.get("topic_id", ""),
                "topic_weight": assignment.get("topic_weight", ""),
                "primary_topic": assignment.get("primary_topic", ""),
                "document_type": passage.get("document_type", ""),
                "accession_number": passage.get("accession_number", ""),
                "heading": _clip(passage.get("heading", ""), 120),
                "quote": _clip(passage.get("text", "")),
                "source_url": passage.get("source_url", ""),
                "source_highlight_url": highlight,
                # A reader deserves to know when a deep link was not available, rather than
                # finding an empty cell and guessing why.
                "highlight_status": "ok" if highlight else "unavailable",
                "passage_id": assignment["passage_id"],
            }
        )
    rows.sort(key=lambda row: (row["deal_id"], row["topic_id"], row["passage_id"]))
    return rows


def sample_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """The highest-weight primary passages for each deal and topic."""
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["primary_topic"].strip().lower() != "true":
            continue
        grouped[(row["deal_id"], row["topic_id"])].append(row)

    selected: list[dict[str, str]] = []
    for key in sorted(grouped):
        ranked = sorted(
            grouped[key],
            key=lambda row: (-_weight(row["topic_weight"]), row["passage_id"]),
        )
        selected.extend(ranked[:SAMPLE_PER_DEAL_TOPIC])
    return selected


def _weight(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def _write_csv_gz(path: Path, rows: list[dict[str, str]]) -> None:
    # mtime=0 keeps the gzip header byte-identical between runs on identical input, so a
    # re-publish that changes nothing produces no diff.
    # TextIOWrapper, not open(raw.fileno()): the latter writes to the underlying descriptor and
    # bypasses the compressor, producing a file with a gzip header and plain CSV behind it.
    with (
        gzip.GzipFile(path, "wb", mtime=0) as raw,
        io.TextIOWrapper(raw, newline="", encoding="utf-8") as file,
    ):
        writer = csv.DictWriter(file, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip())
    parser.add_argument("--topics-dir", type=Path, default=DERIVED / "employee_topics_100")
    parser.add_argument("--corpus-dir", type=Path, default=DERIVED / "employee_corpus_100")
    parser.add_argument(
        "--frozen-sample",
        type=Path,
        default=DERIVED / "disclosure_frozen_sample" / "frozen_sample.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "published" / "disclosure_sample_133",
    )
    args = parser.parse_args(argv[1:])

    assignments = args.topics_dir / "canonical_topic_assignments.csv"
    passages = args.corpus_dir / "passages.csv"
    missing = [
        str(path) for path in (assignments, passages, args.frozen_sample) if not path.exists()
    ]
    if missing:
        print("Missing inputs; run the analysis first:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1

    rows = build_rows(assignments, passages, args.frozen_sample)
    if not rows:
        print(
            "No passages joined to the frozen sample; refusing to publish an empty table.",
            file=sys.stderr,
        )
        return 1
    sample = sample_rows(rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    full_path = args.output_dir / "08_passage_links.csv.gz"
    sample_path = args.output_dir / "08_passage_links_sample.csv"
    _write_csv_gz(full_path, rows)
    _write_csv(sample_path, sample)

    with_link = sum(1 for row in rows if row["highlight_status"] == "ok")
    manifest = {
        "schema_version": 1,
        "written": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "passage_rows": len(rows),
        "row_rule": "one row per included passage, carrying its primary topic",
        "distinct_passages": len({row["passage_id"] for row in rows}),
        "distinct_deals": len({row["deal_id"] for row in rows}),
        "rows_with_highlight_link": with_link,
        "highlight_link_coverage": round(with_link / len(rows), 6),
        "sample_rows": len(sample),
        "sample_rule": f"top {SAMPLE_PER_DEAL_TOPIC} primary passages per deal and topic by weight",
        "quote_chars": QUOTE_CHARS,
        "files": {
            "08_passage_links.csv.gz": {
                "bytes": full_path.stat().st_size,
                "sha256": _sha256(full_path),
            },
            "08_passage_links_sample.csv": {
                "bytes": sample_path.stat().st_size,
                "sha256": _sha256(sample_path),
            },
        },
        "evidence_boundary": (
            "Quotes are filing text as retrieved. A highlight link locates a passage; it does "
            "not certify that the passage supports any claim made about it."
        ),
    }
    (args.output_dir / "08_passage_links_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Rows: {len(rows)} passages across {manifest['distinct_deals']} deals")
    print(f"Highlight links: {with_link} ({manifest['highlight_link_coverage']:.1%})")
    print(f"Full   {full_path} ({full_path.stat().st_size // 1024} KB)")
    print(f"Sample {sample_path} ({sample_path.stat().st_size // 1024} KB, {len(sample)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
