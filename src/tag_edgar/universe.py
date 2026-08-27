"""Freeze and verify the 100-deal AI transaction research universe.

The frozen manifest is the only entry point for downstream corpus construction. Each row
records source-backed AI relevance with exact excerpts, accession identifiers, separate
legal-form and talent-motive fields, and explicit missingness reasons. Deals without
primary-source AI evidence stay in the manifest but are marked not qualifying; they are
never silently dropped and never replaced by generic mergers.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .ai_screening import (
    AiScreenResult,
    TalentSignals,
    classify_ai_category,
    classify_talent_motive,
    detect_talent_signals,
    normalize_transaction_form,
    screen_ai_text_for_target,
    target_name_mentioned,
)
from .cik import TickerRegistry, build_registry, resolve_registry_candidates
from .models import Filing
from .submissions import normalized_cik

MANIFEST_FIELDS: tuple[str, ...] = (
    "deal_id",
    "target_name",
    "acquirer_name",
    "announcement_date",
    "closing_date",
    "transaction_form",
    "talent_motive",
    "ai_category",
    "ai_relevance_evidence",
    "supporting_excerpt",
    "source_url",
    "source_accession",
    "source_document_id",
    "source_quality",
    "verification_status",
    "confidence",
    "missingness_reason",
    "deal_status",
    "candidate_score",
    "matched_target_terms",
    "sdc_source_file",
    "sdc_source_row",
)

QUALIFYING_STATUS = "qualifying_machine_verified_pending_human_review"
NONQUALIFYING_STATUS = "not_qualifying_no_primary_source_found"


@dataclass(frozen=True)
class CandidateRow:
    deal_id: str
    announcement_date: date
    target_name: str
    acquirer_name: str
    source_file: str
    source_row_number: int
    candidate_score: int
    matched_terms: str
    selection_status: str


@dataclass(frozen=True)
class DocumentText:
    """One retrieved document body prepared for screening."""

    document_id: str
    accession_number: str
    url: str
    document_type: str
    text: str
    source_quality: str = "primary_sec_filing"


@dataclass(frozen=True)
class DealAssessment:
    """Pure, deterministic result of screening one deal's retrieved documents."""

    deal_id: str
    qualifies: bool
    verification_status: str
    confidence: str
    ai_category: str
    talent_motive: str
    transaction_form: str
    supporting_excerpt: str
    source_url: str
    source_accession: str
    source_document_id: str
    source_quality: str
    missingness_reason: str
    total_weight: int
    distinct_terms: tuple[str, ...]


def load_candidates(manifest_csv: Path) -> list[CandidateRow]:
    rows: list[CandidateRow] = []
    with manifest_csv.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            rows.append(
                CandidateRow(
                    deal_id=row["deal_id"],
                    announcement_date=date.fromisoformat(row["announcement_date"]),
                    target_name=row["target_name"],
                    acquirer_name=row["acquirer_name"],
                    source_file=row["source_file"],
                    source_row_number=int(row["source_row_number"]),
                    candidate_score=int(row["candidate_score"]),
                    matched_terms=row["matched_target_terms"],
                    selection_status=row["selection_status"],
                )
            )
    return rows


def load_sdc_form(
    raw_dir: Path, source_file: str, source_row: int
) -> tuple[str | None, date | None]:
    """Recover the original SDC ``Form`` and effective-date values for one candidate."""
    path = raw_dir / source_file
    with path.open(newline="", encoding="utf-8-sig") as file:
        next(file, None)
        reader = csv.DictReader(file)
        for index, row in enumerate(reader, start=2):
            if index == source_row:
                form_raw = (row.get("Form") or "").strip() or None
                effective_raw = (row.get("Date Effective") or "").strip()
                effective: date | None = None
                if effective_raw:
                    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
                        try:
                            from datetime import datetime

                            # The source records a calendar date, not an instant in time.
                            effective = datetime.strptime(effective_raw, fmt).date()  # noqa: DTZ007
                            break
                        except ValueError:
                            continue
                return form_raw, effective
        raise KeyError(f"{source_file} has no data row {source_row}.")


def assessment_window(announcement: date, effective: date | None) -> tuple[date, date]:
    """Deterministic filing window: announcement-30d to min(effective+30d, announcement+365d)."""
    start = announcement - timedelta(days=30)
    end = (
        effective + timedelta(days=30)
        if effective is not None
        else announcement + timedelta(days=365)
    )
    return start, end


def _confidence_for(weight: int, name_mentioned: bool) -> str:
    if weight >= 8 and name_mentioned:
        return "high"
    if (weight >= 5 and name_mentioned) or weight >= 10:
        return "medium"
    return "low"


def assess_deal_documents(
    deal_id: str,
    documents: list[DocumentText],
    *,
    target_name: str,
    sdc_form: str | None,
    qualifying_weight: int = 5,
) -> DealAssessment:
    """Screen every retrieved document for one deal and pick the strongest evidence.

    Documents are screened in sorted order so the result never depends on retrieval order.
    Evidence from a document that also names the target is preferred; a qualifying excerpt
    without the target name is still recorded but at lower confidence.
    """
    form_label = normalize_transaction_form(sdc_form)
    ordered = sorted(documents, key=lambda doc: (doc.accession_number, doc.document_id))

    best: tuple[int, bool, DocumentText, AiScreenResult, TalentSignals] | None = None
    any_retrieved = bool(ordered)
    any_target_mention = False
    for document in ordered:
        any_target_mention = any_target_mention or target_name_mentioned(document.text, target_name)
        screen_result = screen_ai_text_for_target(
            document.text,
            target_name,
            qualifying_weight=qualifying_weight,
        )
        if not screen_result.qualifies:
            continue
        strongest_hit = screen_result.hits[0]
        context_start = max(0, strongest_hit.match_start - 1000)
        context_end = min(len(document.text), strongest_hit.match_end + 1000)
        talent_signals = detect_talent_signals(document.text[context_start:context_end])
        name_mentioned = True
        key = (screen_result.total_weight, name_mentioned)
        if best is None or key > (best[0], best[1]):
            best = (
                screen_result.total_weight,
                name_mentioned,
                document,
                screen_result,
                talent_signals,
            )

    if best is None:
        return DealAssessment(
            deal_id=deal_id,
            qualifies=False,
            verification_status=NONQUALIFYING_STATUS,
            confidence="not_applicable",
            ai_category="unknown",
            talent_motive="unknown",
            transaction_form=form_label,
            supporting_excerpt="",
            source_url="",
            source_accession="",
            source_document_id="",
            source_quality="not_applicable",
            missingness_reason=(
                "no_documents_retrieved_for_deal"
                if not any_retrieved
                else (
                    "target_mentioned_without_local_ai_evidence"
                    if any_target_mention
                    else "no_target_mention_in_retrieved_documents"
                )
            ),
            total_weight=0,
            distinct_terms=(),
        )

    weight, name_mentioned, document, screen_result, talent_signals = best
    category = classify_ai_category(
        screen_result=screen_result, talent_signals=talent_signals, sdc_form=sdc_form
    )
    motive = classify_talent_motive(talent_signals)
    return DealAssessment(
        deal_id=deal_id,
        qualifies=True,
        verification_status=QUALIFYING_STATUS,
        confidence=_confidence_for(weight, name_mentioned),
        ai_category=category,
        talent_motive=motive,
        transaction_form=form_label,
        supporting_excerpt=screen_result.best_excerpt,
        source_url=document.url,
        source_accession=document.accession_number,
        source_document_id=document.document_id,
        source_quality=document.source_quality,
        missingness_reason="",
        total_weight=weight,
        distinct_terms=screen_result.distinct_terms,
    )


def manifest_row(
    candidate: CandidateRow, assessment: DealAssessment, closing_date: date | None
) -> dict[str, object]:
    return {
        "deal_id": candidate.deal_id,
        "target_name": candidate.target_name,
        "acquirer_name": candidate.acquirer_name,
        "announcement_date": candidate.announcement_date.isoformat(),
        "closing_date": closing_date.isoformat() if closing_date else "unknown",
        "transaction_form": assessment.transaction_form,
        "talent_motive": assessment.talent_motive,
        "ai_category": assessment.ai_category,
        "ai_relevance_evidence": "; ".join(assessment.distinct_terms)
        or assessment.missingness_reason,
        "supporting_excerpt": assessment.supporting_excerpt,
        "source_url": assessment.source_url,
        "source_accession": assessment.source_accession,
        "source_document_id": assessment.source_document_id,
        "source_quality": assessment.source_quality if assessment.qualifies else "not_applicable",
        "verification_status": assessment.verification_status,
        "confidence": assessment.confidence,
        "missingness_reason": assessment.missingness_reason,
        "deal_status": "completed" if closing_date is not None else "unclear",
        "candidate_score": candidate.candidate_score,
        "matched_target_terms": candidate.matched_terms,
        "sdc_source_file": candidate.source_file,
        "sdc_source_row": candidate.source_row_number,
    }


def write_manifest(out_dir: Path, rows: list[dict[str, object]], config: dict[str, object]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "frozen_ai_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(MANIFEST_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (out_dir / "frozen_ai_manifest.meta.json").write_text(
        json.dumps({**config, "manifest_sha256": checksum}, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return manifest_path


def registry_from_payload(payload: dict[str, object]) -> TickerRegistry:
    return build_registry(payload)


def acquirer_cik(registry: TickerRegistry, acquirer_name: str) -> str | None:
    candidates = resolve_registry_candidates(registry, acquirer_name)
    if not candidates:
        return None
    top = candidates[0]
    if top.confidence in {"high", "medium"}:
        return normalized_cik(top.cik)
    return None


def filings_in_window(
    filings: list[Filing], start: date, end: date, forms: frozenset[str]
) -> list[Filing]:
    return [
        filing
        for filing in sorted(filings, key=lambda item: (item.filing_date, item.accession_number))
        if start <= filing.filing_date <= end and filing.form in forms
    ]
