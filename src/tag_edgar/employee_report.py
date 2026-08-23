from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

TOPIC_REVIEW_FIELDS = [
    "topic_id",
    "method",
    "top_terms",
    "passage_count",
    "deal_count",
    "representative_passage_ids",
    "representative_source_urls",
    "model_coherence",
    "stability_recovery_rate",
    "reviewer_topic_label",
    "coherence_score_1_to_5",
    "reviewer_id",
    "review_status",
    "reviewer_notes",
]

_DOCUMENT_FIELDS = {"document_id", "url"}
_PASSAGE_FIELDS = {
    "passage_id",
    "deal_id",
    "document_id",
    "source_url",
    "heading",
    "text",
}
_TOPIC_FIELDS = {
    "passage_id",
    "deal_id",
    "document_id",
    "source_url",
    "topic_id",
    "topic_weight",
    "primary_topic",
    "top_terms",
}
_DEAL_TOPIC_FIELDS = {
    "deal_id",
    "topic_id",
    "weight_sum",
    "normalized_weight",
    "primary_passage_count",
    "zero_state",
}
_DIAGNOSTIC_FIELDS = {"stage", "name", "value", "status", "detail"}
_DIAGNOSTIC_STATUSES = {"pass", "fail", "warning", "not_applicable"}
_TRUE_VALUES = {"1", "true", "yes"}
_FALSE_VALUES = {"0", "false", "no"}


@dataclass(frozen=True)
class ClaimLintIssue:
    category: str
    phrase: str
    sentence: str


@dataclass(frozen=True)
class DealClaimLinkIssue:
    deal_id: str
    line: str


@dataclass(frozen=True)
class EmployeeReport:
    markdown: str
    topic_review_rows: tuple[dict[str, str], ...]
    gate_passed: bool


_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "causal",
        re.compile(
            r"\b(?:causes?|caused|causing|drives?|drove|leads? to|led to|results? in|"
            r"is responsible for)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "predictive",
        re.compile(
            r"\b(?:predicts?|predicted|predictive of|forecasts?|forecasted|"
            r"reliably maps? to|determines? (?:the )?outcome)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "actual_retention",
        re.compile(
            r"\b(?:actual retention|employees? (?:were|are|will be) retained|"
            r"workers? (?:stayed|remained)|retention(?: program)? (?:succeeded|worked|failed)|"
            r"kept (?:its|the|their) employees?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "unsupported_certainty",
        re.compile(r"\b(?:proves?|proved|demonstrates? that)\b", re.IGNORECASE),
    ),
)
_NEGATION = re.compile(
    r"\b(?:no|not|never|cannot|can't|doesn't|does not|do not|did not|without)\b",
    re.IGNORECASE,
)


def lint_claims(text: str) -> list[ClaimLintIssue]:
    """Return causal, predictive, or observed-retention claims in authored prose.

    Markdown block quotes are ignored because the report uses them for verbatim source passages.
    Explicitly negated phrases are permitted so limitations can state what the analysis does not do.
    """
    authored_text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(">")
    )
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", authored_text)]
    issues: list[ClaimLintIssue] = []
    for sentence in sentences:
        if not sentence:
            continue
        for category, pattern in _CLAIM_PATTERNS:
            for match in pattern.finditer(sentence):
                prefix = sentence[max(0, match.start() - 60) : match.start()]
                if _NEGATION.search(prefix):
                    continue
                issues.append(
                    ClaimLintIssue(
                        category=category,
                        phrase=match.group(0),
                        sentence=sentence,
                    )
                )
    return issues


def assert_descriptive_claims(text: str) -> None:
    """Reject prose that exceeds a descriptive public-disclosure interpretation."""
    issues = lint_claims(text)
    if not issues:
        return
    rendered = "; ".join(
        f"{issue.category}: {issue.phrase!r}" for issue in issues
    )
    raise ValueError(f"Prohibited research claim(s): {rendered}")


def lint_deal_claim_links(markdown: str, deal_ids: set[str]) -> list[DealClaimLinkIssue]:
    """Find deal-specific report lines without an inline SEC source.

    The sole exception is an explicit pipeline zero state for a deal with no qualifying passage;
    that is a statement about the analysis table, not the contents of an SEC document.
    """
    issues: list[DealClaimLinkIssue] = []
    for line in markdown.splitlines():
        if not line.strip() or line.lstrip().startswith(">"):
            continue
        for deal_id in sorted(deal_ids):
            if deal_id not in line:
                continue
            if "pipeline zero state; no document-content claim" in line:
                continue
            markdown_urls = re.findall(r"\]\((https://[^)]+)\)", line)
            if any(_is_sec_url(url) for url in markdown_urls):
                continue
            issues.append(DealClaimLinkIssue(deal_id=deal_id, line=line))
    return issues


def assert_deal_claim_links(markdown: str, deal_ids: set[str]) -> None:
    """Reject rendered deal-specific claims that lack an inline SEC citation."""
    issues = lint_deal_claim_links(markdown, deal_ids)
    if not issues:
        return
    rendered = "; ".join(f"{issue.deal_id}: {issue.line!r}" for issue in issues)
    raise ValueError(f"Deal-specific claim(s) lack an inline SEC source: {rendered}")


def build_employee_report(
    documents_csv: Path,
    passages_csv: Path,
    topics_csv: Path,
    deal_topics_csv: Path,
    diagnostics_csv: Path,
    *,
    expected_deal_count: int = 10,
    representative_limit: int = 3,
) -> EmployeeReport:
    """Build deterministic Markdown and a blank human topic-review template from CSV outputs."""
    if expected_deal_count < 1:
        raise ValueError("expected_deal_count must be positive.")
    if representative_limit < 1:
        raise ValueError("representative_limit must be positive.")

    documents = _read_rows(documents_csv, _DOCUMENT_FIELDS, "documents")
    passages = _read_rows(passages_csv, _PASSAGE_FIELDS, "passages")
    assignments = _read_rows(topics_csv, _TOPIC_FIELDS, "topics")
    deal_topics = _read_rows(deal_topics_csv, _DEAL_TOPIC_FIELDS, "deal topics")
    diagnostics = _read_rows(diagnostics_csv, _DIAGNOSTIC_FIELDS, "diagnostics")

    document_by_id = _unique_rows(documents, "document_id", "documents")
    passage_by_id = _unique_rows(passages, "passage_id", "passages")
    _validate_passages(passage_by_id, document_by_id)
    _validate_assignments(assignments, passage_by_id)
    deals = _validate_deal_topics(
        deal_topics,
        passage_by_id,
        assignments,
        expected_deal_count,
    )
    gate_passed = _validate_diagnostics(diagnostics)

    review_rows = _topic_review_rows(assignments, representative_limit)
    authored_sections = _authored_report_sections(
        passages,
        assignments,
        deal_topics,
        diagnostics,
        deals,
        gate_passed,
    )
    assert_descriptive_claims("\n".join(authored_sections))
    representative_section = _representative_passage_section(
        assignments,
        passage_by_id,
        deals,
        representative_limit,
    )
    markdown = "\n\n".join([*authored_sections, representative_section]).rstrip() + "\n"
    assert_deal_claim_links(markdown, set(deals))
    return EmployeeReport(
        markdown=markdown,
        topic_review_rows=tuple(review_rows),
        gate_passed=gate_passed,
    )


def write_employee_report(
    report: EmployeeReport,
    markdown_path: Path,
    topic_review_csv: Path,
) -> None:
    """Write a previously built report without changing or reordering its contents."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(report.markdown, encoding="utf-8")
    topic_review_csv.parent.mkdir(parents=True, exist_ok=True)
    with topic_review_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=TOPIC_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(report.topic_review_rows)


def _read_rows(path: Path, required_fields: set[str], label: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing = required_fields - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{label.title()} CSV is missing required columns: {sorted(missing)}")
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def _unique_rows(
    rows: list[dict[str, str]], key: str, label: str
) -> dict[str, dict[str, str]]:
    missing = [index for index, row in enumerate(rows, start=2) if not row[key]]
    if missing:
        raise ValueError(f"{label.title()} CSV has blank {key} at rows {missing}.")
    counts = Counter(row[key] for row in rows)
    duplicates = sorted(value for value, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"{label.title()} CSV has duplicate {key} values: {duplicates}")
    return {row[key]: row for row in rows}


def _canonical_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ValueError(f"Source URL must be an absolute HTTPS URL, got {value!r}.")
    host = parts.hostname.lower()
    if not (host == "sec.gov" or host.endswith(".sec.gov")):
        raise ValueError(f"Source URL must be an HTTPS SEC URL, got {value!r}.")
    if host in {"sec.gov", "www.sec.gov"}:
        host = "sec.gov"
    return urlunsplit(("https", host, parts.path.rstrip("/"), "", ""))


def _is_sec_url(value: str) -> bool:
    try:
        _canonical_url(value)
    except ValueError:
        return False
    return True


def _validate_passages(
    passage_by_id: dict[str, dict[str, str]],
    document_by_id: dict[str, dict[str, str]],
) -> None:
    for passage_id, passage in passage_by_id.items():
        if not passage["deal_id"]:
            raise ValueError(f"Passage {passage_id} has a blank deal_id.")
        document = document_by_id.get(passage["document_id"])
        if document is None:
            raise ValueError(
                f"Passage {passage_id} references unknown document_id={passage['document_id']!r}."
            )
        if _canonical_url(passage["source_url"]) != _canonical_url(document["url"]):
            raise ValueError(
                f"Passage {passage_id} source_url does not match its retrieved document URL."
            )
        if not passage["text"]:
            raise ValueError(f"Passage {passage_id} has blank text.")


def _parse_bool(value: str, field: str) -> bool:
    normalized = value.lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{field} must be a boolean value, got {value!r}.")


def _parse_nonnegative_float(value: str, field: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{field} must be numeric, got {value!r}.") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be finite and nonnegative, got {value!r}.")
    return number


def _parse_nonnegative_int(value: str, field: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an integer, got {value!r}.") from error
    if number < 0:
        raise ValueError(f"{field} must be nonnegative, got {value!r}.")
    return number


def _validate_assignments(
    assignments: list[dict[str, str]],
    passage_by_id: dict[str, dict[str, str]],
) -> None:
    seen: set[tuple[str, str]] = set()
    metadata: dict[str, str] = {}
    primary_by_passage: Counter[str] = Counter()
    for row in assignments:
        topic_id = row["topic_id"]
        passage_id = row["passage_id"]
        if not topic_id or not passage_id:
            raise ValueError("Topic assignments require nonblank topic_id and passage_id.")
        key = (passage_id, topic_id)
        if key in seen:
            raise ValueError(f"Duplicate passage/topic assignment: {key}")
        seen.add(key)
        passage = passage_by_id.get(passage_id)
        if passage is None:
            raise ValueError(f"Topic assignment references unknown passage_id={passage_id!r}.")
        for field in ("deal_id", "document_id", "source_url"):
            actual = row[field]
            expected = passage[field]
            if field == "source_url":
                actual = _canonical_url(actual)
                expected = _canonical_url(expected)
            if actual != expected:
                raise ValueError(
                    f"Topic assignment for {passage_id} has {field} inconsistent with passage."
                )
        _parse_nonnegative_float(row["topic_weight"], "topic_weight")
        is_primary = _parse_bool(row["primary_topic"], "primary_topic")
        if is_primary:
            primary_by_passage[passage_id] += 1
        prior_terms = metadata.setdefault(topic_id, row["top_terms"])
        if prior_terms != row["top_terms"]:
            raise ValueError(f"Topic {topic_id} has inconsistent top_terms values.")
    duplicate_primary = sorted(
        passage_id for passage_id, count in primary_by_passage.items() if count > 1
    )
    if duplicate_primary:
        raise ValueError(f"Passages have multiple primary topics: {duplicate_primary}")


def _validate_deal_topics(
    deal_topics: list[dict[str, str]],
    passage_by_id: dict[str, dict[str, str]],
    assignments: list[dict[str, str]],
    expected_deal_count: int,
) -> dict[str, dict[str, str]]:
    if not deal_topics:
        raise ValueError("Deal topics CSV must contain one or more rows.")
    topic_ids = {row["topic_id"] for row in assignments}
    assigned_deal_topics = {(row["deal_id"], row["topic_id"]) for row in assignments}
    seen: set[tuple[str, str]] = set()
    deals: dict[str, dict[str, str]] = {}
    zero_states: dict[str, list[str]] = defaultdict(list)
    for row in deal_topics:
        deal_id = row["deal_id"]
        if not deal_id:
            raise ValueError("Deal topics CSV has a row with blank deal_id.")
        topic_id = row["topic_id"]
        key = (deal_id, topic_id)
        if key in seen:
            raise ValueError(f"Duplicate deal/topic row: {key}")
        seen.add(key)
        weight_sum = _parse_nonnegative_float(row["weight_sum"], "weight_sum")
        normalized_weight = _parse_nonnegative_float(
            row["normalized_weight"], "normalized_weight"
        )
        primary_count = _parse_nonnegative_int(
            row["primary_passage_count"], "primary_passage_count"
        )
        if normalized_weight > 1:
            raise ValueError("normalized_weight must be between 0 and 1.")
        if topic_id:
            if row["zero_state"]:
                raise ValueError(f"Modeled deal/topic row {key} cannot also have zero_state.")
            if topic_id not in topic_ids:
                raise ValueError(f"Deal/topic row references unknown topic_id={topic_id!r}.")
            if key not in assigned_deal_topics:
                raise ValueError(f"Deal/topic row {key} has no source-linked passage assignment.")
        else:
            if not row["zero_state"]:
                raise ValueError(
                    f"Deal {deal_id} requires zero_state when topic_id is blank."
                )
            if weight_sum or normalized_weight or primary_count:
                raise ValueError(f"Zero-state deal {deal_id} must have zero topic values.")
            zero_states[deal_id].append(row["zero_state"])
        prior = deals.setdefault(
            deal_id,
            {
                "deal_id": deal_id,
                "acquirer_name": row.get("acquirer_name", ""),
                "target_name": row.get("target_name", ""),
            },
        )
        for name_field in ("acquirer_name", "target_name"):
            value = row.get(name_field, "")
            if prior[name_field] and value and prior[name_field] != value:
                raise ValueError(f"Deal {deal_id} has inconsistent {name_field} values.")
            if value:
                prior[name_field] = value
    if len(deals) != expected_deal_count:
        raise ValueError(
            f"Deal topics CSV must represent exactly {expected_deal_count} deals; "
            f"found {len(deals)}."
        )
    mixed = sorted(
        deal_id
        for deal_id in zero_states
        if any(row["deal_id"] == deal_id and row["topic_id"] for row in deal_topics)
    )
    if mixed:
        raise ValueError(f"Deals cannot contain both topic rows and zero-state rows: {mixed}")
    roster = set(deals)
    passage_deals = {row["deal_id"] for row in passage_by_id.values()}
    assignment_deals = {row["deal_id"] for row in assignments}
    unknown = sorted((passage_deals | assignment_deals) - roster)
    if unknown:
        raise ValueError(f"Passage/topic data contain deals absent from deal matrix: {unknown}")
    return deals


def _validate_diagnostics(diagnostics: list[dict[str, str]]) -> bool:
    if not diagnostics:
        raise ValueError("Diagnostics CSV must contain explicit gate rows.")
    for row in diagnostics:
        if not row["stage"] or not row["name"]:
            raise ValueError("Each diagnostic requires nonblank stage and name.")
        status = row["status"].lower()
        if status not in _DIAGNOSTIC_STATUSES:
            raise ValueError(
                f"Diagnostic status must be one of {sorted(_DIAGNOSTIC_STATUSES)}, "
                f"got {row['status']!r}."
            )
        assert_descriptive_claims(row["detail"])
    return all(row["status"].lower() == "pass" for row in diagnostics)


def _topic_review_rows(
    assignments: list[dict[str, str]], representative_limit: int
) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in assignments:
        grouped[row["topic_id"]].append(row)
    output: list[dict[str, str]] = []
    for topic_id in sorted(grouped):
        rows = grouped[topic_id]
        representatives = _representatives(rows, representative_limit)
        first = rows[0]
        output.append(
            {
                "topic_id": topic_id,
                "method": first.get("method", "nmf") or "nmf",
                "top_terms": first["top_terms"],
                "passage_count": str(len({row["passage_id"] for row in rows})),
                "deal_count": str(len({row["deal_id"] for row in rows})),
                "representative_passage_ids": "|".join(
                    row["passage_id"] for row in representatives
                ),
                "representative_source_urls": "|".join(
                    row["source_url"] for row in representatives
                ),
                "model_coherence": first.get("coherence", ""),
                "stability_recovery_rate": first.get("stability_recovery_rate", ""),
                "reviewer_topic_label": "",
                "coherence_score_1_to_5": "",
                "reviewer_id": "",
                "review_status": "pending",
                "reviewer_notes": "",
            }
        )
    return output


def _representatives(
    rows: list[dict[str, str]], representative_limit: int
) -> list[dict[str, str]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            not _parse_bool(row["primary_topic"], "primary_topic"),
            -_parse_nonnegative_float(row["topic_weight"], "topic_weight"),
            row["passage_id"],
        ),
    )
    representatives: list[dict[str, str]] = []
    seen_passages: set[str] = set()
    for row in ordered:
        if row["passage_id"] in seen_passages:
            continue
        seen_passages.add(row["passage_id"])
        representatives.append(row)
        if len(representatives) == representative_limit:
            break
    return representatives


def _authored_report_sections(
    passages: list[dict[str, str]],
    assignments: list[dict[str, str]],
    deal_topics: list[dict[str, str]],
    diagnostics: list[dict[str, str]],
    deals: dict[str, dict[str, str]],
    gate_passed: bool,
) -> list[str]:
    verdict = "PASS" if gate_passed else "FAIL"
    passed_count = sum(row["status"].lower() == "pass" for row in diagnostics)
    gate_lines = [
        "# Employee disclosure topic report",
        (
            "## Gate verdict\n\n"
            f"**{verdict}** — {passed_count} of {len(diagnostics)} diagnostic gates passed."
        ),
    ]
    for row in sorted(diagnostics, key=lambda item: (item["stage"], item["name"])):
        status = row["status"].upper()
        value = row["value"] or "not reported"
        detail = f" — {row['detail']}" if row["detail"] else ""
        gate_lines.append(
            f"- **{_escape_inline(row['stage'])} / {_escape_inline(row['name'])}: "
            f"{status}** ({_escape_inline(value)}){_escape_inline(detail)}"
        )
    if gate_passed:
        gate_lines.append(
            "The prespecified descriptive gate passed; the topic structure may proceed to "
            "human interpretation and held-out validation."
        )
    else:
        gate_lines.append(
            "The prespecified descriptive gate failed. Treat the topic output as a method "
            "diagnostic and do not present it as a validated taxonomy."
        )

    boundary = (
        "## Interpretation boundary\n\n"
        "This is a descriptive-only analysis of employee-related language in retrieved public "
        "filings. It does not estimate workforce outcomes or establish cause and effect. "
        "Employee behavior is outside this dataset. Public silence is not evidence that an "
        "arrangement was absent, and an observed clause is not evidence that it achieved its "
        "stated purpose."
    )

    passage_counts = Counter(row["deal_id"] for row in passages)
    passage_sources: dict[str, list[dict[str, str]]] = defaultdict(list)
    for passage in passages:
        passage_sources[passage["deal_id"]].append(passage)
    assignment_sources: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for assignment in assignments:
        assignment_sources[(assignment["deal_id"], assignment["topic_id"])].append(assignment)
    profile_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    zero_states: dict[str, str] = {}
    for row in deal_topics:
        if row["topic_id"]:
            profile_rows[row["deal_id"]].append(row)
        else:
            zero_states[row["deal_id"]] = row["zero_state"]
    table = [
        "## Deal coverage",
        "| Deal | Qualifying passages | Topic profile | Coverage state |",
        "| --- | ---: | --- | --- |",
    ]
    for deal_id in sorted(deals):
        deal = deals[deal_id]
        display = _deal_display(deal)
        deal_passages = sorted(passage_sources.get(deal_id, []), key=lambda row: row["passage_id"])
        if deal_passages:
            display = f"{display} {_source_citation(deal_passages[0])}"
        else:
            display = f"{display} — pipeline zero state; no document-content claim"
        profiles = sorted(
            profile_rows.get(deal_id, []),
            key=lambda row: (
                -_parse_nonnegative_float(row["normalized_weight"], "normalized_weight"),
                row["topic_id"],
            ),
        )
        if profiles:
            rendered_profiles: list[str] = []
            for row in profiles:
                sources = sorted(
                    assignment_sources[(deal_id, row["topic_id"])],
                    key=lambda item: (
                        -_parse_nonnegative_float(item["topic_weight"], "topic_weight"),
                        item["passage_id"],
                    ),
                )
                rendered_profiles.append(
                    f"{row['topic_id']} {_format_percent(row['normalized_weight'])} "
                    f"(primary n={row['primary_passage_count']}) {_source_citation(sources[0])}"
                )
            profile = "; ".join(rendered_profiles)
            coverage_state = "modeled"
        else:
            profile = "—"
            coverage_state = zero_states[deal_id].replace("_", " ")
        table.append(
            f"| {_escape_table(display)} | {passage_counts[deal_id]} | "
            f"{_escape_table(profile)} | {_escape_table(coverage_state)} |"
        )

    method_note = (
        "## Reproducibility note\n\n"
        f"The report covers {len(deals)} deals, {len(passages)} canonical passages, and "
        f"{len({row['topic_id'] for row in assignments})} discovered topics. Topic labels remain "
        "blank in the review template until a reviewer examines the source-linked representatives."
    )
    return ["\n\n".join(gate_lines), boundary, "\n".join(table), method_note]


def _representative_passage_section(
    assignments: list[dict[str, str]],
    passage_by_id: dict[str, dict[str, str]],
    deals: dict[str, dict[str, str]],
    representative_limit: int,
) -> str:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in assignments:
        grouped[row["topic_id"]].append(row)
    lines = ["## Source-linked representative passages"]
    if not grouped:
        lines.append(
            "No modeled topic assignments were available; see the deal zero states and gate verdict."
        )
        return "\n\n".join(lines)
    for topic_id in sorted(grouped):
        rows = grouped[topic_id]
        terms = rows[0]["top_terms"] or "terms unavailable"
        lines.append(f"### {topic_id}\n\nTop terms: {_escape_inline(terms)}")
        for index, assignment in enumerate(_representatives(rows, representative_limit), start=1):
            passage = passage_by_id[assignment["passage_id"]]
            deal = deals[passage["deal_id"]]
            excerpt = _excerpt(passage["text"])
            lines.append(
                f"{index}. {_escape_inline(_deal_display(deal))} — "
                f"{_source_citation(passage)} "
                f"(passage `{passage['passage_id']}`)\n\n> {excerpt}"
            )
    return "\n\n".join(lines)


def _deal_display(deal: dict[str, str]) -> str:
    acquirer = deal.get("acquirer_name", "")
    target = deal.get("target_name", "")
    if acquirer and target:
        return f"{acquirer}–{target} ({deal['deal_id']})"
    if target:
        return f"{target} ({deal['deal_id']})"
    return deal["deal_id"]


def _format_percent(value: str) -> str:
    return f"{_parse_nonnegative_float(value, 'normalized_weight') * 100:.1f}%"


def _source_citation(row: dict[str, str]) -> str:
    heading = row.get("heading", "") or "exact SEC document"
    return f"([{_escape_inline(heading)}]({row['source_url']}))"


def _excerpt(value: str, limit: int = 360) -> str:
    normalized = " ".join(value.split()).replace(">", "&gt;")
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _escape_inline(value: str) -> str:
    return value.replace("\n", " ").replace("`", "\\`")


def _escape_table(value: str) -> str:
    return _escape_inline(value).replace("|", "\\|")
