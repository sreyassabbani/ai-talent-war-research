from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .storage import write_dict_csv

PACKET_FIELDS = [
    "audit_item_id",
    "packet_order",
    "heading",
    "passage_text",
    "relevance_label",
    "assessor_id",
    "assessor_note",
    "human_attestation",
]

KEY_FIELDS = [
    "audit_item_id",
    "passage_id",
    "deal_id",
    "document_family_id",
    "source_url",
    "inclusion_decision",
    "exclusion_reason",
    "selection_stratum",
    "selection_hash",
    "immutable_packet_hash",
]

SCORE_FIELDS = [
    "metric",
    "scope_dimension",
    "scope_value",
    "successes",
    "total",
    "point_rate",
    "wilson_confidence_level",
    "wilson_lower",
    "wilson_upper",
]

_REQUIRED_CANDIDATE_FIELDS = {
    "passage_id",
    "deal_id",
    "document_family_id",
    "inclusion_status",
    "text",
}
_DECISIONS = frozenset({"included", "excluded"})
_LABELS = frozenset({"relevant", "not_relevant"})
_ATTESTATION = "human_assessed"


@dataclass(frozen=True)
class CorpusAuditPacket:
    packet_rows: tuple[dict[str, str], ...]
    key_rows: tuple[dict[str, str], ...]
    manifest: dict[str, object]


@dataclass(frozen=True)
class CorpusAuditScore:
    status: str
    score_rows: tuple[dict[str, object], ...]
    manifest: dict[str, object]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        rows = [dict(row) for row in reader]
        return list(reader.fieldnames), rows


def _hash(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def _immutable_packet_hash(row: Mapping[str, str]) -> str:
    return _hash(
        row["audit_item_id"],
        row["packet_order"],
        row["heading"],
        row["passage_text"],
    )


def _clean_candidate_rows(path: Path) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    missing = sorted(_REQUIRED_CANDIDATE_FIELDS.difference(fields))
    if missing:
        raise ValueError(f"Candidate CSV is missing required columns: {missing}")
    cleaned = [{key: (value or "").strip() for key, value in row.items()} for row in rows]
    blank_identity = [
        index
        for index, row in enumerate(cleaned, start=2)
        if not row["passage_id"] or not row["deal_id"] or not row["document_family_id"]
    ]
    if blank_identity:
        raise ValueError(f"Candidate rows have blank audit identities at rows {blank_identity}.")
    blank_text = [index for index, row in enumerate(cleaned, start=2) if not row["text"]]
    if blank_text:
        raise ValueError(f"Candidate rows have blank passage text at rows {blank_text}.")
    invalid_decisions = sorted(
        {row["inclusion_status"] for row in cleaned}.difference(_DECISIONS)
    )
    if invalid_decisions:
        raise ValueError(f"Unsupported inclusion_status values: {invalid_decisions}")
    counts = Counter(row["passage_id"] for row in cleaned)
    duplicates = sorted(identifier for identifier, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Candidate CSV has duplicate passage IDs: {duplicates}")
    return cleaned


def _sample_decision(
    rows: Sequence[dict[str, str]], decision: str, limit: int, seed: str
) -> list[dict[str, str]]:
    buckets: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["inclusion_status"] == decision:
            buckets[(row["deal_id"], row["document_family_id"])].append(row)
    for bucket in buckets.values():
        bucket.sort(key=lambda row: (_hash(seed, decision, row["passage_id"]), row["passage_id"]))
    ordered_buckets = sorted(
        buckets,
        key=lambda group: (_hash(seed, decision, *group), group),
    )
    selected: list[dict[str, str]] = []
    while len(selected) < limit and any(buckets.values()):
        for group in ordered_buckets:
            if buckets[group] and len(selected) < limit:
                selected.append(buckets[group].pop(0))
    return selected


def prepare_corpus_relevance_audit(
    candidates_csv: Path,
    *,
    included_limit: int = 75,
    excluded_limit: int = 75,
    seed: str = "employee-corpus-relevance-v1",
) -> CorpusAuditPacket:
    """Create a deterministic assessor-blinded relevance/recall audit packet."""
    if included_limit < 1 or excluded_limit < 1:
        raise ValueError("Included and excluded sample limits must both be positive.")
    if not seed.strip():
        raise ValueError("Audit seed cannot be blank.")
    candidates = _clean_candidate_rows(candidates_csv)
    universe_counts = Counter(row["inclusion_status"] for row in candidates)
    missing_decisions = sorted(_DECISIONS.difference(universe_counts))
    if missing_decisions:
        raise ValueError(f"Candidate CSV has no rows for decisions: {missing_decisions}")

    selected = _sample_decision(candidates, "included", included_limit, seed)
    selected.extend(_sample_decision(candidates, "excluded", excluded_limit, seed))
    selected.sort(key=lambda row: (_hash(seed, "packet-order", row["passage_id"]), row["passage_id"]))

    packet_rows: list[dict[str, str]] = []
    key_rows: list[dict[str, str]] = []
    selected_counts: Counter[str] = Counter()
    for order, source in enumerate(selected, start=1):
        item_id = f"audit_{_hash(seed, 'item', source['passage_id'])[:16]}"
        packet = {
            "audit_item_id": item_id,
            "packet_order": str(order),
            "heading": source.get("heading", ""),
            "passage_text": source["text"],
            "relevance_label": "",
            "assessor_id": "",
            "assessor_note": "",
            "human_attestation": "",
        }
        decision = source["inclusion_status"]
        stratum = f"{decision}|{source['deal_id']}|{source['document_family_id']}"
        key_rows.append(
            {
                "audit_item_id": item_id,
                "passage_id": source["passage_id"],
                "deal_id": source["deal_id"],
                "document_family_id": source["document_family_id"],
                "source_url": source.get("source_url", ""),
                "inclusion_decision": decision,
                "exclusion_reason": source.get("exclusion_reason", ""),
                "selection_stratum": stratum,
                "selection_hash": _hash(seed, decision, source["passage_id"]),
                "immutable_packet_hash": _immutable_packet_hash(packet),
            }
        )
        packet_rows.append(packet)
        selected_counts[decision] += 1

    manifest: dict[str, object] = {
        "schema_version": 1,
        "audit_status": "pending_human_labels",
        "gate_status": "pending",
        "labels_present": False,
        "labels_are_human_attested": False,
        "candidate_csv_sha256": _file_sha256(candidates_csv),
        "selection_seed": seed,
        "selection_method": "decision_then_deal_document_family_round_robin_with_sha256_order",
        "blinded_packet_omits": [
            "passage_id",
            "deal_id",
            "document_family_id",
            "source_url",
            "inclusion_decision",
            "exclusion_reason",
        ],
        "universe_counts": dict(sorted(universe_counts.items())),
        "requested_counts": {"included": included_limit, "excluded": excluded_limit},
        "sample_counts": dict(sorted(selected_counts.items())),
        "distinct_sampled_deals": len({row["deal_id"] for row in key_rows}),
        "distinct_sampled_document_families": len(
            {row["document_family_id"] for row in key_rows}
        ),
        "human_label_contract": {
            "relevance_label": sorted(_LABELS),
            "assessor_id": "nonblank",
            "human_attestation": _ATTESTATION,
            "all_sampled_rows_required": True,
        },
        "gate_thresholds": {
            "included_passage_relevance_minimum": 0.90,
            "excluded_candidate_missed_content_maximum_exclusive": 0.05,
        },
        "confidence_interval": "two-sided 95% Wilson score interval",
    }
    return CorpusAuditPacket(tuple(packet_rows), tuple(key_rows), manifest)


def write_corpus_relevance_audit(output_dir: Path, audit: CorpusAuditPacket) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "assessor_packet.csv"
    key_path = output_dir / "private_key.csv"
    write_dict_csv(packet_path, audit.packet_rows, PACKET_FIELDS)
    write_dict_csv(key_path, audit.key_rows, KEY_FIELDS)
    manifest = {
        **audit.manifest,
        "assessor_packet_sha256": _file_sha256(packet_path),
        "private_key_sha256": _file_sha256(key_path),
    }
    (output_dir / "audit_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _validate_completed_packet(
    key_csv: Path, completed_packet_csv: Path
) -> list[tuple[dict[str, str], dict[str, str]]]:
    key_fields, key_rows = _read_csv(key_csv)
    packet_fields, packet_rows = _read_csv(completed_packet_csv)
    if key_fields != KEY_FIELDS:
        raise ValueError(f"Private key columns must exactly match {KEY_FIELDS}.")
    if packet_fields != PACKET_FIELDS:
        raise ValueError(f"Completed packet columns must exactly match {PACKET_FIELDS}.")
    for name, rows in (("Private key", key_rows), ("Completed packet", packet_rows)):
        identifiers = [row["audit_item_id"] for row in rows]
        if any(not identifier for identifier in identifiers):
            raise ValueError(f"{name} contains a blank audit_item_id.")
        duplicates = sorted(identifier for identifier, count in Counter(identifiers).items() if count > 1)
        if duplicates:
            raise ValueError(f"{name} has duplicate audit item IDs: {duplicates}")
    keys = {row["audit_item_id"]: row for row in key_rows}
    packets = {row["audit_item_id"]: row for row in packet_rows}
    if keys.keys() != packets.keys():
        missing = sorted(keys.keys() - packets.keys())
        unexpected = sorted(packets.keys() - keys.keys())
        raise ValueError(f"Completed packet item mismatch; missing={missing}, unexpected={unexpected}.")

    joined: list[tuple[dict[str, str], dict[str, str]]] = []
    for item_id in sorted(keys):
        key = keys[item_id]
        packet = packets[item_id]
        if _immutable_packet_hash(packet) != key["immutable_packet_hash"]:
            raise ValueError(f"Immutable packet content changed for {item_id}.")
        label = packet["relevance_label"]
        if label not in _LABELS:
            raise ValueError(
                f"{item_id} relevance_label must be exactly relevant or not_relevant."
            )
        if not packet["assessor_id"].strip():
            raise ValueError(f"{item_id} assessor_id must be nonblank.")
        if packet["human_attestation"] != _ATTESTATION:
            raise ValueError(f"{item_id} human_attestation must be exactly {_ATTESTATION}.")
        if key["inclusion_decision"] not in _DECISIONS:
            raise ValueError(f"Private key has invalid inclusion decision for {item_id}.")
        packet["relevance_label"] = label
        joined.append((key, packet))
    if not joined:
        raise ValueError("Completed packet contains no audit items.")
    return joined


def _validate_audit_manifest(manifest_json: Path, key_csv: Path) -> dict[str, object]:
    try:
        manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"Cannot read audit manifest: {manifest_json}") from error
    if not isinstance(manifest, dict):
        raise TypeError("Audit manifest must contain a JSON object.")
    if manifest.get("schema_version") != 1:
        raise ValueError("Audit manifest schema_version must be 1.")
    if manifest.get("audit_status") != "pending_human_labels" or manifest.get(
        "gate_status"
    ) != "pending":
        raise ValueError("Audit manifest must be an unscored pending-human-label manifest.")
    if manifest.get("labels_present") is not False:
        raise ValueError("Audit manifest must record labels_present=false before scoring.")
    expected_key_hash = manifest.get("private_key_sha256")
    if not isinstance(expected_key_hash, str) or expected_key_hash != _file_sha256(key_csv):
        raise ValueError("Private key SHA-256 does not match the audit manifest.")
    return manifest


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("Wilson interval requires a positive denominator.")
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    half_width = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total**2)) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def _score_row(
    metric: str,
    scope_dimension: str,
    scope_value: str,
    labels: Sequence[str],
) -> dict[str, object]:
    successes = sum(label == "relevant" for label in labels)
    lower, upper = _wilson(successes, len(labels))
    return {
        "metric": metric,
        "scope_dimension": scope_dimension,
        "scope_value": scope_value,
        "successes": successes,
        "total": len(labels),
        "point_rate": f"{successes / len(labels):.6f}",
        "wilson_confidence_level": "0.95",
        "wilson_lower": f"{lower:.6f}",
        "wilson_upper": f"{upper:.6f}",
    }


def score_corpus_relevance_audit(
    key_csv: Path,
    completed_packet_csv: Path,
    audit_manifest_json: Path,
    *,
    minimum_included_relevance: float = 0.90,
    maximum_excluded_miss_rate: float = 0.05,
) -> CorpusAuditScore:
    """Validate attested labels and score the prespecified corpus quality gate."""
    if not 0 <= minimum_included_relevance <= 1:
        raise ValueError("minimum_included_relevance must be between zero and one.")
    if not 0 <= maximum_excluded_miss_rate <= 1:
        raise ValueError("maximum_excluded_miss_rate must be between zero and one.")
    preparation_manifest = _validate_audit_manifest(audit_manifest_json, key_csv)
    joined = _validate_completed_packet(key_csv, completed_packet_csv)
    decision_rows: defaultdict[str, list[tuple[dict[str, str], dict[str, str]]]] = defaultdict(list)
    for key, packet in joined:
        decision_rows[key["inclusion_decision"]].append((key, packet))
    missing = sorted(_DECISIONS.difference(decision_rows))
    if missing:
        raise ValueError(f"Completed audit has no sampled rows for decisions: {missing}")
    actual_sample_counts = {
        decision: len(decision_rows[decision]) for decision in sorted(_DECISIONS)
    }
    if preparation_manifest.get("sample_counts") != actual_sample_counts:
        raise ValueError(
            "Completed audit decision counts do not match audit_manifest.json sample_counts."
        )

    score_rows: list[dict[str, object]] = []
    metric_names = {
        "included": "included_passage_relevance",
        "excluded": "excluded_candidate_missed_content",
    }
    for decision in ("included", "excluded"):
        rows = decision_rows[decision]
        labels = [packet["relevance_label"] for _, packet in rows]
        metric = metric_names[decision]
        score_rows.append(_score_row(metric, "overall", "all", labels))
        for dimension in ("deal_id", "document_family_id"):
            groups: defaultdict[str, list[str]] = defaultdict(list)
            for key, packet in rows:
                groups[key[dimension]].append(packet["relevance_label"])
            for value in sorted(groups):
                score_rows.append(_score_row(metric, dimension, value, groups[value]))

    included = next(
        row
        for row in score_rows
        if row["metric"] == "included_passage_relevance" and row["scope_dimension"] == "overall"
    )
    excluded = next(
        row
        for row in score_rows
        if row["metric"] == "excluded_candidate_missed_content" and row["scope_dimension"] == "overall"
    )
    included_rate = int(str(included["successes"])) / int(str(included["total"]))
    excluded_rate = int(str(excluded["successes"])) / int(str(excluded["total"]))
    included_pass = included_rate >= minimum_included_relevance
    excluded_pass = excluded_rate < maximum_excluded_miss_rate
    status = "pass" if included_pass and excluded_pass else "fail"
    manifest: dict[str, object] = {
        "schema_version": 1,
        "audit_status": "scored_human_labels",
        "gate_status": status,
        "labels_present": True,
        "labels_are_human_attested": True,
        "private_key_sha256": _file_sha256(key_csv),
        "audit_manifest_sha256": _file_sha256(audit_manifest_json),
        "completed_packet_sha256": _file_sha256(completed_packet_csv),
        "completed_item_count": len(joined),
        "sample_counts": actual_sample_counts,
        "assessor_ids": sorted({packet["assessor_id"].strip() for _, packet in joined}),
        "gate_thresholds": {
            "included_passage_relevance_minimum": minimum_included_relevance,
            "excluded_candidate_missed_content_maximum_exclusive": maximum_excluded_miss_rate,
        },
        "gate_results": {
            "included_passage_relevance": {
                "point_rate": included_rate,
                "passes": included_pass,
            },
            "excluded_candidate_missed_content": {
                "point_rate": excluded_rate,
                "passes": excluded_pass,
            },
        },
        "gate_rule": "point estimate: included >= minimum AND excluded < maximum",
        "confidence_interval": "two-sided 95% Wilson score interval; informational, not the gate rule",
        "selection_seed": preparation_manifest.get("selection_seed"),
        "candidate_csv_sha256": preparation_manifest.get("candidate_csv_sha256"),
    }
    return CorpusAuditScore(status, tuple(score_rows), manifest)


def write_corpus_relevance_scores(output_dir: Path, score: CorpusAuditScore) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dict_csv(output_dir / "audit_scores.csv", score.score_rows, SCORE_FIELDS)
    (output_dir / "score_manifest.json").write_text(
        json.dumps(score.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
