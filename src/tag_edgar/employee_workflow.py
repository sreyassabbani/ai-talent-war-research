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
from .corpus_validation import CorpusValidationState, resolve_corpus_validation
from .employee_corpus import CorpusDocument, build_employee_corpus, parse_document
from .employee_report import build_employee_report, write_employee_report
from .employee_topics import (
    AssignmentRow,
    EmployeeTopicResult,
    TopicModelConfig,
    analyze_employee_topics_csv,
)
from .source_links import text_fragment_url

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
    "source_highlight_url",
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
    "exclusion_reason",
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
    "source_highlight_url",
    "heading",
    "block_start",
    "block_end",
    "char_start",
    "char_end",
    "inclusion_status",
    "exclusion_reason",
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

DOCUMENT_ELIGIBILITY_FIELDS = [
    "deal_id",
    "document_id",
    "accession_number",
    "filing_form",
    "document_type",
    "source_url",
    "transaction_evidence_hits",
    "target_name_proximity",
    "transaction_language_found",
    "inclusion_status",
    "decision_reason",
]

MANUAL_SOURCE_VALIDATION_FIELDS = [
    "deal_id",
    "source_url",
    "manual_employee_term_code",
    "expected_positive",
    "retrieved_document_id",
    "document_inclusion_status",
    "qualifying_passage_count",
    "validation_status",
]

TOPIC_ASSIGNMENT_FIELDS = [
    "passage_id",
    "canonical_passage_id",
    "deal_id",
    "document_id",
    "document_family_id",
    "source_url",
    "source_highlight_url",
    "topic_id",
    "topic_weight",
    "primary_topic",
    "top_terms",
    "method",
    "coherence",
    "stability_recovery_rate",
    "disclosure_salience",
    "assignment_specificity",
    "top_positive_residual_terms",
    "top_positive_residual_scores",
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
    "disclosure_salience",
    "assignment_specificity",
    "top_positive_residual_terms",
    "top_positive_residual_scores",
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
BOOTSTRAP_STABILITY_FIELDS = [
    "replicate_id",
    "topic_id",
    "aligned_topic_id",
    "cosine_similarity",
    "recovered",
]
BOOTSTRAP_SUMMARY_FIELDS = [
    "topic_id",
    "replicate_count",
    "recurrence_count",
    "recovery_rate",
    "median_cosine_similarity",
]
EMBEDDING_ROBUSTNESS_FIELDS = [
    "passage_id",
    "deal_id",
    "method",
    "cluster_id",
    "noise",
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
    rows = [
        row for row in _read_rows(review_csv) if row.get("pilot_status", "").lower() == "selected"
    ]
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


def _target_aliases(target_name: str) -> tuple[str, ...]:
    normalized = " ".join(re.findall(r"[a-z0-9]+", target_name.casefold()))
    if not normalized:
        return ()
    suffixes = {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "llc",
        "ltd",
        "limited",
        "plc",
        "company",
        "co",
    }
    tokens = normalized.split()
    stripped = " ".join(token for token in tokens if token not in suffixes)
    aliases = {normalized, stripped}
    if len(tokens) == 2 and tokens[-1] in suffixes and len(tokens[0]) >= 5:
        aliases.add(tokens[0])
    return tuple(sorted(alias for alias in aliases if len(alias) >= 4))


def _party_aliases(party_name: str) -> tuple[str, ...]:
    aliases = set(_target_aliases(party_name))
    normalized = " ".join(re.findall(r"[a-z0-9]+", party_name.casefold()))
    for token in normalized.split():
        if len(token) >= 5 and token not in _GENERIC_ENTITY_TOKENS:
            aliases.add(token)
    return tuple(sorted(aliases, key=lambda alias: (-len(alias), alias)))


def _normalize_party_names(model_text: str, acquirer_name: str, target_name: str) -> str:
    normalized = model_text
    for alias in (*_party_aliases(acquirer_name), *_party_aliases(target_name)):
        normalized = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", " entitytoken ", normalized)
    return " ".join(normalized.split())


def _has_target_proximity(text: str, target_name: str) -> bool:
    normalized = " ".join(re.findall(r"[a-z0-9]+", text.casefold()))
    return any(
        re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized)
        for alias in _target_aliases(target_name)
    )


def _document_eligibility(
    row: Mapping[str, str],
    filing_form: str,
    transaction_accessions: frozenset[str],
    transaction_evidence_hits: int,
    target_name: str,
    text: str,
) -> tuple[bool, str, bool, bool]:
    document_type = row.get("document_type", "").upper()
    accession = row.get("accession_number", "")
    target_proximity = _has_target_proximity(text, target_name)
    transaction_language = bool(_TRANSACTION_LANGUAGE.search(text))
    employee_action = bool(_ACQUISITION_EMPLOYEE_ACTION.search(text))
    if document_type.startswith("EX-2."):
        return True, "included_ex2_transaction_agreement", target_proximity, transaction_language
    if filing_form.upper() in _TRANSACTION_FORMS:
        return True, "included_transaction_specific_form", target_proximity, transaction_language
    if transaction_evidence_hits:
        return True, "included_transaction_evidence", target_proximity, transaction_language
    if (
        filing_form.upper() == "8-K"
        and document_type.startswith("EX-")
        and not document_type.startswith(("EX-2.", "EX-99."))
    ):
        if target_proximity and transaction_language and employee_action:
            return (
                True,
                "included_transaction_employee_action_exhibit",
                target_proximity,
                transaction_language,
            )
        return (
            False,
            "excluded_nontransaction_8k_exhibit",
            target_proximity,
            transaction_language,
        )
    if accession in transaction_accessions:
        return True, "included_transaction_accession", target_proximity, transaction_language
    if target_proximity and transaction_language:
        return True, "included_target_transaction_proximity", target_proximity, transaction_language
    return False, "excluded_unrelated_event_window_document", target_proximity, transaction_language


def _passage_eligibility(
    screen_terms: Sequence[str], model_text: str, raw_text: str | None = None
) -> tuple[bool, str]:
    term_set = set(screen_terms)
    # Keep the screening universe broad, but do not model labels, table-of-contents entries, or
    # other navigation fragments as if they were employee provisions. The audit found that these
    # fragments were a major source of false positives.
    if _NAVIGATION_CONTEXT.search(model_text) and not _EMPLOYEE_TREATMENT_CONTEXT.search(model_text):
        return False, "excluded_navigation_or_index_fragment"
    if raw_text is not None and _is_bare_employee_caption(raw_text):
        return False, "excluded_bare_employee_caption"
    if _SAFE_HARBOR_CONTEXT.search(model_text):
        return False, "excluded_safe_harbor_or_forward_looking_context"
    if _ACCOUNTING_CONTEXT.search(model_text):
        return False, "excluded_accounting_or_financial_context"
    if _NONEMPLOYEE_UNION_CONTEXT.search(model_text) and not _LABOR_CONTEXT.search(model_text):
        return False, "excluded_nonemployee_union_context"
    if (
        _PRIVACY_IP_CONTEXT.search(model_text)
        and not term_set & _STRONG_EMPLOYEE_SCREEN_TERMS
        and not _LEADERSHIP_CONTINUITY_CONTEXT.search(model_text)
    ):
        return False, "excluded_nonemployee_privacy_or_ip_context"
    substantive_action = bool(
        _EMPLOYEE_TREATMENT_CONTEXT.search(model_text)
        or _LEADERSHIP_CONTINUITY_CONTEXT.search(model_text)
        or _COMPENSATION_CONTEXT.search(model_text)
    )
    if _PROXY_SOLICITATION_CONTEXT.search(model_text) and not substantive_action:
        return False, "excluded_proxy_solicitation_logistics"
    if _LITIGATION_CONTEXT.search(model_text) and not substantive_action:
        return False, "excluded_litigation_allegation_context"
    if _GENERIC_REPRESENTATIVE_DEFINITION.search(model_text) and not substantive_action:
        return False, "excluded_generic_representative_definition"
    substantive_terms = term_set - _GENERIC_SCREEN_TERMS
    if not substantive_terms:
        award_terms = term_set & _AWARD_SCREEN_TERMS
        contextual = bool(
            (award_terms and _AWARD_TREATMENT_CONTEXT.search(model_text))
            or _EMPLOYEE_TREATMENT_CONTEXT.search(model_text)
            or _HUMAN_CONTEXT.search(model_text)
            or _GENERIC_PEOPLE_CONTEXT.search(model_text)
            or _COMPENSATION_CONTEXT.search(model_text)
        )
        if not contextual:
            return False, "excluded_generic_term_without_people_context"
    return True, "included_employee_context"


_MODEL_TOKEN = re.compile(r"[a-z][a-z0-9]*(?:[-'][a-z0-9]+)*")
_TRANSACTION_LANGUAGE = re.compile(
    r"\b(?:acqui(?:re|red|res|ring|sition)|merger|business combination|tender offer|"
    r"purchase agreement|transaction)\b",
    re.IGNORECASE,
)
_ACQUISITION_EMPLOYEE_ACTION = re.compile(
    r"\b(?:acquisition|acquire[ds]?|merger|transaction|closing|effective time)\b.{0,240}"
    r"\b(?:continu(?:ing|ed) employees?|continued (?:employment|service)|remain employed|"
    r"employee benefits?|retention bonus|transaction bonus|equity awards?|stock options?|"
    r"restricted stock units?|severance|management team)\b|"
    r"\b(?:continu(?:ing|ed) employees?|continued (?:employment|service)|remain employed|"
    r"employee benefits?|retention bonus|transaction bonus|equity awards?|stock options?|"
    r"restricted stock units?|severance|management team)\b.{0,240}"
    r"\b(?:acquisition|acquire[ds]?|merger|transaction|closing|effective time)\b",
    re.IGNORECASE | re.DOTALL,
)
_ACCOUNTING_CONTEXT = re.compile(
    r"\b(?:stock[- ]based compensation expense|share[- ]based compensation expense|"
    r"consolidated statements?|unaudited|three months ended|six months ended|fiscal year|"
    r"non-gaap|cash flows?|operating expenses?|compensation expense|in millions)\b",
    re.IGNORECASE,
)
_SAFE_HARBOR_CONTEXT = re.compile(
    r"\b(?:safe harbor|forward-looking statements?|actual results (?:may|could) differ|"
    r"risks? and uncertainties|cautionary statement|sec filings)\b",
    re.IGNORECASE,
)
_HUMAN_CONTEXT = re.compile(
    r"\b(?:employment|severance|"
    r"continued service|remain employed|benefit plans?|pension|labor|labour|union|"
    r"award holders?|participants?)\b",
    re.IGNORECASE,
)
_GENERIC_PEOPLE_CONTEXT = re.compile(
    r"\b(?:remain|continue|serve|report(?:ing)? to|appoint(?:ed|ment)?|lead(?:er|ership)?|"
    r"employ(?:ed|ment)?|terminate)\b",
    re.IGNORECASE,
)
_LEADERSHIP_CONTINUITY_CONTEXT = re.compile(
    r"\b(?:chief executive|chief financial|ceo|cfo|executive|officer|founder|management)\b"
    r".{0,100}\b(?:remain|continue|serve|report(?:ing)? to|appoint(?:ed|ment)?|lead)\b|"
    r"\b(?:remain|continue|serve|report(?:ing)? to|appoint(?:ed|ment)?|lead)\b"
    r".{0,100}\b(?:chief executive|chief financial|ceo|cfo|executive|officer|founder|"
    r"management)\b",
    re.IGNORECASE,
)
_COMPENSATION_CONTEXT = re.compile(
    r"\b(?:retention|stay|transaction) bonus(?:es)?\b|"
    r"\b(?:salary|salaries|wages?|payroll|severance|incentive)\b|"
    r"\b(?:employees?|executive|officers?|personnel|management)\b.{0,80}\bcompensation\b|"
    r"\bcompensation\b.{0,80}\b(?:employees?|executive|officers?|personnel|management)\b",
    re.IGNORECASE,
)
_EMPLOYEE_TREATMENT_CONTEXT = re.compile(
    r"\b(?:continuing employees?|continued employment|continued service|remain employed|"
    r"post-transaction employment|employee benefits?|benefit plans?|retention bonus|"
    r"transaction bonus|severance|salary|salaries|wages?|payroll|collective bargaining)\b|"
    r"\b(?:employees?|executive|officers?|personnel|workforce|management)\b.{0,100}"
    r"\b(?:remain|continue|retain|receive|provide|pay|compensation|bonus|benefits?|severance|"
    r"terminate|employment|service)\b|"
    r"\b(?:equity awards?|stock options?|restricted stock units?|rsus?)\b.{0,100}"
    r"\b(?:effective time|convert(?:ed)?|assum(?:e|ed)|cancel(?:led)?|vest(?:ed|ing)?|"
    r"cash(?:ed)? out|continued service)\b",
    re.IGNORECASE,
)
_PROXY_SOLICITATION_CONTEXT = re.compile(
    r"\b(?:solicit(?:ed|ing|ation)? proxies|proxy solicitation|proxies may be solicited|"
    r"bear the (?:entire )?cost of soliciting|by mail|telephone|facsimile|messenger)\b",
    re.IGNORECASE,
)
_LITIGATION_CONTEXT = re.compile(
    r"\b(?:plaintiffs?|defendants?|complaint|alleg(?:e|ed|ation)|wrongful conduct|"
    r"liable pursuant|violat(?:e|ed|or|ion)|cause of action|individual defendants)\b",
    re.IGNORECASE,
)
_GENERIC_REPRESENTATIVE_DEFINITION = re.compile(
    r"\brepresentatives?\b.{0,40}\b(?:shall )?mean\b|"
    r"\b(?:shall )?mean\b.{0,180}\b(?:directors?|officers?|employees?|agents?|advisors?|"
    r"consultants?)\b.{0,80}\brepresentatives?\b|"
    r"\b(?:directors?|officers?)\b.{0,100}\bemployees?\b.{0,100}"
    r"\b(?:agents?|advisors?|consultants?|representatives?)\b",
    re.IGNORECASE,
)
_NONEMPLOYEE_UNION_CONTEXT = re.compile(
    r"\b(?:european union|united nations|union security council|eu member state)\b",
    re.IGNORECASE,
)
_LABOR_CONTEXT = re.compile(
    r"\b(?:employees?|labor|labour|collective bargaining|trade union|workforce|workers?)\b",
    re.IGNORECASE,
)
_PRIVACY_IP_CONTEXT = re.compile(
    r"\b(?:privacy polic(?:y|ies)|personal information|data protection|source code|"
    r"intellectual property|trade secrets?|non-disclosure|confidentiality|"
    r"information security)\b",
    re.IGNORECASE,
)
_AWARD_TREATMENT_CONTEXT = re.compile(
    r"\b(?:award holders?|participants?|employees?|service|closing|effective time|converted?|"
    r"cancelled?|assumed?|cashed out|vested|unvested|forfeit(?:ed)?|terminat(?:e|ed|ion))\b",
    re.IGNORECASE,
)
_NAVIGATION_CONTEXT = re.compile(r"\b(?:table of contents|exhibits?)\b", re.IGNORECASE)
_CAPTION_ACTION = re.compile(
    r"\b(?:is|are|was|were|be|been|being|shall|will|may|must|means?|include[ds]?|"
    r"provide[ds]?|receive[ds]?|convert(?:ed|s)?|assum(?:e|ed|es)|cancel(?:led|s)?|"
    r"vest(?:ed|ing|s)?|forfeit(?:ed|s)?|terminat(?:e|ed|ion))\b",
    re.IGNORECASE,
)


def _is_bare_employee_caption(raw_text: str) -> bool:
    """Identify short employee-labelled headings that contain no operative provision."""
    words = _MODEL_TOKEN.findall(raw_text)
    return bool(words) and len(words) <= 12 and not _CAPTION_ACTION.search(raw_text)
_AWARD_SCREEN_TERMS = frozenset(
    {
        "equity award",
        "stock option",
        "restricted stock",
        "restricted stock unit",
        "rsu",
        "vesting",
        "incentive award",
    }
)
_GENERIC_SCREEN_TERMS = frozenset(
    {
        "employee",
        "employees",
        "personnel",
        "workforce",
        "worker",
        "workers",
        "executive officer",
        "management team",
        "founder",
        "compensation",
        "bonus",
        "change in control",
        "retention",
        "retain",
        *_AWARD_SCREEN_TERMS,
    }
)
_STRONG_EMPLOYEE_SCREEN_TERMS = frozenset(
    {
        "employment",
        "continued employment",
        "continued service",
        "remain employed",
        "key employee",
        "stay bonus",
        "transaction bonus",
        "salary",
        "wages",
        "payroll",
        "severance",
        "benefit plan",
        "employee benefit",
        "pension",
        "collective bargaining",
        "union",
        "labor",
        "labour",
        *_AWARD_SCREEN_TERMS,
    }
)
_GENERIC_ENTITY_TOKENS = frozenset(
    {
        "company",
        "group",
        "holdings",
        "interactive",
        "solutions",
        "software",
        "systems",
        "technologies",
        "technology",
        "communications",
    }
)
_TRANSACTION_FORMS = frozenset(
    {
        "S-4",
        "S-4/A",
        "424B3",
        "PREM14A",
        "PREM14A/A",
        "DEFM14A",
        "DEFM14A/A",
        "SC 14D9",
        "SC 14D9/A",
        "SC TO-T",
        "SC TO-T/A",
        "SC TO-I",
        "SC TO-I/A",
        "425",
        "DEFA14A",
        "PREM14C",
        "PREM14C/A",
        "DEFM14C",
        "DEFM14C/A",
        "SC TO-C",
        "SC14D9C",
        "F-4",
        "F-4/A",
        "CB",
    }
)


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
            int.from_bytes(hashlib.sha256(f"{permutation}:{shingle}".encode()).digest()[:8], "big")
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

    # Passages whose shingle sets are identical have Jaccard similarity 1.0 with each other and
    # identical similarity to every other passage, so they always land in one family. Merging
    # them up front and then comparing only one representative per distinct shingle set gives
    # exactly the same components. It also removes the quadratic blow-up that repeated legal
    # boilerplate would otherwise cause: at 400 deals a single recurring employee-matters clause
    # can appear tens of thousands of times, and comparing every such pair does not finish.
    by_shingles: defaultdict[frozenset[str], list[str]] = defaultdict(list)
    for passage_id in sorted(passage_ids):
        by_shingles[shingles[passage_id]].append(passage_id)
    representatives: list[str] = []
    for shingle_set, group in by_shingles.items():
        if not shingle_set:
            # A passage too short to shingle never matches anything: the original size guard
            # rejects every pair when one side is empty. Keep them separate.
            representatives.extend(group)
            continue
        first = group[0]
        representatives.append(first)
        for passage_id in group[1:]:
            union(first, passage_id)

    buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)
    for passage_id in representatives:
        signature = _minhash(shingles[passage_id])
        for band in range(3):
            buckets[(band, signature[band * 4 : (band + 1) * 4])].append(passage_id)

    for bucket in buckets.values():
        for left_index, left in enumerate(bucket):
            for right in bucket[left_index + 1 :]:
                # Union is idempotent, so a pair already joined through another band or a
                # transitive match needs no similarity computation.
                if find(left) == find(right):
                    continue
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


def _canonical_sec_url(value: str) -> str:
    return canonical_document_url("https://www.sec.gov/", value).replace(
        "https://www.sec.gov/", "https://sec.gov/"
    )


def _manual_source_validation(
    manual_coding_csv: Path | None,
    document_rows: Mapping[str, Mapping[str, object]],
    eligibility_by_document: Mapping[tuple[str, str], bool],
    source_rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int, tuple[str, ...]]:
    if manual_coding_csv is None:
        return [], 0, ()
    manual_rows = _read_rows(manual_coding_csv)
    documents_by_url: dict[tuple[str, str], str] = {}
    for document_id, document in document_rows.items():
        deal_id = str(document["deal_id"])
        documents_by_url[(deal_id, _canonical_sec_url(str(document["url"])))] = document_id

    output: list[dict[str, object]] = []
    failures: list[str] = []
    positive_count = 0
    qualifying_passages = Counter(
        (str(row["deal_id"]), str(row["document_id"]))
        for row in source_rows
        if str(row.get("inclusion_status", "")).lower() == "included"
    )
    for row in sorted(manual_rows, key=lambda item: item.get("deal_id", "")):
        deal_id = row.get("deal_id", "")
        source_url = row.get("source_url", "")
        manual_code = row.get("manual_employee_term_code", "")
        expected_positive = bool(manual_code) and not manual_code.casefold().startswith("no_")
        positive_count += int(expected_positive)
        document_id = (
            documents_by_url.get((deal_id, _canonical_sec_url(source_url)), "")
            if source_url
            else ""
        )
        included = bool(document_id) and eligibility_by_document.get((deal_id, document_id), False)
        qualifying_count = qualifying_passages[(deal_id, document_id)] if document_id else 0
        if not document_id:
            status = "source_not_retrieved"
        elif expected_positive and not included:
            status = "positive_source_excluded"
        elif expected_positive and not qualifying_count:
            status = "positive_source_has_no_qualifying_passage"
        else:
            status = "pass"
        if expected_positive and status != "pass":
            failures.append(f"{deal_id}: {status}")
        output.append(
            {
                "deal_id": deal_id,
                "source_url": source_url,
                "manual_employee_term_code": manual_code,
                "expected_positive": str(expected_positive).lower(),
                "retrieved_document_id": document_id,
                "document_inclusion_status": "included" if included else "excluded",
                "qualifying_passage_count": qualifying_count,
                "validation_status": status,
            }
        )
    return output, positive_count, tuple(failures)


def build_employee_corpus_workflow(
    review_csv: Path,
    runs_dir: Path,
    output_dir: Path,
    cache_dir: Path,
    *,
    context_blocks: int = 0,
    max_block_words: int = 220,
    manual_coding_csv: Path | None = None,
) -> WorkflowSummary:
    """Build the source-linked passage corpus entirely from reviewed runs and cached bodies."""
    deals = _selected_deals(review_csv)
    corpus_documents: list[CorpusDocument] = []
    document_rows: dict[str, dict[str, object]] = {}
    document_text_rows: list[dict[str, object]] = []
    document_eligibility_rows: list[dict[str, object]] = []
    eligibility_by_document: dict[tuple[str, str], bool] = {}
    family_by_occurrence: dict[tuple[str, str], str] = {}

    for deal in deals:
        deal_id = deal["deal_id"]
        documents_path = runs_dir / deal_id / "documents.csv"
        if not documents_path.exists():
            continue
        filings_path = runs_dir / deal_id / "filings.csv"
        filing_rows = _read_rows(filings_path) if filings_path.exists() else []
        form_by_accession = {
            row.get("accession_number", ""): row.get("form", "").upper() for row in filing_rows
        }
        evidence_path = runs_dir / deal_id / "evidence.csv"
        evidence_rows = _read_rows(evidence_path) if evidence_path.exists() else []
        transaction_hits = Counter(
            row.get("document_id", "")
            for row in evidence_rows
            if row.get("category", "") == "transaction"
        )
        all_document_rows = _read_rows(documents_path)
        transaction_accessions = frozenset(
            row.get("accession_number", "")
            for row in all_document_rows
            if row.get("document_type", "").upper().startswith("EX-2.")
            or form_by_accession.get(row.get("accession_number", ""), "") in _TRANSACTION_FORMS
        )
        for row in all_document_rows:
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
                raise ValueError(
                    f"Document {document_id} has inconsistent source URLs across deals."
                )
            document_rows.setdefault(document_id, combined_row)

            body_path, metadata_path = _cache_paths(cache_dir, url)
            if not body_path.exists():
                eligibility_by_document[(deal_id, document_id)] = False
                document_eligibility_rows.append(
                    {
                        "deal_id": deal_id,
                        "document_id": document_id,
                        "accession_number": row.get("accession_number", ""),
                        "filing_form": form_by_accession.get(row.get("accession_number", ""), ""),
                        "document_type": row.get("document_type", ""),
                        "source_url": url,
                        "transaction_evidence_hits": transaction_hits[document_id],
                        "target_name_proximity": "false",
                        "transaction_language_found": "false",
                        "inclusion_status": "excluded",
                        "decision_reason": "excluded_cache_missing",
                    }
                )
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
                eligibility_by_document[(deal_id, document_id)] = False
                document_eligibility_rows.append(
                    {
                        "deal_id": deal_id,
                        "document_id": document_id,
                        "accession_number": row.get("accession_number", ""),
                        "filing_form": form_by_accession.get(row.get("accession_number", ""), ""),
                        "document_type": row.get("document_type", ""),
                        "source_url": url,
                        "transaction_evidence_hits": transaction_hits[document_id],
                        "target_name_proximity": "false",
                        "transaction_language_found": "false",
                        "inclusion_status": "excluded",
                        "decision_reason": "excluded_parse_error",
                    }
                )
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
            filing_form = form_by_accession.get(row.get("accession_number", ""), "")
            included, decision_reason, target_proximity, transaction_language = (
                _document_eligibility(
                    row,
                    filing_form,
                    transaction_accessions,
                    transaction_hits[document_id],
                    deal.get("target_name", ""),
                    parsed.text,
                )
            )
            eligibility_by_document[(deal_id, document_id)] = included
            document_eligibility_rows.append(
                {
                    "deal_id": deal_id,
                    "document_id": document_id,
                    "accession_number": row.get("accession_number", ""),
                    "filing_form": filing_form,
                    "document_type": row.get("document_type", ""),
                    "source_url": url,
                    "transaction_evidence_hits": transaction_hits[document_id],
                    "target_name_proximity": str(target_proximity).lower(),
                    "transaction_language_found": str(transaction_language).lower(),
                    "inclusion_status": "included" if included else "excluded",
                    "decision_reason": decision_reason,
                }
            )
            if not included:
                continue
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
    deal_by_id = {deal["deal_id"]: deal for deal in deals}
    passage_rows: list[dict[str, object]] = []
    for passage in corpus.passages:
        family_id = family_by_occurrence[(passage.deal_id, passage.document_id)]
        deal = deal_by_id[passage.deal_id]
        model_text = _normalize_party_names(
            passage.model_text,
            deal.get("acquirer_name", ""),
            deal.get("target_name", ""),
        )
        passage_included, passage_reason = _passage_eligibility(
            passage.screen_terms, model_text, passage.text
        )
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
                "source_highlight_url": text_fragment_url(passage.source_url, passage.text),
                "heading": passage.heading or "",
                "block_start": passage.block_start,
                "block_end": passage.block_end,
                "char_start": passage.char_start,
                "char_end": passage.char_end,
                "text": passage.text,
                "raw_text": passage.text,
                "model_text": model_text,
                "token_count": passage.token_count,
                "screen_terms": "|".join(passage.screen_terms),
                "content_sha256": passage.content_sha256,
                "duplicate_group": passage.duplicate_group_id,
                "duplicate_group_id": passage.duplicate_group_id,
                "occurrence_count": passage.occurrence_count,
                "inclusion_status": "included" if passage_included else "excluded",
                "exclusion_reason": "" if passage_included else passage_reason,
            }
        )
    provision_family_by_passage = _provision_family_ids(passage_rows)
    for row in passage_rows:
        row["document_family_id"] = provision_family_by_passage[str(row["passage_id"])]

    source_rows: list[dict[str, object]] = []
    passage_status = {
        str(row["passage_id"]): (
            str(row["inclusion_status"]),
            str(row["exclusion_reason"]),
        )
        for row in passage_rows
    }
    # Each occurrence records where one canonical passage was seen; the quoted text lives on the
    # passage, so the highlight target is resolved per occurrence URL using that text.
    passage_text_by_id = {str(row["passage_id"]): str(row["text"]) for row in passage_rows}
    for occurrence in corpus.occurrences:
        inclusion_status, exclusion_reason = passage_status[occurrence.passage_id]
        source_rows.append(
            {
                **asdict(occurrence),
                "source_highlight_url": text_fragment_url(
                    occurrence.source_url, passage_text_by_id.get(occurrence.passage_id, "")
                ),
                "document_family_id": provision_family_by_passage[occurrence.passage_id],
                "source_document_family_id": family_by_occurrence[
                    (occurrence.deal_id, occurrence.document_id)
                ],
                "heading": occurrence.heading or "",
                "inclusion_status": inclusion_status,
                "exclusion_reason": exclusion_reason,
            }
        )

    documents_path = output_dir / "documents.csv"
    document_texts_path = output_dir / "document_texts.csv"
    document_eligibility_path = output_dir / "document_eligibility.csv"
    passages_path = output_dir / "passages.csv"
    sources_path = output_dir / "passage_sources.csv"
    _write_rows(
        documents_path,
        DOCUMENT_FIELDS,
        sorted(document_rows.values(), key=lambda row: str(row["document_id"])),
    )
    _write_rows(
        document_texts_path,
        DOCUMENT_TEXT_FIELDS,
        sorted(document_text_rows, key=lambda row: (str(row["deal_id"]), str(row["document_id"]))),
    )
    _write_rows(
        document_eligibility_path,
        DOCUMENT_ELIGIBILITY_FIELDS,
        sorted(
            document_eligibility_rows,
            key=lambda row: (str(row["deal_id"]), str(row["document_id"])),
        ),
    )
    _write_rows(passages_path, PASSAGE_FIELDS, passage_rows)
    _write_rows(sources_path, PASSAGE_SOURCE_FIELDS, source_rows)

    manual_validation_rows, manual_positive_count, manual_validation_failures = (
        _manual_source_validation(
            manual_coding_csv,
            document_rows,
            eligibility_by_document,
            source_rows,
        )
    )
    _write_rows(
        output_dir / "manual_source_validation.csv",
        MANUAL_SOURCE_VALIDATION_FIELDS,
        manual_validation_rows,
    )
    if manual_validation_failures:
        raise ValueError(
            "Employee document gate failed manually positive source recall: "
            + "; ".join(manual_validation_failures)
        )

    extraction_counts = Counter(str(row["extraction_status"]) for row in document_text_rows)
    document_decisions = Counter(str(row["decision_reason"]) for row in document_eligibility_rows)
    passage_decisions = Counter(
        "included_employee_context"
        if row["inclusion_status"] == "included"
        else str(row["exclusion_reason"])
        for row in passage_rows
    )
    manifest: dict[str, object] = {
        "schema_version": 2,
        "review_sha256": _file_sha256(review_csv),
        "selected_deal_ids": [deal["deal_id"] for deal in deals],
        "context_blocks": context_blocks,
        "max_block_words": max_block_words,
        "documents_considered": len(document_text_rows),
        "documents_parsed": extraction_counts["parsed"],
        "documents_included": sum(
            row["inclusion_status"] == "included" for row in document_eligibility_rows
        ),
        "documents_excluded": sum(
            row["inclusion_status"] == "excluded" for row in document_eligibility_rows
        ),
        "document_decision_counts": dict(sorted(document_decisions.items())),
        "extraction_status_counts": dict(sorted(extraction_counts.items())),
        # ``corpus.passages`` contains the exact-text-deduplicated screening universe. Keep that
        # distinct from the included model universe, which topic diagnostics call canonical after
        # their own duplicate-group and non-empty-text filter.
        "screened_candidate_passages": len(corpus.passages),
        "included_screened_passages": sum(
            row["inclusion_status"] == "included" for row in passage_rows
        ),
        "excluded_screened_passages": sum(
            row["inclusion_status"] == "excluded" for row in passage_rows
        ),
        "passage_decision_counts": dict(sorted(passage_decisions.items())),
        "provision_families": len(set(provision_family_by_passage.values())),
        "passage_occurrences": len(corpus.occurrences),
        "blocks_scanned": corpus.blocks_scanned,
        "blocks_matched": corpus.blocks_matched,
        "manual_positive_sources_validated": manual_positive_count,
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
            "documents_included": sum(
                row["inclusion_status"] == "included" for row in document_eligibility_rows
            ),
            "passages": sum(row["inclusion_status"] == "included" for row in passage_rows),
            "passage_occurrences": len(corpus.occurrences),
        },
    )


def _format_number(value: float | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".10g")
    return str(value)


def _assignment_rows(
    result: EmployeeTopicResult,
    disclosure_salience: Mapping[str, float] | None = None,
    passage_text: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    topics = {row.topic_id: row for row in result.topics}
    salience = disclosure_salience or {}
    texts = passage_text or {}
    output: list[dict[str, object]] = []
    for assignment in result.assignments:
        topic = topics[assignment.topic_id]
        output.append(
            {
                **asdict(assignment),
                "source_highlight_url": text_fragment_url(
                    assignment.source_url, texts.get(assignment.passage_id, "")
                ),
                "canonical_passage_id": assignment.passage_id,
                "topic_weight": _format_number(assignment.topic_weight),
                "primary_topic": str(assignment.primary_topic).lower(),
                "top_terms": "|".join(topic.top_terms),
                "method": "nmf",
                "coherence": _format_number(topic.coherence),
                "stability_recovery_rate": _format_number(topic.stability_recovery_rate),
                "disclosure_salience": _format_number(salience.get(topic.topic_id, 0.0)),
                "assignment_specificity": _format_number(topic.assignment_specificity),
                "top_positive_residual_terms": "|".join(topic.top_positive_residual_terms),
                "top_positive_residual_scores": "|".join(
                    _format_number(value) for value in topic.top_positive_residual_scores
                ),
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
                "source_highlight_url": text_fragment_url(
                    source["source_url"], canonical.get("text", "")
                ),
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
    result: EmployeeTopicResult,
    source_passages: Sequence[dict[str, object]],
    disclosure_salience: Mapping[str, float] | None = None,
    passage_text: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    canonical_rows = _assignment_rows(result, disclosure_salience, passage_text)
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
                    "source_highlight_url": passage.get("source_highlight_url", ""),
                }
            )
    return output


def _disclosure_salience(
    deals: Sequence[dict[str, str]], rows: Sequence[dict[str, object]]
) -> dict[str, float]:
    """Mean deal-normalized topic share, with every explicit-zero deal contributing zero."""
    if not deals:
        return {}
    topic_ids = sorted({str(row["topic_id"]) for row in rows if row["topic_id"]})
    shares = {
        (str(row["deal_id"]), str(row["topic_id"])): float(str(row["normalized_weight"]))
        for row in rows
        if row["topic_id"]
    }
    return {
        topic_id: sum(shares.get((deal["deal_id"], topic_id), 0.0) for deal in deals) / len(deals)
        for topic_id in topic_ids
    }


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
    sums: defaultdict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
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


def _heatmap_svg(
    deals: Sequence[dict[str, str]], result: EmployeeTopicResult, rows: Sequence[dict[str, object]]
) -> str:
    topics = sorted(row.topic_id for row in result.topics)
    cell_width = 92
    cell_height = 28
    label_width = 230
    width = label_width + max(1, len(topics)) * cell_width + 20
    height = 72 + len(deals) * cell_height + 40
    weights = {
        (str(row["deal_id"]), str(row["topic_id"])): float(str(row["normalized_weight"]))
        for row in rows
        if row["topic_id"]
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        "<style>text{font-family:system-ui,sans-serif;font-size:12px}.title{font-size:16px;font-weight:600}.topic{font-weight:600}</style>",
        '<text class="title" x="10" y="24">Employee disclosure topic shares by deal</text>',
    ]
    if not topics:
        parts.append('<text x="10" y="50">No stable topic solution; see diagnostic output.</text>')
    for column, topic_id in enumerate(topics):
        x = label_width + column * cell_width
        parts.append(f'<text class="topic" x="{x + 4}" y="52">{escape(topic_id)}</text>')
    for row_index, deal in enumerate(deals):
        y = 60 + row_index * cell_height
        label = (
            f"{deal.get('acquirer_name', '')}–{deal.get('target_name', '')}".strip("–")
            or deal["deal_id"]
        )
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
    corpus_audit_dir: Path | None = None,
    corpus_scores_dir: Path | None = None,
) -> WorkflowSummary:
    """Analyze canonical passages and propagate their assignments to every represented deal."""
    passages_path = corpus_dir / "passages.csv"
    sources_path = corpus_dir / "passage_sources.csv"
    corpus_validation = resolve_corpus_validation(
        corpus_audit_dir,
        corpus_scores_dir,
        expected_candidate_sha256=_file_sha256(passages_path),
    )
    deals = _selected_deals(review_csv)
    canonical_passages = _read_rows(passages_path)
    source_rows = _read_rows(sources_path)
    included_source_rows = [
        row for row in source_rows if row.get("inclusion_status", "").lower() == "included"
    ]
    result = analyze_employee_topics_csv(passages_path, config)
    source_passage_rows = _source_passages(canonical_passages, included_source_rows)
    deal_topic_rows = _propagated_deal_topics(deals, result, included_source_rows)
    disclosure_salience = _disclosure_salience(deals, deal_topic_rows)
    canonical_text = {row["passage_id"]: row.get("text", "") for row in canonical_passages}
    canonical_assignment_rows = _assignment_rows(result, disclosure_salience, canonical_text)
    assignment_rows = _propagated_assignment_rows(
        result, source_passage_rows, disclosure_salience, canonical_text
    )

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
                "disclosure_salience": _format_number(disclosure_salience.get(row.topic_id, 0.0)),
                "assignment_specificity": _format_number(row.assignment_specificity),
                "top_positive_residual_terms": "|".join(row.top_positive_residual_terms),
                "top_positive_residual_scores": "|".join(
                    _format_number(value) for value in row.top_positive_residual_scores
                ),
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
    _write_rows(
        output_dir / "bootstrap_stability.csv",
        BOOTSTRAP_STABILITY_FIELDS,
        (
            {
                **asdict(row),
                "cosine_similarity": _format_number(row.cosine_similarity),
                "recovered": str(row.recovered).lower(),
            }
            for row in result.bootstrap_stability
        ),
    )
    _write_rows(
        output_dir / "bootstrap_summary.csv",
        BOOTSTRAP_SUMMARY_FIELDS,
        (
            {
                **asdict(row),
                "recovery_rate": _format_number(row.recovery_rate),
                "median_cosine_similarity": _format_number(row.median_cosine_similarity),
            }
            for row in result.bootstrap_summary
        ),
    )
    _write_rows(
        output_dir / "embedding_robustness_assignments.csv",
        EMBEDDING_ROBUSTNESS_FIELDS,
        (
            {**asdict(row), "noise": str(row.noise).lower()}
            for row in result.embedding_robustness_assignments
        ),
    )
    heatmap_path = output_dir / "deal_topic_heatmap.svg"
    heatmap_path.parent.mkdir(parents=True, exist_ok=True)
    heatmap_path.write_text(_heatmap_svg(deals, result, deal_topic_rows), encoding="utf-8")
    manifest: dict[str, object] = {
        "schema_version": 3,
        "status": result.status,
        "release_status": (
            "modeled_corpus_validated"
            if result.status == "modeled" and corpus_validation.accepted
            else "modeled_provisional"
            if result.status == "modeled"
            else result.status
        ),
        "corpus_validation": corpus_validation.as_manifest(),
        "reason": result.reason,
        "review_sha256": _file_sha256(review_csv),
        "passages_sha256": _file_sha256(passages_path),
        "passage_sources_sha256": _file_sha256(sources_path),
        "config": asdict(config),
        "bootstrap_design": {
            "purpose": "complementary_robustness_diagnostic_not_model_selection",
            "sampling_unit": "deal_provision_family_representative",
            "sampling_scope": "within_deal",
            "replacement": True,
            "per_deal_sample_size": "preserve_original_fit_row_count",
            "fit_universe": "same_configured_fit_rows_as_full_nmf_fit",
            "vocabulary": "fixed_from_full_fit",
            "projected_passages_included": False,
            "seed_formula": "config.seed + 1700003 + replicate_id",
            "alignment": "one_to_one_maximum_total_cosine",
            "recovery_cosine_threshold": config.stability_threshold,
        },
        "embedding_robustness_design": {
            "purpose": "complementary_robustness_diagnostic_not_model_selection",
            "fit_universe": "same_configured_fit_rows_as_full_nmf_fit",
            "input_features": "word_bigram_tfidf",
            "embedding": "normalized_truncated_svd_lsa_not_transformer_semantics",
            "svd_algorithm": "randomized",
            "svd_iterations": 7,
            "svd_seed": config.seed,
            "requested_svd_components": config.embedding_svd_components,
            "minimum_fit_rows": config.embedding_min_fit_rows,
            "methods": [
                {
                    "name": "sklearn_hdbscan",
                    "min_cluster_size": config.embedding_hdbscan_min_cluster_size,
                    "min_samples": None,
                    "metric": "euclidean",
                    "cluster_selection_method": "eom",
                    "allow_single_cluster": False,
                    "copy": False,
                },
                {
                    "name": "sklearn_agglomerative",
                    "n_clusters": "selected_nmf_k",
                    "metric": "cosine",
                    "linkage": "average",
                },
            ],
            "comparison": "adjusted_rand_on_shared_nonnoise_rows_when_defined",
        },
        "reporting_metric_definitions": {
            "disclosure_salience": (
                "mean deal-normalized topic share across every selected deal; explicit-zero "
                "deals contribute zero; comparative disclosure share, not importance, concern, "
                "or outcome"
            ),
            "assignment_specificity": (
                "mean normalized top-topic minus runner-up weight margin among passages whose "
                "primary assignment is the topic; model concentration, not substantive certainty"
            ),
            "top_positive_residual_terms": (
                "highest mean positive TF-IDF reconstruction residual max(X-WH,0) within the "
                "topic's primary passages"
            ),
        },
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


def _release_status(gate_passed: bool, corpus_validation: CorpusValidationState) -> str:
    """Collapse the gate and corpus state into one status no artifact can misread as accepted."""
    if gate_passed:
        return "pass"
    if corpus_validation.status == "failed_human_corpus_validation":
        return "fail"
    if corpus_validation.blocks_release:
        return corpus_validation.status
    return "fail"


def summarize_employee_topics_workflow(
    review_csv: Path,
    corpus_dir: Path,
    analysis_dir: Path,
    output_dir: Path,
    *,
    representative_limit: int = 3,
    corpus_audit_dir: Path | None = None,
    corpus_scores_dir: Path | None = None,
) -> WorkflowSummary:
    """Validate the full artifact chain and write the descriptive report plus review queue.

    The corpus relevance-audit state is resolved against the hash of the exact ``passages.csv``
    in ``corpus_dir`` so a verdict from a different corpus can never be borrowed.
    """
    deals = _selected_deals(review_csv)
    corpus_passages_sha256 = _file_sha256(corpus_dir / "passages.csv")
    corpus_validation = resolve_corpus_validation(
        corpus_audit_dir,
        corpus_scores_dir,
        expected_candidate_sha256=corpus_passages_sha256,
    )
    report = build_employee_report(
        corpus_dir / "documents.csv",
        analysis_dir / "source_passages.csv",
        analysis_dir / "topic_assignments.csv",
        analysis_dir / "deal_topic_matrix.csv",
        analysis_dir / "model_diagnostics.csv",
        expected_deal_count=len(deals),
        representative_limit=representative_limit,
        corpus_validation=corpus_validation,
    )
    write_employee_report(
        report,
        output_dir / "employee_topics_report.md",
        output_dir / "topic_review.csv",
    )
    _write_json(
        output_dir / "report_manifest.json",
        {
            "schema_version": 2,
            "gate_passed": report.gate_passed,
            "release_status": _release_status(report.gate_passed, corpus_validation),
            "corpus_validation": corpus_validation.as_manifest(),
            "corpus_passages_sha256": corpus_passages_sha256,
            "selected_deal_ids": [deal["deal_id"] for deal in deals],
            "representative_limit": representative_limit,
            "passages_sha256": _file_sha256(analysis_dir / "source_passages.csv"),
            "assignments_sha256": _file_sha256(analysis_dir / "topic_assignments.csv"),
            "deal_topics_sha256": _file_sha256(analysis_dir / "deal_topic_matrix.csv"),
            "diagnostics_sha256": _file_sha256(analysis_dir / "model_diagnostics.csv"),
        },
    )
    return WorkflowSummary(
        status=_release_status(report.gate_passed, corpus_validation),
        output_dir=output_dir,
        counts={"deals": len(deals), "topic_review_rows": len(report.topic_review_rows)},
    )
