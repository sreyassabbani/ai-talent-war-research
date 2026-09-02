"""Deal-architecture review layer for the 10-deal pilot.

This layer answers a different question from the employee-language topic model. The topic model
asks what recurring themes appear in employee-related passages. This layer asks what kind of
transaction each deal was: its legal form, what scope and control moved, how intellectual property
was treated, whether the business continued, which people moved, and whether talent was an
explicit motive. Those are not latent topics to discover from ten rows; they are coded from
source-backed deal attributes by explicit rules and then handed to a human reviewer.

The source of truth is the version-controlled evidence register (one row per deal, attribute,
and supporting source). This module validates that register, derives deal-level attributes and
archetype suggestions from it, attaches canonical and highlight URLs, and writes the review table.
Every machine suggestion is labelled ``machine_suggested_pending_human_review``; the human fields
are always written blank.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .source_links import highlight_link
from .storage import write_dict_csv

__all__ = [
    "ARCHETYPES",
    "ATTRIBUTES",
    "EVIDENCE_FIELDS",
    "OUTPUT_FIELDS",
    "REVIEW_STATUS",
    "DealArchitecture",
    "build_deal_architecture",
    "load_evidence_register",
    "suggest_archetypes",
    "write_deal_architecture",
]

RULES_VERSION = "deal-architecture-rules-v1"
REVIEW_STATUS = "machine_suggested_pending_human_review"

ATTRIBUTES: tuple[str, ...] = (
    "legal_transaction_form",
    "scope_and_control",
    "ip_treatment",
    "business_product_continuity",
    "workforce_movement",
    "talent_motive_explicit",
)

EVIDENCE_BASES = frozenset({"direct_passage", "inferred_from_legal_form", "unknown"})
EVIDENCE_STATUSES = frozenset({"direct", "partial", "indirect", "unknown"})
EXCERPT_KINDS = frozenset({"verbatim", "paraphrase"})

ARCHETYPES: tuple[str, ...] = (
    "full_acquisition",
    "asset_acquisition",
    "traditional_acquihire",
    "reverse_acquihire",
    "hire_and_license",
    "acquisition_with_talent_emphasis",
    "mixed",
    "unknown",
)

EVIDENCE_FIELDS = [
    "deal_id",
    "sdc_deal_id",
    "deal_name",
    "acquirer",
    "target",
    "agreement_date",
    "attribute",
    "machine_value",
    "evidence_basis",
    "evidence_status",
    "document_id",
    "document_type",
    "source_url",
    "source_locator",
    "excerpt_kind",
    "evidence_excerpt",
    "limitation",
    "salvage_reference",
]

EVIDENCE_OUTPUT_FIELDS = [
    "evidence_id",
    *EVIDENCE_FIELDS,
    "source_highlight_url",
    "highlight_status",
    "review_status",
]

OUTPUT_FIELDS = [
    "deal_id",
    "sdc_deal_id",
    "deal_name",
    "acquirer",
    "target",
    "agreement_date",
    *ATTRIBUTES,
    *(f"{attribute}_basis" for attribute in ATTRIBUTES),
    "machine_suggested_archetypes",
    "archetype_ambiguity",
    "competing_interpretations",
    "direct_evidence_count",
    "inferred_evidence_count",
    "unknown_attribute_count",
    "evidence_ids",
    "review_status",
    "human_final_archetype",
    "human_reviewer_id",
    "human_review_note",
]


@dataclass(frozen=True)
class DealArchitecture:
    deal_rows: tuple[dict[str, str], ...]
    evidence_rows: tuple[dict[str, str], ...]
    manifest: dict[str, object]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_evidence_register(path: Path) -> list[dict[str, str]]:
    """Read and validate the evidence register; refuse rows that would let a claim float free."""
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or list(reader.fieldnames) != EVIDENCE_FIELDS:
            raise ValueError(
                f"Evidence register columns must be exactly {EVIDENCE_FIELDS}; got {reader.fieldnames}."
            )
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("Evidence register is empty.")

    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=2):
        for field in ("deal_id", "attribute", "machine_value", "evidence_basis", "evidence_status"):
            if not row[field]:
                raise ValueError(f"Row {index}: {field} is required.")
        if row["attribute"] not in ATTRIBUTES:
            raise ValueError(f"Row {index}: unknown attribute {row['attribute']!r}.")
        if row["evidence_basis"] not in EVIDENCE_BASES:
            raise ValueError(f"Row {index}: evidence_basis must be one of {sorted(EVIDENCE_BASES)}.")
        if row["evidence_status"] not in EVIDENCE_STATUSES:
            raise ValueError(
                f"Row {index}: evidence_status must be one of {sorted(EVIDENCE_STATUSES)}."
            )
        if row["excerpt_kind"] not in EXCERPT_KINDS:
            raise ValueError(f"Row {index}: excerpt_kind must be one of {sorted(EXCERPT_KINDS)}.")
        key = (row["deal_id"], row["attribute"])
        if key in seen:
            raise ValueError(f"Row {index}: duplicate attribute {key}; merge evidence into one row.")
        seen.add(key)
        # A non-unknown claim must be pinned to a document and a canonical URL.
        if row["machine_value"] != "unknown" and row["evidence_basis"] != "unknown":
            for field in ("document_id", "source_url", "evidence_excerpt"):
                if not row[field]:
                    raise ValueError(
                        f"Row {index}: {field} is required when machine_value is not unknown."
                    )
            if not row["source_url"].startswith("https://"):
                raise ValueError(f"Row {index}: source_url must be an absolute https URL.")
        if row["machine_value"] == "unknown" and row["evidence_status"] != "unknown":
            raise ValueError(f"Row {index}: an unknown value must carry evidence_status=unknown.")

    deals = {row["deal_id"] for row in rows}
    for deal_id in sorted(deals):
        present = {row["attribute"] for row in rows if row["deal_id"] == deal_id}
        missing = [attribute for attribute in ATTRIBUTES if attribute not in present]
        if missing:
            raise ValueError(f"Deal {deal_id} is missing attribute rows for {missing}.")
    return rows


def _values(machine_value: str) -> set[str]:
    return {part for part in machine_value.split("|") if part}


def suggest_archetypes(attributes: Mapping[str, str]) -> tuple[list[str], str, str]:
    """Map coded attributes to archetype suggestions, an ambiguity grade, and a competing reading.

    The rules are deliberately small and legible. They are a starting point for human review,
    not a classifier, and a single deal may receive more than one archetype.
    """
    scope = _values(attributes["scope_and_control"])
    ip = attributes["ip_treatment"]
    talent = attributes["talent_motive_explicit"]
    continuity = attributes["business_product_continuity"]
    workforce = _values(attributes["workforce_movement"])

    control_moved = bool(scope & {"control_transferred", "control_of_purchased_assets_only"})
    if not scope or scope == {"unknown"}:
        return (
            ["unknown"],
            "high",
            "Scope and control are not established, so no archetype can be suggested.",
        )

    if not control_moved:
        if ip == "licensed" and workforce:
            return (
                ["hire_and_license", "reverse_acquihire"],
                "medium",
                (
                    "Team hiring plus an IP licence without control transfer reads as a "
                    "license-and-hire; whether it is economically merger-like is a separate "
                    "question."
                ),
            )
        return (
            ["mixed"],
            "high",
            "No control transfer and no IP licence recorded; the structure needs human coding.",
        )

    base = "asset_acquisition" if "business_unit_assets" in scope else "full_acquisition"
    named_people = any(part.startswith("named_") for part in workforce)

    if talent == "yes" and continuity == "discontinued":
        return (
            ["traditional_acquihire"],
            "low",
            (
                "Control moved, talent was an explicit motive, and the product did not continue; "
                f"a reviewer may still prefer {base} if the discontinuation is later reversed."
            ),
        )
    if talent in {"yes", "partial"}:
        competing = (
            f"{base} with people-related deal terms. A reviewer must decide whether founder or "
            "key-employee conditions rise to a talent motive or are ordinary deal protection."
        )
        return ([base, "acquisition_with_talent_emphasis"], "medium", competing)
    if named_people:
        return (
            [base],
            "medium",
            (
                "Named leaders or founders are addressed, but no talent motive is stated; treat "
                "the naming as continuity disclosure unless a reviewer finds motive language."
            ),
        )
    if talent == "unknown":
        return (
            [base],
            "medium",
            (
                "Talent motive is unknown in the reviewed passages; the archetype rests on legal "
                "form alone and could change if a reviewer finds motive language elsewhere."
            ),
        )
    return ([base], "low", "Legal form, scope, and control are consistent with a conventional deal.")


def build_deal_architecture(register_path: Path) -> DealArchitecture:
    """Derive the deal-level table and the long-format evidence table from the register."""
    rows = load_evidence_register(register_path)
    by_deal: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_deal[row["deal_id"]].append(row)

    evidence_rows: list[dict[str, str]] = []
    deal_rows: list[dict[str, str]] = []
    highlight_counts: dict[str, int] = defaultdict(int)

    for deal_id in sorted(by_deal):
        deal_evidence = sorted(by_deal[deal_id], key=lambda row: ATTRIBUTES.index(row["attribute"]))
        header = deal_evidence[0]
        attributes: dict[str, str] = {}
        bases: dict[str, str] = {}
        evidence_ids: list[str] = []
        direct = inferred = unknown = 0
        for row in deal_evidence:
            evidence_id = f"arch_{hashlib.sha256(f'{deal_id}:{row['attribute']}'.encode()).hexdigest()[:12]}"
            evidence_ids.append(evidence_id)
            attributes[row["attribute"]] = row["machine_value"]
            bases[row["attribute"]] = row["evidence_basis"]
            if row["evidence_basis"] == "direct_passage":
                direct += 1
            elif row["evidence_basis"] == "inferred_from_legal_form":
                inferred += 1
            if row["machine_value"] == "unknown":
                unknown += 1

            # Only a verbatim excerpt can honestly be turned into a highlight target.
            if row["excerpt_kind"] == "verbatim" and row["source_url"]:
                link = highlight_link(row["source_url"], row["evidence_excerpt"])
                highlight_url, highlight_status = link.url, link.status
            elif row["source_url"]:
                highlight_url, highlight_status = "", "unsupported_paraphrase_not_quotable"
            else:
                highlight_url, highlight_status = "", "unsupported_missing_url"
            highlight_counts[highlight_status] += 1
            evidence_rows.append(
                {
                    "evidence_id": evidence_id,
                    **{field: row[field] for field in EVIDENCE_FIELDS},
                    "source_highlight_url": highlight_url,
                    "highlight_status": highlight_status,
                    "review_status": REVIEW_STATUS,
                }
            )

        archetypes, ambiguity, competing = suggest_archetypes(attributes)
        deal_rows.append(
            {
                "deal_id": deal_id,
                "sdc_deal_id": header["sdc_deal_id"],
                "deal_name": header["deal_name"],
                "acquirer": header["acquirer"],
                "target": header["target"],
                "agreement_date": header["agreement_date"] or "unknown",
                **attributes,
                **{f"{attribute}_basis": bases[attribute] for attribute in ATTRIBUTES},
                "machine_suggested_archetypes": "|".join(archetypes),
                "archetype_ambiguity": ambiguity,
                "competing_interpretations": competing,
                "direct_evidence_count": str(direct),
                "inferred_evidence_count": str(inferred),
                "unknown_attribute_count": str(unknown),
                "evidence_ids": "|".join(evidence_ids),
                "review_status": REVIEW_STATUS,
                "human_final_archetype": "",
                "human_reviewer_id": "",
                "human_review_note": "",
            }
        )

    archetype_counts: dict[str, int] = defaultdict(int)
    for row in deal_rows:
        for archetype in row["machine_suggested_archetypes"].split("|"):
            archetype_counts[archetype] += 1

    manifest: dict[str, object] = {
        "schema_version": 1,
        "rules_version": RULES_VERSION,
        "review_status": REVIEW_STATUS,
        "evidence_register_sha256": _file_sha256(register_path),
        "deal_count": len(deal_rows),
        "evidence_row_count": len(evidence_rows),
        "machine_suggested_archetype_counts": dict(sorted(archetype_counts.items())),
        "highlight_status_counts": dict(sorted(highlight_counts.items())),
        "human_fields_left_blank": [
            "human_final_archetype",
            "human_reviewer_id",
            "human_review_note",
        ],
        "boundary": (
            "Attributes describe disclosed transaction structure. They are not employee outcomes, "
            "and a suggested archetype is not a finding until a human reviewer records one."
        ),
    }
    return DealArchitecture(tuple(deal_rows), tuple(evidence_rows), manifest)


def write_deal_architecture(output_dir: Path, result: DealArchitecture) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dict_csv(output_dir / "deal_architecture.csv", result.deal_rows, OUTPUT_FIELDS)
    write_dict_csv(
        output_dir / "deal_architecture_evidence.csv", result.evidence_rows, EVIDENCE_OUTPUT_FIELDS
    )
    manifest = {
        **result.manifest,
        "deal_architecture_sha256": _file_sha256(output_dir / "deal_architecture.csv"),
        "deal_architecture_evidence_sha256": _file_sha256(
            output_dir / "deal_architecture_evidence.csv"
        ),
    }
    (output_dir / "architecture_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def architecture_rows(path: Path) -> Sequence[dict[str, str]]:
    """Read a written deal_architecture.csv back for downstream joins."""
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))
