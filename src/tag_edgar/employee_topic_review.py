from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

REVIEW_PACKET_FIELDS = [
    "review_order",
    "review_item_id",
    "blind_topic_id",
    "topic_terms",
    "passage_text",
    "fit_code",
    "reviewer_id",
    "reviewer_notes",
]

REVIEW_KEY_FIELDS = [
    "review_order",
    "review_item_id",
    "topic_id",
    "blind_topic_id",
    "passage_id",
    "canonical_passage_id",
    "deal_id",
    "document_id",
    "document_family_id",
    "source_url",
    "topic_weight",
    "topic_terms",
    "passage_text_sha256",
]

TOPIC_SCORE_FIELDS = [
    "topic_id",
    "blind_topic_id",
    "item_count",
    "reviewer_1_id",
    "reviewer_1_fit_count",
    "reviewer_1_partial_count",
    "reviewer_1_not_fit_count",
    "reviewer_1_fit_rate",
    "reviewer_2_id",
    "reviewer_2_fit_count",
    "reviewer_2_partial_count",
    "reviewer_2_not_fit_count",
    "reviewer_2_fit_rate",
    "pooled_fit_rate",
    "pooled_partial_rate",
    "exact_agreement_rate",
    "cohen_kappa",
    "cohen_kappa_status",
    "gwet_ac1",
    "agreement_metric_used",
    "agreement_coefficient",
]

DIAGNOSTIC_FIELDS = ["stage", "name", "value", "status", "detail"]

_ASSIGNMENT_COLUMNS = frozenset(
    {"passage_id", "topic_id", "topic_weight", "primary_topic", "top_terms"}
)
_PASSAGE_COLUMNS = frozenset({"passage_id"})
_KEY_COLUMNS = frozenset(REVIEW_KEY_FIELDS)
_CODING_COLUMNS = frozenset(
    {"review_item_id", "blind_topic_id", "fit_code", "reviewer_id"}
)
_FIT_CODES = ("fit", "partial", "not_fit")


@dataclass(frozen=True)
class TopicReviewConfig:
    top_n: int = 10
    seed: int = 20260823
    min_fit_rate: float = 0.80
    min_exact_agreement: float = 0.80
    min_agreement_coefficient: float = 0.70

    def __post_init__(self) -> None:
        if self.top_n < 1:
            raise ValueError("top_n must be at least 1.")
        for name in (
            "min_fit_rate",
            "min_exact_agreement",
            "min_agreement_coefficient",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")


@dataclass(frozen=True)
class ReviewPreparation:
    output_dir: Path
    topic_count: int
    review_item_count: int
    packet_sha256: str


@dataclass(frozen=True)
class ReviewScore:
    output_dir: Path
    status: str
    topic_scores: tuple[dict[str, str], ...]
    diagnostics: tuple[dict[str, str], ...]


class _AgreementValues(TypedDict):
    exact_agreement_rate: float
    cohen_kappa: float | None
    cohen_kappa_status: str
    gwet_ac1: float
    agreement_metric_used: str
    agreement_coefficient: float


def prepare_topic_review(
    assignments_csv: Path,
    passages_csv: Path,
    output_dir: Path,
    *,
    config: TopicReviewConfig = TopicReviewConfig(),
) -> ReviewPreparation:
    """Write a seeded, blinded top-passage packet and a private re-identification key."""
    assignments = _read_csv(assignments_csv, _ASSIGNMENT_COLUMNS)
    passages = _read_csv(passages_csv, _PASSAGE_COLUMNS)
    passage_by_id = _unique_rows(passages, "passage_id", passages_csv)
    primary = [row for row in assignments if _parse_bool(row["primary_topic"])]
    if not primary:
        raise ValueError("No primary topic assignments were found.")

    by_topic: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()
    for row in primary:
        pair = (row["topic_id"].strip(), row["passage_id"].strip())
        if not all(pair) or pair in seen_pairs:
            continue
        if pair[1] not in passage_by_id:
            raise ValueError(f"Assignment references unknown passage_id={pair[1]!r}.")
        _parse_weight(row["topic_weight"], pair[1])
        seen_pairs.add(pair)
        by_topic[pair[0]].append(row)

    topic_ids = sorted(by_topic)
    if not topic_ids:
        raise ValueError("No non-empty topic IDs were found in primary assignments.")
    blinded_topics = {
        topic_id: f"blind_topic_{index:03d}"
        for index, topic_id in enumerate(
            sorted(topic_ids, key=lambda item: _seed_rank(config.seed, "topic", item)), start=1
        )
    }

    prepared: list[tuple[dict[str, str], dict[str, str]]] = []
    for topic_id in topic_ids:
        candidates = sorted(
            by_topic[topic_id],
            key=lambda row: (-_parse_weight(row["topic_weight"], row["passage_id"]), row["passage_id"]),
        )
        selected = _family_diverse_top(candidates, passage_by_id, config.top_n)
        if len(selected) < config.top_n:
            raise ValueError(
                f"Topic {topic_id!r} has {len(selected)} unique primary passages; "
                f"top_n={config.top_n} cannot be prepared."
            )
        for assignment in selected:
            passage = passage_by_id[assignment["passage_id"]]
            passage_text = _passage_text(passage)
            if not passage_text:
                raise ValueError(
                    f"Passage {assignment['passage_id']!r} has no raw_text or text."
                )
            review_item_id = "review_" + _digest(
                str(config.seed), topic_id, assignment["passage_id"]
            )[:16]
            topic_terms = assignment["top_terms"].strip()
            packet = {
                "review_order": "",
                "review_item_id": review_item_id,
                "blind_topic_id": blinded_topics[topic_id],
                "topic_terms": topic_terms,
                "passage_text": passage_text,
                "fit_code": "",
                "reviewer_id": "",
                "reviewer_notes": "",
            }
            key = {
                "review_order": "",
                "review_item_id": review_item_id,
                "topic_id": topic_id,
                "blind_topic_id": blinded_topics[topic_id],
                "passage_id": assignment["passage_id"],
                "canonical_passage_id": assignment.get("canonical_passage_id", "")
                or passage.get("canonical_passage_id", "")
                or assignment["passage_id"],
                "deal_id": assignment.get("deal_id", "") or passage.get("deal_id", ""),
                "document_id": assignment.get("document_id", "")
                or passage.get("document_id", ""),
                "document_family_id": assignment.get("document_family_id", "")
                or passage.get("document_family_id", ""),
                "source_url": assignment.get("source_url", "") or passage.get("source_url", ""),
                "topic_weight": _format_float(
                    _parse_weight(assignment["topic_weight"], assignment["passage_id"])
                ),
                "topic_terms": topic_terms,
                "passage_text_sha256": hashlib.sha256(passage_text.encode()).hexdigest(),
            }
            prepared.append((packet, key))

    prepared.sort(key=lambda item: _seed_rank(config.seed, "order", item[0]["review_item_id"]))
    packet_rows: list[dict[str, str]] = []
    key_rows: list[dict[str, str]] = []
    for order, (packet, key) in enumerate(prepared, start=1):
        packet_rows.append({**packet, "review_order": str(order)})
        key_rows.append({**key, "review_order": str(order)})

    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "topic_review_packet.csv"
    _write_csv(packet_path, packet_rows, REVIEW_PACKET_FIELDS)
    _write_csv(output_dir / "reviewer_1.csv", packet_rows, REVIEW_PACKET_FIELDS)
    _write_csv(output_dir / "reviewer_2.csv", packet_rows, REVIEW_PACKET_FIELDS)
    _write_csv(output_dir / "topic_review_key.csv", key_rows, REVIEW_KEY_FIELDS)
    packet_sha256 = _file_sha256(packet_path)
    manifest = {
        "schema_version": 1,
        "seed": config.seed,
        "top_n": config.top_n,
        "topic_count": len(topic_ids),
        "review_item_count": len(packet_rows),
        "fit_codes": list(_FIT_CODES),
        "packet_sha256": packet_sha256,
        "assignments_sha256": _file_sha256(assignments_csv),
        "passages_sha256": _file_sha256(passages_csv),
        "blinding": "actual topic IDs, model weights, deal IDs, and sources are private-key only",
    }
    (output_dir / "topic_review_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ReviewPreparation(output_dir, len(topic_ids), len(packet_rows), packet_sha256)


def score_topic_review(
    key_csv: Path,
    reviewer_one_csv: Path,
    reviewer_two_csv: Path,
    output_dir: Path,
    *,
    config: TopicReviewConfig = TopicReviewConfig(),
) -> ReviewScore:
    """Validate two independent coding files and write fit/agreement release gates."""
    key_rows = _read_csv(key_csv, _KEY_COLUMNS)
    key_by_id = _unique_rows(key_rows, "review_item_id", key_csv)
    if not key_by_id:
        raise ValueError("The review key contains no review items.")
    reviewer_one = _validated_codings(reviewer_one_csv, key_by_id)
    reviewer_two = _validated_codings(reviewer_two_csv, key_by_id)
    reviewer_one_id = _single_reviewer_id(reviewer_one, reviewer_one_csv)
    reviewer_two_id = _single_reviewer_id(reviewer_two, reviewer_two_csv)
    if reviewer_one_id == reviewer_two_id:
        raise ValueError("The two coding files must contain distinct reviewer_id values.")

    by_topic: defaultdict[str, list[str]] = defaultdict(list)
    blind_by_topic: dict[str, str] = {}
    topic_by_blind: dict[str, str] = {}
    for item_id, row in key_by_id.items():
        topic_id = row["topic_id"].strip()
        blind_topic_id = row["blind_topic_id"].strip()
        if not topic_id:
            raise ValueError(f"Review key item {item_id!r} has a blank topic_id.")
        if not blind_topic_id:
            raise ValueError(f"Review key item {item_id!r} has a blank blind_topic_id.")
        mapped_topic = topic_by_blind.setdefault(blind_topic_id, topic_id)
        if mapped_topic != topic_id:
            raise ValueError(
                f"Review key blind_topic_id={blind_topic_id!r} maps to multiple topics."
            )
        mapped_blind = blind_by_topic.setdefault(topic_id, blind_topic_id)
        if mapped_blind != blind_topic_id:
            raise ValueError(f"Review key topic_id={topic_id!r} maps to multiple blind topics.")
        by_topic[topic_id].append(item_id)

    scores: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = [
        _diagnostic(
            "human_review",
            "coding_completeness",
            len(key_by_id),
            "pass",
            "Both files contain exactly one valid code for every private-key item.",
        ),
        _diagnostic(
            "human_review",
            "independent_reviewer_ids",
            2,
            "pass",
            f"Distinct reviewer IDs: {reviewer_one_id!r} and {reviewer_two_id!r}.",
        ),
    ]
    all_one: list[str] = []
    all_two: list[str] = []
    for topic_id in sorted(by_topic):
        item_ids = sorted(by_topic[topic_id])
        codes_one = [reviewer_one[item_id]["fit_code"] for item_id in item_ids]
        codes_two = [reviewer_two[item_id]["fit_code"] for item_id in item_ids]
        all_one.extend(codes_one)
        all_two.extend(codes_two)
        diagnostics.append(
            _diagnostic(
                "human_review",
                f"{topic_id}_sample_size",
                len(item_ids),
                "pass" if len(item_ids) == config.top_n else "fail",
                f"Required exactly {config.top_n} independently coded passages per topic.",
            )
        )
        score = _topic_score(
            topic_id,
            blind_by_topic[topic_id],
            reviewer_one_id,
            codes_one,
            reviewer_two_id,
            codes_two,
        )
        scores.append(score)
        for reviewer_number in (1, 2):
            rate = float(score[f"reviewer_{reviewer_number}_fit_rate"])
            diagnostics.append(
                _diagnostic(
                    "human_review",
                    f"{topic_id}_reviewer_{reviewer_number}_fit_rate",
                    rate,
                    "pass" if rate >= config.min_fit_rate else "fail",
                    f"Only 'fit' counts; required >= {config.min_fit_rate:.0%}. "
                    f"Partial={score[f'reviewer_{reviewer_number}_partial_count']}.",
                )
            )
        diagnostics.append(_agreement_diagnostic(topic_id, score, config))

    overall = _agreement_values(all_one, all_two)
    diagnostics.append(
        _diagnostic(
            "human_review",
            "overall_interrater_agreement",
            overall["agreement_coefficient"],
            "pass"
            if overall["exact_agreement_rate"] >= config.min_exact_agreement
            and overall["agreement_coefficient"] >= config.min_agreement_coefficient
            else "fail",
            _agreement_detail(overall, config),
        )
    )
    status = "pass" if all(row["status"] == "pass" for row in diagnostics) else "fail"
    diagnostics.append(
        _diagnostic(
            "human_review",
            "topic_review_release_gate",
            status,
            status,
            "Pass requires complete independent coding, reviewer-level fit gates for every "
            "topic, and topic-level plus overall agreement gates.",
        )
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "topic_review_scores.csv", scores, TOPIC_SCORE_FIELDS)
    _write_csv(output_dir / "topic_review_diagnostics.csv", diagnostics, DIAGNOSTIC_FIELDS)
    score_manifest = {
        "schema_version": 1,
        "status": status,
        "topic_count": len(scores),
        "review_item_count": len(key_by_id),
        "top_n": config.top_n,
        "min_fit_rate": config.min_fit_rate,
        "min_exact_agreement": config.min_exact_agreement,
        "min_agreement_coefficient": config.min_agreement_coefficient,
        "key_sha256": _file_sha256(key_csv),
        "reviewer_one_sha256": _file_sha256(reviewer_one_csv),
        "reviewer_two_sha256": _file_sha256(reviewer_two_csv),
    }
    (output_dir / "topic_review_score_manifest.json").write_text(
        json.dumps(score_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ReviewScore(output_dir, status, tuple(scores), tuple(diagnostics))


def _family_diverse_top(
    candidates: Sequence[dict[str, str]],
    passage_by_id: Mapping[str, dict[str, str]],
    limit: int,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()
    families: set[str] = set()
    for candidate in candidates:
        passage = passage_by_id[candidate["passage_id"]]
        family = candidate.get("document_family_id", "") or passage.get(
            "document_family_id", ""
        )
        if family and family in families:
            continue
        selected.append(candidate)
        selected_ids.add(candidate["passage_id"])
        if family:
            families.add(family)
        if len(selected) == limit:
            return selected
    for candidate in candidates:
        if candidate["passage_id"] in selected_ids:
            continue
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


def _topic_score(
    topic_id: str,
    blind_topic_id: str,
    reviewer_one_id: str,
    codes_one: Sequence[str],
    reviewer_two_id: str,
    codes_two: Sequence[str],
) -> dict[str, str]:
    one = Counter(codes_one)
    two = Counter(codes_two)
    total = len(codes_one)
    agreement = _agreement_values(codes_one, codes_two)
    return {
        "topic_id": topic_id,
        "blind_topic_id": blind_topic_id,
        "item_count": str(total),
        "reviewer_1_id": reviewer_one_id,
        "reviewer_1_fit_count": str(one["fit"]),
        "reviewer_1_partial_count": str(one["partial"]),
        "reviewer_1_not_fit_count": str(one["not_fit"]),
        "reviewer_1_fit_rate": _format_float(one["fit"] / total),
        "reviewer_2_id": reviewer_two_id,
        "reviewer_2_fit_count": str(two["fit"]),
        "reviewer_2_partial_count": str(two["partial"]),
        "reviewer_2_not_fit_count": str(two["not_fit"]),
        "reviewer_2_fit_rate": _format_float(two["fit"] / total),
        "pooled_fit_rate": _format_float((one["fit"] + two["fit"]) / (2 * total)),
        "pooled_partial_rate": _format_float(
            (one["partial"] + two["partial"]) / (2 * total)
        ),
        "exact_agreement_rate": _format_float(agreement["exact_agreement_rate"]),
        "cohen_kappa": _format_optional_float(agreement["cohen_kappa"]),
        "cohen_kappa_status": str(agreement["cohen_kappa_status"]),
        "gwet_ac1": _format_float(agreement["gwet_ac1"]),
        "agreement_metric_used": str(agreement["agreement_metric_used"]),
        "agreement_coefficient": _format_float(agreement["agreement_coefficient"]),
    }


def _agreement_values(
    codes_one: Sequence[str], codes_two: Sequence[str]
) -> _AgreementValues:
    if not codes_one or len(codes_one) != len(codes_two):
        raise ValueError("Agreement requires two non-empty coding sequences of equal length.")
    total = len(codes_one)
    observed = sum(left == right for left, right in zip(codes_one, codes_two, strict=True)) / total
    one = Counter(codes_one)
    two = Counter(codes_two)
    expected = sum((one[code] / total) * (two[code] / total) for code in _FIT_CODES)
    denominator = 1 - expected
    kappa = None if math.isclose(denominator, 0.0, abs_tol=1e-12) else (observed - expected) / denominator

    prevalence = {code: (one[code] + two[code]) / (2 * total) for code in _FIT_CODES}
    ac1_expected = sum(value * (1 - value) for value in prevalence.values()) / (
        len(_FIT_CODES) - 1
    )
    ac1 = (observed - ac1_expected) / (1 - ac1_expected)
    return {
        "exact_agreement_rate": observed,
        "cohen_kappa": kappa,
        "cohen_kappa_status": "estimated" if kappa is not None else "undefined_zero_denominator",
        "gwet_ac1": ac1,
        "agreement_metric_used": "cohen_kappa" if kappa is not None else "gwet_ac1",
        "agreement_coefficient": kappa if kappa is not None else ac1,
    }


def _agreement_diagnostic(
    topic_id: str, score: Mapping[str, str], config: TopicReviewConfig
) -> dict[str, str]:
    exact = float(score["exact_agreement_rate"])
    coefficient = float(score["agreement_coefficient"])
    values: _AgreementValues = {
        "exact_agreement_rate": exact,
        "cohen_kappa": float(score["cohen_kappa"]) if score["cohen_kappa"] else None,
        "cohen_kappa_status": score["cohen_kappa_status"],
        "gwet_ac1": float(score["gwet_ac1"]),
        "agreement_metric_used": score["agreement_metric_used"],
        "agreement_coefficient": coefficient,
    }
    return _diagnostic(
        "human_review",
        f"{topic_id}_interrater_agreement",
        coefficient,
        "pass"
        if exact >= config.min_exact_agreement
        and coefficient >= config.min_agreement_coefficient
        else "fail",
        _agreement_detail(values, config),
    )


def _agreement_detail(values: _AgreementValues, config: TopicReviewConfig) -> str:
    kappa = values["cohen_kappa"]
    kappa_text = "undefined (zero denominator)" if kappa is None else f"{float(kappa):.3f}"
    return (
        f"Exact agreement={float(values['exact_agreement_rate']):.3f} "
        f"(required >= {config.min_exact_agreement:.3f}); Cohen kappa={kappa_text}; "
        f"Gwet AC1={float(values['gwet_ac1']):.3f}; prespecified coefficient="
        f"{values['agreement_metric_used']}={float(values['agreement_coefficient']):.3f} "
        f"(required >= {config.min_agreement_coefficient:.3f}). AC1 is used only when "
        "kappa is mathematically undefined."
    )


def _validated_codings(
    path: Path, key_by_id: Mapping[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    rows = _read_csv(path, _CODING_COLUMNS)
    by_id = _unique_rows(rows, "review_item_id", path)
    expected = set(key_by_id)
    actual = set(by_id)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"{path} does not exactly cover the review key; missing={missing}, extra={extra}."
        )
    for item_id, row in by_id.items():
        code = row["fit_code"].strip().lower()
        if code not in _FIT_CODES:
            raise ValueError(
                f"{path} item {item_id!r} has fit_code={row['fit_code']!r}; "
                f"expected one of {', '.join(_FIT_CODES)}."
            )
        if row["blind_topic_id"].strip() != key_by_id[item_id]["blind_topic_id"].strip():
            raise ValueError(f"{path} item {item_id!r} has an altered blind_topic_id.")
        if not row["reviewer_id"].strip():
            raise ValueError(f"{path} item {item_id!r} has a blank reviewer_id.")
        row["fit_code"] = code
        row["reviewer_id"] = row["reviewer_id"].strip()
    return by_id


def _single_reviewer_id(rows: Mapping[str, dict[str, str]], path: Path) -> str:
    reviewer_ids = {row["reviewer_id"] for row in rows.values()}
    if len(reviewer_ids) != 1:
        raise ValueError(f"{path} must contain exactly one consistent reviewer_id.")
    return next(iter(reviewer_ids))


def _read_csv(path: Path, required: frozenset[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)):
            raise ValueError(f"{path} contains duplicate CSV column names.")
        missing = sorted(required - set(fields))
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}.")
        return [{key: value or "" for key, value in row.items() if key is not None} for row in reader]


def _unique_rows(
    rows: Sequence[dict[str, str]], key: str, path: Path
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        value = row[key].strip()
        if not value:
            raise ValueError(f"{path} row {row_number} has a blank {key}.")
        if value in output:
            raise ValueError(f"{path} contains duplicate {key}={value!r}.")
        output[value] = row
    return output


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"primary_topic must be a boolean, got {value!r}.")


def _parse_weight(value: str, passage_id: str) -> float:
    try:
        weight = float(value)
    except ValueError as error:
        raise ValueError(f"Passage {passage_id!r} has invalid topic_weight={value!r}.") from error
    if not math.isfinite(weight) or weight < 0:
        raise ValueError(f"Passage {passage_id!r} has invalid topic_weight={value!r}.")
    return weight


def _passage_text(row: Mapping[str, str]) -> str:
    return (row.get("raw_text", "") or row.get("text", "")).strip()


def _seed_rank(seed: int, namespace: str, value: str) -> str:
    return _digest(str(seed), namespace, value)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _format_float(value: float) -> str:
    return format(value, ".10g")


def _format_optional_float(value: float | None) -> str:
    return "" if value is None else _format_float(value)


def _diagnostic(
    stage: str, name: str, value: object, status: str, detail: str
) -> dict[str, str]:
    rendered = _format_float(value) if isinstance(value, float) else str(value)
    return {"stage": stage, "name": name, "value": rendered, "status": status, "detail": detail}


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
