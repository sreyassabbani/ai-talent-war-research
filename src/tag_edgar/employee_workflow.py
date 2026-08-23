from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from .accessions import canonical_document_url
from .employee_corpus import CorpusDocument, build_employee_corpus, parse_document
from .employee_report import build_employee_report, write_employee_report
from .employee_topics import (
    AssignmentRow,
    EmployeeTopicResult,
    TopicModelConfig,
    analyze_employee_topics_csv,
)

PASSAGE_FIELDS = [
    "passage_id",
    "canonical_passage_id",
    "deal_id",
    "document_id",
    "document_family_id",
    "source_document_family_id",
    "accession_number",
    "document_type",
    "source_url",
    "heading",
    "block_start",
    "block_end",
    "char_start",
    "char_end",
    "text",
    "raw_text",
    "model_text",
    "token_count",
    "screen_terms",
    "content_sha256",
    "duplicate_group",
    "duplicate_group_id",
    "occurrence_count",
    "inclusion_status",
]

PASSAGE_SOURCE_FIELDS = [
    "occurrence_id",
    "passage_id",
    "deal_id",
    "document_id",
    "document_family_id",
    "source_document_family_id",
    "accession_number",
    "document_type",
    "source_url",
    "heading",
    "block_start",
    "block_end",
    "char_start",
    "char_end",
]

DOCUMENT_FIELDS = [
    "deal_id",
    "document_id",
    "source_document_family_id",
    "accession_number",
    "document_type",
    "description",
    "document_name",
    "url",
    "is_primary",
]

DOCUMENT_TEXT_FIELDS = [
    "deal_id",
    "document_id",
    "source_document_family_id",
    "source_url",
    "source_sha256",
    "text_sha256",
    "block_count",
    "extraction_status",
    "extraction_error",
]

TOPIC_ASSIGNMENT_FIELDS = [
    "passage_id",
    "canonical_passage_id",
    "deal_id",
    "document_id",
    "document_family_id",
    "source_url",
    "topic_id",
    "topic_weight",
    "primary_topic",
    "top_terms",
    "method",
    "coherence",
    "stability_recovery_rate",
]

TOPIC_SUMMARY_FIELDS = [
    "topic_id",
    "top_terms",
    "primary_passage_count",
    "document_family_count",
    "deal_count",
    "coherence",
    "stability_median_cosine",
    "stability_recovery_rate",
]

DEAL_TOPIC_FIELDS = [
    "deal_id",
    "acquirer_name",
    "target_name",
    "topic_id",
    "weight_sum",
    "normalized_weight",
    "primary_passage_count",
    "zero_state",
]

DIAGNOSTIC_FIELDS = ["stage", "name", "value", "status", "detail"]
SENSITIVITY_FIELDS = ["passage_id", "deal_id", "cluster_id"]
STABILITY_FIELDS = [
    "left_out_deal_id",
    "topic_id",
    "aligned_topic_id",
    "cosine_similarity",
    "recovered",
]


@dataclass(frozen=True)
class WorkflowSummary:
    status: str
    output_dir: Path
    counts: dict[str, int]


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(file)
        ]


def _write_rows(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(materialized)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selected_deals(review_csv: Path) -> list[dict[str, str]]:
    rows = [row for row in _read_rows(review_csv) if row.get("pilot_status", "").lower() == "selected"]
    if not rows:
        raise ValueError("Review CSV has no rows with pilot_status=selected.")
    missing = [index for index, row in enumerate(rows, start=2) if not row.get("deal_id")]
    if missing:
        raise ValueError(f"Selected review rows have blank deal_id values at rows {missing}.")
    counts = Counter(row["deal_id"] for row in rows)
    duplicates = sorted(deal_id for deal_id, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Review CSV has duplicate selected deal IDs: {duplicates}")
    return sorted(rows, key=lambda row: row["deal_id"])


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _relevant_document(row: Mapping[str, str]) -> bool:
    document_type = row.get("document_type", "").upper()
    return _truthy(row.get("is_primary", "")) or document_type.startswith(
        ("EX-2.", "EX-10.", "EX-99.")
    )


def _document_family_id(deal_id: str, row: Mapping[str, str]) -> str:
    family_seed = ":".join(
        (
            deal_id,
            row.get("document_type", "").strip().upper() or "UNKNOWN",
            " ".join(row.get("description", "").casefold().split()),
        )
    )
    return f"family_{hashlib.sha256(family_seed.encode()).hexdigest()[:16]}"


_MODEL_TOKEN = re.compile(r"[a-z][a-z0-9]*(?:[-'][a-z0-9]+)*")


def _provision_shingles(model_text: str) -> frozenset[str]:
    tokens = _MODEL_TOKEN.findall(model_text.casefold())
    if len(tokens) < 3:
        return frozenset(tokens)
    return frozenset(" ".join(tokens[index : index + 3]) for index in range(len(tokens) - 2))


def _minhash(shingles: frozenset[str], permutations: int = 12) -> tuple[int, ...]:
    if not shingles:
        return tuple(0 for _ in range(permutations))
    return tuple(
        min(
            int.from_bytes(
                hashlib.sha256(f"{permutation}:{shingle}".encode()).digest()[:8], "big"
            )
            for shingle in shingles
        )
        for permutation in range(permutations)
    )


def _provision_family_ids(passages: Sequence[Mapping[str, object]]) -> dict[str, str]:
    """Group normalized near-duplicate provisions without pairwise all-corpus comparison."""
    passage_ids = [str(row["passage_id"]) for row in passages]
    shingles = {
        str(row["passage_id"]): _provision_shingles(str(row["model_text"])) for row in passages
    }
    parents = {passage_id: passage_id for passage_id in passage_ids}

    def find(passage_id: str) -> str:
        while parents[passage_id] != passage_id:
            parents[passage_id] = parents[parents[passage_id]]
            passage_id = parents[passage_id]
        return passage_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        lower, higher = sorted((left_root, right_root))
        parents[higher] = lower

    buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)
    for passage_id in sorted(passage_ids):
        signature = _minhash(shingles[passage_id])
        for band in range(3):
            buckets[(band, signature[band * 4 : (band + 1) * 4])].append(passage_id)

    compared: set[tuple[str, str]] = set()
    for bucket in buckets.values():
        for left_index, left in enumerate(bucket):
            for right in bucket[left_index + 1 :]:
                pair = (left, right)
                if pair in compared:
                    continue
                compared.add(pair)
                left_shingles = shingles[left]
                right_shingles = shingles[right]
                larger = max(len(left_shingles), len(right_shingles))
                if not larger or min(len(left_shingles), len(right_shingles)) / larger < 0.7:
                    continue
                similarity = len(left_shingles & right_shingles) / len(
                    left_shingles | right_shingles
                )
                if similarity >= 0.72:
                    union(left, right)

    members: defaultdict[str, list[str]] = defaultdict(list)
    for passage_id in passage_ids:
        members[find(passage_id)].append(passage_id)
    family_ids: dict[str, str] = {}
    for group in members.values():
        family_seed = ":".join(sorted(group))
        family_id = f"provision_{hashlib.sha256(family_seed.encode()).hexdigest()[:16]}"
        for passage_id in group:
            family_ids[passage_id] = family_id
    return family_ids


def _cache_paths(cache_dir: Path, url: str) -> tuple[Path, Path]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.body", cache_dir / f"{digest}.json"


def _cache_content_type(metadata_path: Path) -> str:
    if not metadata_path.exists():
        return ""
    value = json.loads(metadata_path.read_text(encoding="utf-8"))
    return str(value.get("content_type", "")) if isinstance(value, dict) else ""


def build_employee_corpus_workflow(
    review_csv: Path,
    runs_dir: Path,
    output_dir: Path,
    cache_dir: Path,
    *,
    context_blocks: int = 1,
    max_block_words: int = 220,
) -> WorkflowSummary:
    """Build the source-linked passage corpus entirely from reviewed runs and cached bodies."""
    deals = _selected_deals(review_csv)
    corpus_documents: list[CorpusDocument] = []
    document_rows: dict[str, dict[str, object]] = {}
    document_text_rows: list[dict[str, object]] = []
    family_by_occurrence: dict[tuple[str, str], str] = {}

    for deal in deals:
        deal_id = deal["deal_id"]
        documents_path = runs_dir / deal_id / "documents.csv"
        if not documents_path.exists():
            continue
        for row in _read_rows(documents_path):
            if not _relevant_document(row):
                continue
            document_id = row.get("document_id", "")
            if not document_id or not row.get("url"):
                continue
            url = canonical_document_url("https://www.sec.gov/", row["url"])
            family_id = _document_family_id(deal_id, row)
            family_by_occurrence[(deal_id, document_id)] = family_id
            combined_row: dict[str, object] = {
                "deal_id": deal_id,
                "document_id": document_id,
                "source_document_family_id": family_id,
                "accession_number": row.get("accession_number", ""),
                "document_type": row.get("document_type", ""),
                "description": row.get("description", ""),
                "document_name": row.get("document_name", ""),
                "url": url,
                "is_primary": row.get("is_primary", ""),
            }
            prior = document_rows.get(document_id)
            if prior is not None and prior["url"] != url:
                raise ValueError(f"Document {document_id} has inconsistent source URLs across deals.")
            document_rows.setdefault(document_id, combined_row)

            body_path, metadata_path = _cache_paths(cache_dir, url)
            if not body_path.exists():
                document_text_rows.append(
                    {
                        "deal_id": deal_id,
                        "document_id": document_id,
                        "source_document_family_id": family_id,
                        "source_url": url,
                        "source_sha256": "",
                        "text_sha256": "",
                        "block_count": 0,
                        "extraction_status": "cache_missing",
                        "extraction_error": f"No cached body for {url}",
                    }
                )
                continue
            content = body_path.read_bytes()
            content_type = _cache_content_type(metadata_path)
            try:
                parsed = parse_document(
                    content,
                    content_type,
                    max_block_words=max_block_words,
                )
            except (UnicodeError, ValueError) as error:
                document_text_rows.append(
                    {
                        "deal_id": deal_id,
                        "document_id": document_id,
                        "source_document_family_id": family_id,
                        "source_url": url,
                        "source_sha256": hashlib.sha256(content).hexdigest(),
                        "text_sha256": "",
                        "block_count": 0,
                        "extraction_status": "parse_error",
                        "extraction_error": str(error),
                    }
                )
                continue
            document_text_rows.append(
                {
                    "deal_id": deal_id,
                    "document_id": document_id,
                    "source_document_family_id": family_id,
                    "source_url": url,
                    "source_sha256": parsed.source_sha256,
                    "text_sha256": parsed.text_sha256,
                    "block_count": len(parsed.blocks),
                    "extraction_status": "parsed",
                    "extraction_error": "",
                }
            )
            corpus_documents.append(
                CorpusDocument(
                    deal_id=deal_id,
                    document_id=document_id,
                    accession_number=row.get("accession_number", ""),
                    document_type=row.get("document_type", ""),
                    source_url=url,
                    content=content,
                    content_type=content_type,
                )
            )

    corpus = build_employee_corpus(
        corpus_documents,
        context_blocks=context_blocks,
        max_block_words=max_block_words,
    )
    passage_rows: list[dict[str, object]] = []
    for passage in corpus.passages:
        family_id = family_by_occurrence[(passage.deal_id, passage.document_id)]
        passage_rows.append(
            {
                "passage_id": passage.passage_id,
                "canonical_passage_id": passage.passage_id,
                "deal_id": passage.deal_id,
                "document_id": passage.document_id,
                "document_family_id": "",
                "source_document_family_id": family_id,
                "accession_number": passage.accession_number,
                "document_type": passage.document_type,
                "source_url": passage.source_url,
                "heading": passage.heading or "",
                "block_start": passage.block_start,
                "block_end": passage.block_end,
                "char_start": passage.char_start,
                "char_end": passage.char_end,
                "text": passage.text,
                "raw_text": passage.text,
                "model_text": passage.model_text,
                "token_count": passage.token_count,
                "screen_terms": "|".join(passage.screen_terms),
                "content_sha256": passage.content_sha256,
                "duplicate_group": passage.duplicate_group_id,
                "duplicate_group_id": passage.duplicate_group_id,
                "occurrence_count": passage.occurrence_count,
                "inclusion_status": "included",
            }
        )
    provision_family_by_passage = _provision_family_ids(passage_rows)
    for row in passage_rows:
        row["document_family_id"] = provision_family_by_passage[str(row["passage_id"])]

    source_rows: list[dict[str, object]] = []
    for occurrence in corpus.occurrences:
        source_rows.append(
            {
                **asdict(occurrence),
                "document_family_id": provision_family_by_passage[occurrence.passage_id],
                "source_document_family_id": family_by_occurrence[
                    (occurrence.deal_id, occurrence.document_id)
                ],
                "heading": occurrence.heading or "",
            }
        )

    documents_path = output_dir / "documents.csv"
    document_texts_path = output_dir / "document_texts.csv"
    passages_path = output_dir / "passages.csv"
    sources_path = output_dir / "passage_sources.csv"
    _write_rows(documents_path, DOCUMENT_FIELDS, sorted(document_rows.values(), key=lambda row: str(row["document_id"])))
    _write_rows(
        document_texts_path,
        DOCUMENT_TEXT_FIELDS,
        sorted(document_text_rows, key=lambda row: (str(row["deal_id"]), str(row["document_id"]))),
    )
    _write_rows(passages_path, PASSAGE_FIELDS, passage_rows)
    _write_rows(sources_path, PASSAGE_SOURCE_FIELDS, source_rows)

    extraction_counts = Counter(str(row["extraction_status"]) for row in document_text_rows)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "review_sha256": _file_sha256(review_csv),
        "selected_deal_ids": [deal["deal_id"] for deal in deals],
        "context_blocks": context_blocks,
        "max_block_words": max_block_words,
        "documents_considered": len(document_text_rows),
        "documents_parsed": extraction_counts["parsed"],
        "extraction_status_counts": dict(sorted(extraction_counts.items())),
        "canonical_passages": len(corpus.passages),
        "provision_families": len(set(provision_family_by_passage.values())),
        "passage_occurrences": len(corpus.occurrences),
        "blocks_scanned": corpus.blocks_scanned,
        "blocks_matched": corpus.blocks_matched,
        "passages_sha256": _file_sha256(passages_path),
        "passage_sources_sha256": _file_sha256(sources_path),
    }
    _write_json(output_dir / "corpus_manifest.json", manifest)
    return WorkflowSummary(
        status="complete" if extraction_counts["parsed"] else "no_cached_documents",
        output_dir=output_dir,
        counts={
            "deals": len(deals),
            "documents": len(document_text_rows),
            "documents_parsed": extraction_counts["parsed"],
            "passages": len(corpus.passages),
            "passage_occurrences": len(corpus.occurrences),
        },
    )


def _format_number(value: float | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".10g")
    return str(value)


def _assignment_rows(result: EmployeeTopicResult) -> list[dict[str, object]]:
    topics = {row.topic_id: row for row in result.topics}
    output: list[dict[str, object]] = []
    for assignment in result.assignments:
        topic = topics[assignment.topic_id]
        output.append(
            {
                **asdict(assignment),
                "canonical_passage_id": assignment.passage_id,
                "topic_weight": _format_number(assignment.topic_weight),
                "primary_topic": str(assignment.primary_topic).lower(),
                "top_terms": "|".join(topic.top_terms),
                "method": "nmf",
                "coherence": _format_number(topic.coherence),
                "stability_recovery_rate": _format_number(topic.stability_recovery_rate),
            }
        )
    return output


def _source_passages(
    canonical_rows: Sequence[dict[str, str]], source_rows: Sequence[dict[str, str]]
) -> list[dict[str, object]]:
    canonical_by_id = {row["passage_id"]: row for row in canonical_rows}
    representative_sources: dict[tuple[str, str], dict[str, str]] = {}
    for source in sorted(source_rows, key=lambda row: row.get("occurrence_id", "")):
        key = (source.get("deal_id", ""), source.get("passage_id", ""))
        representative_sources.setdefault(key, source)

    output: list[dict[str, object]] = []
    for (deal_id, canonical_passage_id), source in sorted(representative_sources.items()):
        canonical = canonical_by_id.get(canonical_passage_id)
        if canonical is None:
            raise ValueError(
                f"Passage source references unknown passage_id={canonical_passage_id!r}."
            )
        row: dict[str, object] = {field: canonical.get(field, "") for field in PASSAGE_FIELDS}
        row.update(
            {
                "passage_id": source["occurrence_id"],
                "canonical_passage_id": canonical_passage_id,
                "deal_id": deal_id,
                "document_id": source["document_id"],
                "document_family_id": source["document_family_id"],
                "source_document_family_id": source["source_document_family_id"],
                "accession_number": source["accession_number"],
                "document_type": source["document_type"],
                "source_url": source["source_url"],
                "heading": source["heading"],
                "block_start": source["block_start"],
                "block_end": source["block_end"],
                "char_start": source["char_start"],
                "char_end": source["char_end"],
                "occurrence_count": 1,
            }
        )
        output.append(row)
    return output


def _propagated_assignment_rows(
    result: EmployeeTopicResult, source_passages: Sequence[dict[str, object]]
) -> list[dict[str, object]]:
    canonical_rows = _assignment_rows(result)
    by_passage: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in canonical_rows:
        by_passage[str(row["canonical_passage_id"])].append(row)
    output: list[dict[str, object]] = []
    for passage in source_passages:
        canonical_passage_id = str(passage["canonical_passage_id"])
        for canonical in by_passage.get(canonical_passage_id, ()):
            output.append(
                {
                    **canonical,
                    "passage_id": passage["passage_id"],
                    "canonical_passage_id": canonical_passage_id,
                    "deal_id": passage["deal_id"],
                    "document_id": passage["document_id"],
                    "document_family_id": passage["document_family_id"],
                    "source_url": passage["source_url"],
                }
            )
    return output


def _propagated_deal_topics(
    deals: Sequence[dict[str, str]],
    result: EmployeeTopicResult,
    source_rows: Sequence[dict[str, str]],
) -> list[dict[str, object]]:
    assignments_by_passage: defaultdict[str, list[AssignmentRow]] = defaultdict(list)
    for assignment in result.assignments:
        assignments_by_passage[assignment.passage_id].append(assignment)
    deal_passages = {
        (row.get("deal_id", ""), row.get("passage_id", ""))
        for row in source_rows
        if row.get("deal_id") and row.get("passage_id")
    }
    sums: defaultdict[str, defaultdict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    primary: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for deal_id, passage_id in sorted(deal_passages):
        for assignment in assignments_by_passage.get(passage_id, ()):
            sums[deal_id][assignment.topic_id] += assignment.topic_weight
            if assignment.primary_topic:
                primary[deal_id][assignment.topic_id] += 1

    topic_ids = sorted(row.topic_id for row in result.topics)
    output: list[dict[str, object]] = []
    for deal in deals:
        deal_id = deal["deal_id"]
        total = sum(sums[deal_id].values())
        if not topic_ids or not total:
            zero_state = (
                "no_employee_passages"
                if not any(source_deal == deal_id for source_deal, _ in deal_passages)
                else "no_stable_topic_assignment"
            )
            output.append(
                {
                    "deal_id": deal_id,
                    "acquirer_name": deal.get("acquirer_name", ""),
                    "target_name": deal.get("target_name", ""),
                    "topic_id": "",
                    "weight_sum": "0",
                    "normalized_weight": "0",
                    "primary_passage_count": "0",
                    "zero_state": zero_state,
                }
            )
            continue
        for topic_id in topic_ids:
            weight = sums[deal_id][topic_id]
            output.append(
                {
                    "deal_id": deal_id,
                    "acquirer_name": deal.get("acquirer_name", ""),
                    "target_name": deal.get("target_name", ""),
                    "topic_id": topic_id,
                    "weight_sum": _format_number(weight),
                    "normalized_weight": _format_number(weight / total),
                    "primary_passage_count": primary[deal_id][topic_id],
                    "zero_state": "",
                }
            )
    return output


def _heatmap_svg(deals: Sequence[dict[str, str]], result: EmployeeTopicResult, rows: Sequence[dict[str, object]]) -> str:
    topics = sorted(row.topic_id for row in result.topics)
    cell_width = 92
    cell_height = 28
    label_width = 230
    width = label_width + max(1, len(topics)) * cell_width + 20
    height = 72 + len(deals) * cell_height + 40
    weights = {
        (str(row["deal_id"]), str(row["topic_id"])): float(
            str(row["normalized_weight"])
        )
        for row in rows
        if row["topic_id"]
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:system-ui,sans-serif;font-size:12px}.title{font-size:16px;font-weight:600}.topic{font-weight:600}</style>',
        '<text class="title" x="10" y="24">Employee disclosure topic shares by deal</text>',
    ]
    if not topics:
        parts.append('<text x="10" y="50">No stable topic solution; see diagnostic output.</text>')
    for column, topic_id in enumerate(topics):
        x = label_width + column * cell_width
        parts.append(f'<text class="topic" x="{x + 4}" y="52">{escape(topic_id)}</text>')
    for row_index, deal in enumerate(deals):
        y = 60 + row_index * cell_height
        label = f"{deal.get('acquirer_name', '')}–{deal.get('target_name', '')}".strip("–") or deal["deal_id"]
        parts.append(f'<text x="10" y="{y + 19}">{escape(label[:34])}</text>')
        for column, topic_id in enumerate(topics):
            value = weights.get((deal["deal_id"], topic_id), 0.0)
            intensity = round(245 - (155 * value))
            x = label_width + column * cell_width
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_width - 4}" height="{cell_height - 4}" fill="rgb({intensity},{intensity},245)"/>'
            )
            parts.append(f'<text x="{x + 6}" y="{y + 17}">{value:.1%}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def analyze_employee_topics_workflow(
    review_csv: Path,
    corpus_dir: Path,
    output_dir: Path,
    *,
    config: TopicModelConfig = TopicModelConfig(),
) -> WorkflowSummary:
    """Analyze canonical passages and propagate their assignments to every represented deal."""
    passages_path = corpus_dir / "passages.csv"
    sources_path = corpus_dir / "passage_sources.csv"
    deals = _selected_deals(review_csv)
    canonical_passages = _read_rows(passages_path)
    source_rows = _read_rows(sources_path)
    result = analyze_employee_topics_csv(passages_path, config)
    source_passage_rows = _source_passages(canonical_passages, source_rows)
    canonical_assignment_rows = _assignment_rows(result)
    assignment_rows = _propagated_assignment_rows(result, source_passage_rows)
    deal_topic_rows = _propagated_deal_topics(deals, result, source_rows)

    _write_rows(output_dir / "source_passages.csv", PASSAGE_FIELDS, source_passage_rows)
    _write_rows(output_dir / "topic_assignments.csv", TOPIC_ASSIGNMENT_FIELDS, assignment_rows)
    _write_rows(
        output_dir / "canonical_topic_assignments.csv",
        TOPIC_ASSIGNMENT_FIELDS,
        canonical_assignment_rows,
    )
    _write_rows(
        output_dir / "topic_summary.csv",
        TOPIC_SUMMARY_FIELDS,
        (
            {
                **asdict(row),
                "top_terms": "|".join(row.top_terms),
                "coherence": _format_number(row.coherence),
                "stability_median_cosine": _format_number(row.stability_median_cosine),
                "stability_recovery_rate": _format_number(row.stability_recovery_rate),
            }
            for row in result.topics
        ),
    )
    _write_rows(output_dir / "deal_topic_matrix.csv", DEAL_TOPIC_FIELDS, deal_topic_rows)
    _write_rows(
        output_dir / "model_diagnostics.csv",
        DIAGNOSTIC_FIELDS,
        ({**asdict(row), "value": _format_number(row.value)} for row in result.diagnostics),
    )
    _write_rows(
        output_dir / "sensitivity_assignments.csv",
        SENSITIVITY_FIELDS,
        (asdict(row) for row in result.sensitivity_assignments),
    )
    _write_rows(
        output_dir / "stability.csv",
        STABILITY_FIELDS,
        (
            {
                **asdict(row),
                "cosine_similarity": _format_number(row.cosine_similarity),
                "recovered": str(row.recovered).lower(),
            }
            for row in result.stability
        ),
    )
    heatmap_path = output_dir / "deal_topic_heatmap.svg"
    heatmap_path.parent.mkdir(parents=True, exist_ok=True)
    heatmap_path.write_text(_heatmap_svg(deals, result, deal_topic_rows), encoding="utf-8")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "status": result.status,
        "reason": result.reason,
        "review_sha256": _file_sha256(review_csv),
        "passages_sha256": _file_sha256(passages_path),
        "passage_sources_sha256": _file_sha256(sources_path),
        "config": asdict(config),
        "selected_deal_ids": [deal["deal_id"] for deal in deals],
        "topic_count": len(result.topics),
        "canonical_assignment_count": len(result.assignments),
        "source_assignment_count": len(assignment_rows),
        "deal_topic_row_count": len(deal_topic_rows),
    }
    _write_json(output_dir / "analysis_manifest.json", manifest)
    return WorkflowSummary(
        status=result.status,
        output_dir=output_dir,
        counts={
            "deals": len(deals),
            "topics": len(result.topics),
            "assignments": len(assignment_rows),
            "deal_topic_rows": len(deal_topic_rows),
        },
    )


def summarize_employee_topics_workflow(
    review_csv: Path,
    corpus_dir: Path,
    analysis_dir: Path,
    output_dir: Path,
    *,
    representative_limit: int = 3,
) -> WorkflowSummary:
    """Validate the full artifact chain and write the descriptive report plus review queue."""
    deals = _selected_deals(review_csv)
    report = build_employee_report(
        corpus_dir / "documents.csv",
        analysis_dir / "source_passages.csv",
        analysis_dir / "topic_assignments.csv",
        analysis_dir / "deal_topic_matrix.csv",
        analysis_dir / "model_diagnostics.csv",
        expected_deal_count=len(deals),
        representative_limit=representative_limit,
    )
    write_employee_report(
        report,
        output_dir / "employee_topics_report.md",
        output_dir / "topic_review.csv",
    )
    _write_json(
        output_dir / "report_manifest.json",
        {
            "schema_version": 1,
            "gate_passed": report.gate_passed,
            "selected_deal_ids": [deal["deal_id"] for deal in deals],
            "representative_limit": representative_limit,
            "passages_sha256": _file_sha256(analysis_dir / "source_passages.csv"),
            "assignments_sha256": _file_sha256(analysis_dir / "topic_assignments.csv"),
            "deal_topics_sha256": _file_sha256(analysis_dir / "deal_topic_matrix.csv"),
            "diagnostics_sha256": _file_sha256(analysis_dir / "model_diagnostics.csv"),
        },
    )
    return WorkflowSummary(
        status="pass" if report.gate_passed else "fail",
        output_dir=output_dir,
        counts={"deals": len(deals), "topic_review_rows": len(report.topic_review_rows)},
    )
