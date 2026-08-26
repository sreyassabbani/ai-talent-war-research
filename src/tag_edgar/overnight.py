"""Resumable unattended pipeline for the 100-deal AI expansion.

The pipeline uses no LLM. EDGAR retrieval is cached and rate limited; screening,
corpus construction, topic modelling, baseline adjustment, tone measurement, word
clouds, and reporting are deterministic or fixed-seed. A machine-qualified row is
always labelled as pending human review and is never presented as a verified outcome.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .ai_screening import normalize_transaction_form, target_name_mentioned
from .baseline import BaselineConfig, apply_baselines, compute_family_baselines
from .cik import TICKER_REGISTRY_URL
from .deal_retrieval import RETRIEVAL_FORMS, DocumentRecord, retrieve_deal_documents
from .employee_corpus import CorpusDocument, build_employee_corpus
from .sec_client import SecClient
from .settings import Settings, load_settings
from .submissions import fetch_filings
from .tone import LEXICONS, deal_tone_summary, passage_tone_rows
from .topics100 import (
    TopicsConfig,
    TopicSolution,
    agglomerative_sensitivity,
    fit_topics,
    leave_one_deal_out_stability,
    topic_label,
)
from .universe import (
    QUALIFYING_STATUS,
    CandidateRow,
    DealAssessment,
    DocumentText,
    acquirer_cik,
    assess_deal_documents,
    assessment_window,
    filings_in_window,
    load_candidates,
    load_sdc_form,
    manifest_row,
    registry_from_payload,
    write_manifest,
)
from .wordcloud import CloudConfig, render_svg, write_cloud_index

EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_PARTIAL = 2

PASSAGE_FIELDS = (
    "passage_id",
    "deal_id",
    "document_id",
    "accession_number",
    "document_type",
    "document_family",
    "source_url",
    "heading",
    "block_start",
    "block_end",
    "char_start",
    "char_end",
    "text",
    "model_text",
    "token_count",
    "screen_terms",
    "content_sha256",
    "duplicate_group_id",
    "occurrence_count",
)

OCCURRENCE_FIELDS = (
    "occurrence_id",
    "passage_id",
    "deal_id",
    "document_id",
    "accession_number",
    "document_type",
    "document_family",
    "source_url",
    "heading",
    "block_start",
    "block_end",
    "char_start",
    "char_end",
    "duplicate_group_id",
    "content_sha256",
)

INVENTORY_FIELDS = (
    "deal_id",
    "document_id",
    "accession_number",
    "form",
    "document_type",
    "family",
    "url",
    "status",
    "content_sha256",
    "char_count",
    "error",
    "transaction_relevance_status",
)

_WORD = re.compile(r"\b[a-z][a-z'-]{2,}\b", re.IGNORECASE)
_CLOUD_STOPWORDS = frozenset(
    {
        "and",
        "are",
        "for",
        "from",
        "has",
        "have",
        "into",
        "its",
        "not",
        "shall",
        "that",
        "the",
        "their",
        "this",
        "was",
        "were",
        "will",
        "with",
    }
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"


def _to_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"Expected a numeric value, got {type(value).__name__}.")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    temporary.replace(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _field_union(rows: Sequence[Mapping[str, object]], required: Sequence[str] = ()) -> list[str]:
    fields = list(required)
    seen = set(fields)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


def _document_text(record: DocumentRecord, text: str) -> DocumentText:
    return DocumentText(
        document_id=record.document_id,
        accession_number=record.accession_number,
        url=record.url,
        document_type=record.document_type,
        text=text,
    )


def _failed_assessment(
    deal_id: str,
    reason: str,
    *,
    status: str = "failed_retrieval",
    transaction_form: str = "unknown",
) -> DealAssessment:
    return DealAssessment(
        deal_id=deal_id,
        qualifies=False,
        verification_status=status,
        confidence="not_applicable",
        ai_category="unknown",
        talent_motive="unknown",
        transaction_form=transaction_form,
        supporting_excerpt="",
        source_url="",
        source_accession="",
        source_document_id="",
        source_quality="not_applicable",
        missingness_reason=reason,
        total_weight=0,
        distinct_terms=(),
    )


class OvernightRun:
    """Run and resume the deterministic 100-deal research workflow."""

    def __init__(
        self,
        *,
        settings: Settings,
        client: SecClient,
        candidates_csv: Path,
        raw_dir: Path,
        out_dir: Path,
        max_deals: int | None = None,
        target_deals: int = 100,
        refresh: bool = False,
        topics_config: TopicsConfig | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.candidates_csv = candidates_csv
        self.raw_dir = raw_dir
        self.out_dir = out_dir
        self.max_deals = max_deals
        self.target_deals = target_deals
        self.refresh = refresh
        self.topics_config = topics_config or TopicsConfig()
        self.state_path = out_dir / "state.json"
        self.log_path = out_dir / "overnight_log.jsonl"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.state: dict[str, object] = {}
        if self.state_path.exists() and not refresh:
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.failures: list[dict[str, str]] = []

    def log(self, stage: str, status: str, **detail: object) -> None:
        event = {"ts": _now(), "stage": stage, "status": status, **detail}
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    def save_state(self) -> None:
        self.state["updated_at"] = _now()
        _atomic_text(
            self.state_path,
            json.dumps(self.state, indent=2, sort_keys=True, default=str) + "\n",
        )

    def _stage_done(self, name: str, required_paths: Sequence[Path]) -> bool:
        stages = self.state.get("stages", {})
        complete = (
            isinstance(stages, dict)
            and isinstance(stages.get(name), dict)
            and stages[name].get("status") == "completed"
        )
        return bool(complete and not self.refresh and all(path.exists() for path in required_paths))

    def _mark_stage(self, name: str, **counts: object) -> None:
        stage_counts = dict(counts)
        if "status" in stage_counts:
            stage_counts["outcome_status"] = stage_counts.pop("status")
        stages = self.state.setdefault("stages", {})
        if isinstance(stages, dict):
            stages[name] = {
                "status": "completed",
                "completed_at": _now(),
                **stage_counts,
            }
        self.save_state()
        self.log(name, "completed", **stage_counts)

    def _deal_done(self, deal_id: str) -> bool:
        deals = self.state.get("deals", {})
        return isinstance(deals, dict) and deal_id in deals and not self.refresh

    def _record_failure(self, stage: str, deal_id: str, error: str) -> None:
        entry = {"stage": stage, "deal_id": deal_id, "error": error[:500]}
        failures = self.state.setdefault("failures", [])
        if isinstance(failures, list):
            failures.append(entry)
        self.failures.append(entry)
        self.log(stage, "failed", deal_id=deal_id, error=entry["error"])

    def stage_freeze_universe(self) -> tuple[list[CandidateRow], list[dict[str, object]]]:
        """Retrieve SEC documents and write one explicit manifest row per candidate."""
        candidates = [
            row
            for row in load_candidates(self.candidates_csv)
            if row.selection_status == "selected_candidate"
        ]
        if self.max_deals is not None:
            candidates = candidates[: self.max_deals]
        if not candidates:
            raise ValueError("No selected_candidate rows were found in the candidate CSV.")

        manifest_path = self.out_dir / "frozen_ai_manifest.csv"
        inventory_path = self.out_dir / "document_inventory.csv"
        if self._stage_done("freeze_universe", (manifest_path, inventory_path)):
            return candidates, [dict(row) for row in _read_csv(manifest_path)]

        registry = registry_from_payload(self.client.get_json(TICKER_REGISTRY_URL))
        rows: list[dict[str, object]] = []
        inventory_rows: list[dict[str, object]] = []
        for index, candidate in enumerate(candidates):
            if self._deal_done(candidate.deal_id):
                deals = self.state.get("deals", {})
                cached = deals.get(candidate.deal_id) if isinstance(deals, dict) else None
                if isinstance(cached, dict) and cached.get("manifest_row"):
                    rows.append(dict(cached["manifest_row"]))
                    inventory_rows.extend(dict(row) for row in cached.get("inventory_rows", []))
                    continue

            records: list[DocumentRecord] = []
            texts: list[tuple[str, str]] = []
            try:
                sdc_form, effective = load_sdc_form(
                    self.raw_dir, candidate.source_file, candidate.source_row_number
                )
                cik = acquirer_cik(registry, candidate.acquirer_name)
                if cik is None:
                    assessment = _failed_assessment(
                        candidate.deal_id,
                        "acquirer_not_resolved_on_edgar",
                        status="not_qualifying_no_primary_source_found",
                        transaction_form=normalize_transaction_form(sdc_form),
                    )
                else:
                    filings = fetch_filings(self.client, cik)
                    start, end = assessment_window(candidate.announcement_date, effective)
                    windowed = filings_in_window(filings, start, end, RETRIEVAL_FORMS)
                    texts, records = retrieve_deal_documents(
                        self.client, deal_id=candidate.deal_id, filings=windowed
                    )
                    record_by_id = {record.document_id: record for record in records}
                    document_texts = [
                        _document_text(record_by_id[document_id], text)
                        for document_id, text in texts
                        if document_id in record_by_id
                    ]
                    self._write_document_texts(candidate.deal_id, records, texts)
                    assessment = assess_deal_documents(
                        candidate.deal_id,
                        document_texts,
                        target_name=candidate.target_name,
                        sdc_form=sdc_form,
                    )
                row = manifest_row(candidate, assessment, effective)
                text_by_id = {document_id: text for document_id, text in texts}
                current_inventory = []
                for record in records:
                    inventory_row = asdict(record)
                    document_body = text_by_id.get(record.document_id, "")
                    inventory_row["transaction_relevance_status"] = (
                        "target_linked"
                        if document_body
                        and target_name_mentioned(document_body, candidate.target_name)
                        else (
                            "excluded_no_target_link"
                            if record.status == "retrieved"
                            else "retrieval_failed"
                        )
                    )
                    current_inventory.append(inventory_row)
                rows.append(row)
                inventory_rows.extend(current_inventory)
                deals = self.state.setdefault("deals", {})
                if isinstance(deals, dict):
                    deals[candidate.deal_id] = {
                        "qualifies": assessment.qualifies,
                        "manifest_row": row,
                        "inventory_rows": current_inventory,
                    }
                self.save_state()
                self.log(
                    "freeze_universe",
                    "ok" if assessment.qualifies else "no_evidence",
                    deal_id=candidate.deal_id,
                    confidence=assessment.confidence,
                )
            except Exception as error:  # noqa: BLE001 - continue after individual failures
                self._record_failure("freeze_universe", candidate.deal_id, str(error))
                failed = _failed_assessment(
                    candidate.deal_id, f"retrieval_error:{type(error).__name__}"
                )
                rows.append(manifest_row(candidate, failed, None))
            if (index + 1) % 10 == 0:
                self.log("freeze_universe", "progress", processed=index + 1, total=len(candidates))

        rows.sort(key=lambda row: str(row["deal_id"]))
        inventory_rows.sort(key=lambda row: (str(row["deal_id"]), str(row["document_id"])))
        write_manifest(
            self.out_dir,
            rows,
            {
                "stage": "freeze_universe",
                "candidates_csv": str(self.candidates_csv),
                "candidate_sha256": _sha256(self.candidates_csv),
                "candidate_count": len(candidates),
                "target_deals": self.target_deals,
                "generated_at": _now(),
                "note": "Machine-screened evidence pending human review.",
            },
        )
        _write_csv(inventory_path, inventory_rows, INVENTORY_FIELDS)
        _write_csv(
            self.out_dir / "retrieved_document_index.csv",
            [row for row in inventory_rows if row.get("status") == "retrieved"],
            INVENTORY_FIELDS,
        )
        source_fields = (
            "deal_id",
            "acquirer_name",
            "target_name",
            "source_url",
            "source_accession",
            "source_document_id",
            "source_quality",
            "supporting_excerpt",
            "verification_status",
            "confidence",
            "missingness_reason",
        )
        _write_csv(self.out_dir / "deal_source_register.csv", rows, source_fields)
        qualifying = sum(row["verification_status"] == QUALIFYING_STATUS for row in rows)
        self._mark_stage(
            "freeze_universe",
            candidates=len(candidates),
            manifest_rows=len(rows),
            qualifying_machine_rows=qualifying,
            document_rows=len(inventory_rows),
        )
        return candidates, rows

    def _write_document_texts(
        self,
        deal_id: str,
        records: list[DocumentRecord],
        texts: list[tuple[str, str]],
    ) -> None:
        text_by_id = {document_id: text for document_id, text in texts}
        for record in records:
            text = text_by_id.get(record.document_id)
            if not text:
                continue
            deal_dir = self.out_dir / "corpus_docs" / deal_id
            deal_dir.mkdir(parents=True, exist_ok=True)
            _atomic_text(deal_dir / f"{record.document_id}.txt", text)

    def stage_build_corpus(
        self, manifest_rows: Sequence[dict[str, object]]
    ) -> list[dict[str, str]]:
        """Build the provenance-preserving employee passage corpus."""
        passage_path = self.out_dir / "passages.csv"
        occurrence_path = self.out_dir / "passage_sources.csv"
        if self._stage_done("build_corpus", (passage_path, occurrence_path)):
            return _read_csv(passage_path)

        qualifying = {
            str(row["deal_id"])
            for row in manifest_rows
            if row.get("verification_status") == QUALIFYING_STATUS
        }
        inventory = _read_csv(self.out_dir / "document_inventory.csv")
        family_by_document: dict[tuple[str, str], str] = {}
        documents: list[CorpusDocument] = []
        for row in inventory:
            deal_id = row["deal_id"]
            document_id = row["document_id"]
            family_by_document[(deal_id, document_id)] = row.get("family", "other") or "other"
            text_path = self.out_dir / "corpus_docs" / deal_id / f"{document_id}.txt"
            if (
                deal_id not in qualifying
                or row.get("status") != "retrieved"
                or row.get("transaction_relevance_status") != "target_linked"
                or not text_path.exists()
            ):
                continue
            documents.append(
                CorpusDocument(
                    deal_id=deal_id,
                    document_id=document_id,
                    accession_number=row.get("accession_number", ""),
                    document_type=row.get("document_type", ""),
                    source_url=row.get("url", ""),
                    content=text_path.read_text(encoding="utf-8"),
                    content_type="text/plain",
                )
            )

        corpus = build_employee_corpus(documents)
        passage_rows: list[dict[str, object]] = []
        for passage in corpus.passages:
            row = asdict(passage)
            row["document_family"] = family_by_document.get(
                (passage.deal_id, passage.document_id), "other"
            )
            row["screen_terms"] = "; ".join(passage.screen_terms)
            passage_rows.append(row)
        passage_rows.sort(key=lambda row: str(row["passage_id"]))

        passage_lookup = {str(row["passage_id"]): row for row in passage_rows}
        occurrence_rows: list[dict[str, object]] = []
        for occurrence in corpus.occurrences:
            row = asdict(occurrence)
            canonical = passage_lookup[occurrence.passage_id]
            row["document_family"] = family_by_document.get(
                (occurrence.deal_id, occurrence.document_id), "other"
            )
            row["duplicate_group_id"] = canonical["duplicate_group_id"]
            row["content_sha256"] = canonical["content_sha256"]
            occurrence_rows.append(row)
        occurrence_rows.sort(key=lambda row: str(row["occurrence_id"]))

        _write_csv(passage_path, passage_rows, PASSAGE_FIELDS)
        _write_csv(occurrence_path, occurrence_rows, OCCURRENCE_FIELDS)
        _write_csv(self.out_dir / "deduplication.csv", occurrence_rows, OCCURRENCE_FIELDS)

        passages_by_document = Counter(str(row["document_id"]) for row in occurrence_rows)
        screen_rows: list[dict[str, object]] = []
        for row in inventory:
            if row["deal_id"] not in qualifying:
                continue
            count = passages_by_document[row["document_id"]]
            screen_rows.append(
                {
                    "deal_id": row["deal_id"],
                    "document_id": row["document_id"],
                    "document_family": row.get("family", "other"),
                    "retrieval_status": row.get("status", ""),
                    "transaction_relevance_status": row.get(
                        "transaction_relevance_status", "unknown"
                    ),
                    "employee_passage_count": count,
                    "employee_screen_status": ("included" if count else "zero_qualifying_passages"),
                }
            )
        _write_csv(
            self.out_dir / "employee_screen_results.csv",
            screen_rows,
            (
                "deal_id",
                "document_id",
                "document_family",
                "retrieval_status",
                "transaction_relevance_status",
                "employee_passage_count",
                "employee_screen_status",
            ),
        )

        passage_deals = {str(row["deal_id"]) for row in occurrence_rows}
        zero_rows = [
            {
                "deal_id": deal_id,
                "status": "zero_qualifying_passages",
                "missingness_reason": ("retrieved_documents_produced_no_employee_screen_matches"),
            }
            for deal_id in sorted(qualifying - passage_deals)
        ]
        _write_csv(
            self.out_dir / "zero_passage_deals.csv",
            zero_rows,
            ("deal_id", "status", "missingness_reason"),
        )
        corpus_manifest = {
            "schema_version": 1,
            "generated_at": _now(),
            "qualifying_machine_deals": len(qualifying),
            "documents_scanned": corpus.documents_scanned,
            "blocks_scanned": corpus.blocks_scanned,
            "blocks_matched": corpus.blocks_matched,
            "unique_passages": len(passage_rows),
            "source_occurrences": len(occurrence_rows),
            "zero_passage_deals": len(zero_rows),
            "frozen_manifest_sha256": _sha256(self.out_dir / "frozen_ai_manifest.csv"),
            "document_inventory_sha256": _sha256(self.out_dir / "document_inventory.csv"),
            "passages_sha256": _sha256(passage_path),
        }
        _atomic_text(
            self.out_dir / "corpus_manifest.json",
            json.dumps(corpus_manifest, indent=2, sort_keys=True) + "\n",
        )
        self._mark_stage(
            "build_corpus",
            documents=corpus.documents_scanned,
            passages=len(passage_rows),
            occurrences=len(occurrence_rows),
            zero_passage_deals=len(zero_rows),
        )
        return _read_csv(passage_path)

    @staticmethod
    def _deal_topic_matrix(
        solution: TopicSolution,
        passage_ids: list[str],
        occurrences: Sequence[dict[str, str]],
        label_map: dict[int, str],
    ) -> list[dict[str, object]]:
        """Aggregate each unique passage once per deal where it occurs."""
        index_by_passage = {passage_id: index for index, passage_id in enumerate(passage_ids)}
        deal_passages: defaultdict[str, set[str]] = defaultdict(set)
        for row in occurrences:
            if row["passage_id"] in index_by_passage:
                deal_passages[row["deal_id"]].add(row["passage_id"])
        rows: list[dict[str, object]] = []
        for deal_id in sorted(deal_passages):
            ids = sorted(deal_passages[deal_id])
            indices = [index_by_passage[passage_id] for passage_id in ids]
            output: dict[str, object] = {"deal_id": deal_id, "passage_count": len(indices)}
            for topic_index in range(solution.k):
                output[label_map[topic_index]] = round(
                    sum(float(solution.weights[index, topic_index]) for index in indices)
                    / len(indices),
                    4,
                )
            dominant = Counter(int(solution.labels[index]) for index in indices)
            output["dominant_topic"] = label_map[dominant.most_common(1)[0][0]]
            rows.append(output)
        return rows

    @staticmethod
    def _topic_group_rows(
        deal_rows: Sequence[dict[str, object]],
        manifest_rows: Sequence[dict[str, object]],
        topic_fields: Sequence[str],
    ) -> list[dict[str, object]]:
        manifest = {str(row["deal_id"]): row for row in manifest_rows}
        groups: defaultdict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        for row in deal_rows:
            meta = manifest.get(str(row["deal_id"]), {})
            for field in ("transaction_form", "ai_category"):
                groups[(field, str(meta.get(field, "unknown")))].append(row)
        output: list[dict[str, object]] = []
        for (field, value), members in sorted(groups.items()):
            row: dict[str, object] = {
                "group_field": field,
                "group_value": value,
                "deal_count": len(members),
            }
            for topic in topic_fields:
                row[topic] = round(
                    sum(_to_float(member.get(topic, 0.0)) for member in members) / len(members),
                    4,
                )
            output.append(row)
        return output

    @staticmethod
    def _word_clouds(
        passages: Sequence[dict[str, str]],
        manifest_rows: Sequence[dict[str, object]],
    ) -> dict[str, dict[str, int]]:
        manifest = {str(row["deal_id"]): row for row in manifest_rows}
        counters: defaultdict[str, Counter[str]] = defaultdict(Counter)
        for passage in passages:
            tokens = [
                token.casefold()
                for token in _WORD.findall(passage.get("model_text") or passage.get("text", ""))
                if token.casefold() not in _CLOUD_STOPWORDS
            ]
            counters["all_qualifying_deals"].update(tokens)
            meta = manifest.get(passage["deal_id"], {})
            counters[f"ai_category:{meta.get('ai_category', 'unknown')}"].update(tokens)
            counters[f"transaction_form:{meta.get('transaction_form', 'unknown')}"].update(tokens)
        return {name: dict(counter.most_common(80)) for name, counter in sorted(counters.items())}

    def stage_analyze(
        self,
        passages: Sequence[dict[str, str]],
        manifest_rows: Sequence[dict[str, object]],
    ) -> dict[str, object]:
        """Run deterministic tone, baseline, topic, stability, and word-use analyses."""
        analysis_path = self.out_dir / "analysis_manifest.json"
        if self._stage_done("analyze", (analysis_path,)):
            return json.loads(analysis_path.read_text(encoding="utf-8"))

        tone_rows = passage_tone_rows(passages) if passages else []
        baselines = []
        adjusted_rows: list[dict[str, object]] = []
        global_means: dict[str, float] = {}
        if tone_rows:
            baselines, global_means = compute_family_baselines(tone_rows, config=BaselineConfig())
            adjusted_rows = apply_baselines(tone_rows, baselines, config=BaselineConfig())
        tone_fields = _field_union(adjusted_rows, ("passage_id", "deal_id", "document_family"))
        _write_csv(self.out_dir / "passage_tone.csv", adjusted_rows, tone_fields)
        baseline_rows = [asdict(row) for row in baselines]
        _write_csv(
            self.out_dir / "document_type_baselines.csv",
            baseline_rows,
            (
                "document_family",
                "metric",
                "mean_rate",
                "group_size",
                "fallback_to_global",
            ),
        )

        deal_tone = deal_tone_summary(tone_rows, baseline_means=global_means) if tone_rows else []
        adjusted_by_deal: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for row in adjusted_rows:
            adjusted_by_deal[str(row["deal_id"])].append(row)
        for row in deal_tone:
            members = adjusted_by_deal[str(row["deal_id"])]
            for metric in LEXICONS:
                key = f"rate_{metric}_per100_adjusted"
                row[key] = round(
                    sum(_to_float(member[key]) for member in members) / len(members), 4
                )
        deal_tone_fields = _field_union(deal_tone, ("deal_id", "passage_count", "total_tokens"))
        _write_csv(self.out_dir / "tone_summary.csv", deal_tone, deal_tone_fields)
        word_fields = [
            "deal_id",
            "passage_count",
            "total_tokens",
            *[f"rate_{metric}_per100" for metric in LEXICONS],
            *[f"rate_{metric}_per100_adjusted" for metric in LEXICONS],
        ]
        _write_csv(self.out_dir / "word_use_comparison.csv", deal_tone, word_fields)

        topic_status = "skipped_insufficient_corpus"
        topic_rows: list[dict[str, object]] = []
        assignment_rows: list[dict[str, object]] = []
        topic_diagnostics: list[dict[str, object]] = []
        matrix_rows: list[dict[str, object]] = []
        stability_rows: list[dict[str, object]] = []
        review_rows: list[dict[str, object]] = []
        group_rows: list[dict[str, object]] = []
        agglomerative_ari: float | str = "not_run"
        texts = [(row["passage_id"], row["model_text"]) for row in passages]
        if len(texts) >= 6:
            try:
                solution, topic_diagnostics = fit_topics(texts, config=self.topics_config)
                label_map = {
                    index: topic_label(terms) for index, terms in solution.top_terms.items()
                }
                for index, passage in enumerate(passages):
                    dominant_index = int(solution.labels[index])
                    row: dict[str, object] = {
                        "passage_id": passage["passage_id"],
                        "deal_id": passage["deal_id"],
                        "document_id": passage["document_id"],
                        "source_url": passage["source_url"],
                        "supporting_excerpt": passage["text"],
                        "dominant_topic": label_map[dominant_index],
                        "dominant_weight": round(float(solution.weights[index, dominant_index]), 4),
                    }
                    for topic_index in range(solution.k):
                        row[label_map[topic_index]] = round(
                            float(solution.weights[index, topic_index]), 4
                        )
                    assignment_rows.append(row)
                for topic_index, terms in solution.top_terms.items():
                    label = label_map[topic_index]
                    topic_rows.append(
                        {
                            "topic_id": topic_index,
                            "topic_label": label,
                            "top_terms": "; ".join(terms),
                            "selected_k": solution.k,
                            "half_sample_stability": solution.stability,
                            "release_status": (
                                "provisional_pending_human_review"
                                if solution.stability >= self.topics_config.stability_threshold
                                else "exploratory_low_stability"
                            ),
                        }
                    )
                    representatives = sorted(
                        assignment_rows,
                        key=lambda row: (
                            -_to_float(row[label]),
                            str(row["passage_id"]),
                        ),
                    )[:10]
                    for rank, representative in enumerate(representatives, start=1):
                        review_rows.append(
                            {
                                "topic_label": label,
                                "rank": rank,
                                "passage_id": representative["passage_id"],
                                "deal_id": representative["deal_id"],
                                "source_url": representative["source_url"],
                                "topic_weight": representative[label],
                                "supporting_excerpt": representative["supporting_excerpt"],
                                "human_fit_label": "",
                                "reviewer_note": "",
                            }
                        )
                occurrences = _read_csv(self.out_dir / "passage_sources.csv")
                matrix_rows = self._deal_topic_matrix(
                    solution,
                    [row["passage_id"] for row in passages],
                    occurrences,
                    label_map,
                )
                topic_fields = [label_map[index] for index in range(solution.k)]
                group_rows = self._topic_group_rows(matrix_rows, manifest_rows, topic_fields)
                agglomerative_ari = agglomerative_sensitivity(
                    texts, solution, config=self.topics_config
                )
                try:
                    stability_rows = leave_one_deal_out_stability(
                        texts,
                        [row["deal_id"] for row in passages],
                        config=self.topics_config,
                    )
                except ValueError as error:
                    stability_rows = [
                        {
                            "held_out_deal": "not_run",
                            "status": f"insufficient_corpus:{type(error).__name__}",
                            "mean_top_term_jaccard": "",
                        }
                    ]
                topic_status = "completed_provisional_pending_human_review"
            except (ValueError, RuntimeError) as error:
                topic_status = f"skipped_model_error:{type(error).__name__}"
                self.log("analyze_topics", "skipped", error=str(error))

        _write_csv(
            self.out_dir / "topic_summary.csv",
            topic_rows,
            (
                "topic_id",
                "topic_label",
                "top_terms",
                "selected_k",
                "half_sample_stability",
                "release_status",
            ),
        )
        _write_csv(
            self.out_dir / "topic_assignments.csv",
            assignment_rows,
            _field_union(
                assignment_rows,
                (
                    "passage_id",
                    "deal_id",
                    "document_id",
                    "source_url",
                    "supporting_excerpt",
                    "dominant_topic",
                    "dominant_weight",
                ),
            ),
        )
        _write_csv(
            self.out_dir / "deal_by_topic.csv",
            matrix_rows,
            _field_union(matrix_rows, ("deal_id", "passage_count", "dominant_topic")),
        )
        _write_csv(
            self.out_dir / "topic_model_diagnostics.csv",
            topic_diagnostics,
            (
                "k",
                "half_sample_stability",
                "reconstruction_error",
                "n_passages",
                "n_features",
            ),
        )
        _write_csv(
            self.out_dir / "topic_stability.csv",
            stability_rows,
            ("held_out_deal", "status", "mean_top_term_jaccard"),
        )
        _write_csv(
            self.out_dir / "topic_review_queue.csv",
            review_rows,
            (
                "topic_label",
                "rank",
                "passage_id",
                "deal_id",
                "source_url",
                "topic_weight",
                "supporting_excerpt",
                "human_fit_label",
                "reviewer_note",
            ),
        )
        _write_csv(
            self.out_dir / "topic_group_comparisons.csv",
            group_rows,
            _field_union(group_rows, ("group_field", "group_value", "deal_count")),
        )

        clouds = self._word_clouds(passages, manifest_rows)
        write_cloud_index(clouds, self.out_dir / "wordclouds.html", config=CloudConfig())
        cloud_dir = self.out_dir / "wordclouds"
        cloud_dir.mkdir(parents=True, exist_ok=True)
        for name, frequencies in clouds.items():
            slug = hashlib.sha256(name.encode()).hexdigest()[:12]
            _atomic_text(
                cloud_dir / f"{slug}.svg",
                render_svg(frequencies, config=CloudConfig(), title=name),
            )

        package_versions = {}
        for package in ("beautifulsoup4", "httpx", "numpy", "scikit-learn"):
            try:
                package_versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                package_versions[package] = "not_installed"
        analysis = {
            "schema_version": 1,
            "generated_at": _now(),
            "python_version": platform.python_version(),
            "package_versions": package_versions,
            "topics_config": asdict(self.topics_config),
            "baseline_config": asdict(BaselineConfig()),
            "passage_count": len(passages),
            "deal_count_with_passages": len({row["deal_id"] for row in passages}),
            "topic_status": topic_status,
            "agglomerative_ari": agglomerative_ari,
            "topic_count": len(topic_rows),
            "tone_deal_count": len(deal_tone),
            "wordcloud_group_count": len(clouds),
            "passages_sha256": _sha256(self.out_dir / "passages.csv"),
            "tone_summary_sha256": _sha256(self.out_dir / "tone_summary.csv"),
            "topic_assignments_sha256": _sha256(self.out_dir / "topic_assignments.csv"),
            "interpretation_boundary": (
                "Textual disclosure characteristics only; no actual-retention or causal claims."
            ),
        }
        _atomic_text(analysis_path, json.dumps(analysis, indent=2, sort_keys=True) + "\n")
        self._mark_stage(
            "analyze",
            passages=len(passages),
            topics=len(topic_rows),
            tone_deals=len(deal_tone),
            topic_status=topic_status,
        )
        return analysis

    def stage_report(
        self,
        manifest_rows: Sequence[dict[str, object]],
        passages: Sequence[dict[str, str]],
        analysis: dict[str, object],
    ) -> dict[str, object]:
        """Write the morning summary, missingness audit, and concise research report."""
        qualifying = [
            row for row in manifest_rows if row.get("verification_status") == QUALIFYING_STATUS
        ]
        unresolved = [row for row in manifest_rows if row not in qualifying]
        inventory = _read_csv(self.out_dir / "document_inventory.csv")
        retrieved = [row for row in inventory if row.get("status") == "retrieved"]
        failed_documents = [row for row in inventory if row.get("status", "").startswith("failed:")]
        zero_deals = _read_csv(self.out_dir / "zero_passage_deals.csv")
        shortfall = max(self.target_deals - len(qualifying), 0)

        reason_counts = Counter(
            str(row.get("missingness_reason") or "none_recorded") for row in unresolved
        )
        quality_lines = [
            "# Data quality and missingness report",
            "",
            f"- Candidate manifest rows: {len(manifest_rows)}",
            f"- Machine-qualified, pending human review: {len(qualifying)}",
            f"- Target: {self.target_deals}",
            f"- Shortfall: {shortfall}",
            f"- Retrieved documents: {len(retrieved)}",
            f"- Failed document retrievals: {len(failed_documents)}",
            f"- Unique employee passages: {len(passages)}",
            f"- Zero-passage qualifying deals: {len(zero_deals)}",
            "",
            "## Missingness reasons",
            "",
        ]
        quality_lines.extend(
            f"- `{reason}`: {count}" for reason, count in sorted(reason_counts.items())
        )
        quality_lines.extend(
            [
                "",
                "## Evidence boundary",
                "",
                (
                    "Machine-qualified rows are not human-verified. Missing disclosure "
                    "is not evidence that an arrangement did not exist. Employee-related "
                    "contract language does not prove actual retention or causation."
                ),
            ]
        )
        _atomic_text(
            self.out_dir / "data_quality_report.md",
            "\n".join(quality_lines) + "\n",
        )

        topic_summary = _read_csv(self.out_dir / "topic_summary.csv")
        evidence_rows = sorted(
            qualifying,
            key=lambda row: (
                str(row.get("announcement_date", "")),
                str(row["deal_id"]),
            ),
        )[:20]
        report = [
            "# AI-Transaction Employee-Disclosure Research Report",
            "",
            "## Research question",
            "",
            (
                "How do source-backed AI-related transactions publicly describe employee, "
                "team, compensation, equity, retention, termination, and integration arrangements?"
            ),
            "",
            "## Scope and inclusion",
            "",
            (
                f"The discovery manifest contains {len(manifest_rows)} candidate transactions. "
                f"Deterministic primary-source screening marked {len(qualifying)} as "
                f"machine-qualified and pending human review, against a target of "
                f"{self.target_deals}. The remaining shortfall is {shortfall}; no generic "
                "merger was added to pad the sample."
            ),
            "",
            (
                "Legal transaction form and talent motive are stored separately. SEC filings "
                "are primary evidence; rows without source-backed AI evidence remain "
                "nonqualifying or unresolved."
            ),
            "",
            "## Corpus and method",
            "",
            (
                f"The run retrieved {len(retrieved)} documents and constructed {len(passages)} "
                "unique employee-related passages while preserving source occurrences and "
                "zero-passage states. The primary unsupervised method is fixed-seed "
                f"word/bigram TF-IDF plus NMF over K={list(self.topics_config.k_range)}. "
                "Document-family lexical baselines control for standardized drafting language. "
                "Tone results are transparent per-100-token lexical rates and describe writing "
                "style, not mental states."
            ),
            "",
            "## Topic status",
            "",
            (
                f"Topic analysis status: `{analysis.get('topic_status', 'unknown')}`. "
                "All themes remain provisional until source-linked representative passages "
                "receive human review."
            ),
            "",
        ]
        if topic_summary:
            report.extend(
                [
                    "| Provisional topic | Top terms | Stability |",
                    "|---|---|---:|",
                ]
            )
            for row in topic_summary:
                report.append(
                    f"| {row['topic_label']} | {row['top_terms']} | "
                    f"{row['half_sample_stability']} |"
                )
            report.append("")
        else:
            report.extend(
                [
                    (
                        "The available corpus was insufficient for a defensible topic fit. "
                        "No topic labels were fabricated."
                    ),
                    "",
                ]
            )
        report.extend(["## Representative source evidence", ""])
        if evidence_rows:
            for row in evidence_rows:
                excerpt = str(row.get("supporting_excerpt", "")).replace("\n", " ").strip()
                report.append(
                    f"- **{row['acquirer_name']}–{row['target_name']}** "
                    f"({row['announcement_date']}): "
                    f"[{row.get('source_document_id') or 'source'}]"
                    f"({row.get('source_url')}) — {excerpt[:500]}"
                )
        else:
            report.append(
                "- No candidate yet passed machine source screening; review the missingness report."
            )
        report.extend(
            [
                "",
                "## Limitations and conclusion",
                "",
                (
                    "This is a selected public-disclosure sample, not a representative census "
                    "of AI transactions. Private documents, unfiled employment terms, and later "
                    "employee outcomes are often not observable. The results are descriptive "
                    "and exploratory. A disclosed retention provision does not establish that "
                    "an employee stayed, and silence does not establish that no arrangement existed."
                ),
                "",
                (
                    f"The current run {'reached' if shortfall == 0 else 'did not reach'} the "
                    f"{self.target_deals}-deal target. Machine-qualified rows still require "
                    "human evidence review before being called verified deals."
                ),
                "",
                "## Reproduction",
                "",
                "```powershell",
                (
                    ".venv\\Scripts\\python.exe -m tag_edgar.overnight "
                    "--candidates data\\derived\\ai_100_candidate_preflight.csv "
                    "--raw-dir data\\raw\\ma_events "
                    "--out-dir data\\derived\\ai_100_overnight"
                ),
                "```",
            ]
        )
        _atomic_text(
            self.out_dir / "final_research_report.md",
            "\n".join(report) + "\n",
        )

        summary = {
            "status": ("complete" if shortfall == 0 and not self.failures else "partial"),
            "target_deals": self.target_deals,
            "manifest_rows": len(manifest_rows),
            "qualifying_machine_rows_pending_human_review": len(qualifying),
            "shortfall": shortfall,
            "retrieved_documents": len(retrieved),
            "failed_documents": len(failed_documents),
            "employee_passages": len(passages),
            "zero_passage_deals": len(zero_deals),
            "topic_status": analysis.get("topic_status", "unknown"),
            "run_failures": len(self.failures),
            "final_report": str(self.out_dir / "final_research_report.md"),
        }
        _atomic_text(
            self.out_dir / "morning_verification_summary.json",
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
        )
        summary_lines = ["# Morning verification summary", ""]
        summary_lines.extend(f"- {key}: {value}" for key, value in summary.items())
        _atomic_text(
            self.out_dir / "morning_verification_summary.md",
            "\n".join(summary_lines) + "\n",
        )
        self._mark_stage("report", **summary)
        return summary

    def run(self) -> int:
        """Execute every stage and return a useful process status code."""
        self.log(
            "run",
            "started",
            target_deals=self.target_deals,
            max_deals=self.max_deals,
        )
        _, manifest_rows = self.stage_freeze_universe()
        passages = self.stage_build_corpus(manifest_rows)
        analysis = self.stage_analyze(passages, manifest_rows)
        summary = self.stage_report(manifest_rows, passages, analysis)
        exit_code = EXIT_OK if summary["status"] == "complete" else EXIT_PARTIAL
        self.state["exit_code"] = exit_code
        self.state["status"] = summary["status"]
        self.save_state()
        self.log(
            "run",
            "finished",
            exit_code=exit_code,
            outcome_status=summary["status"],
        )
        return exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run the deterministic, resumable 100-deal AI transaction pipeline.")
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path("data/derived/ai_100_candidate_preflight.csv"),
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/ma_events"))
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/derived/ai_100_overnight"),
    )
    parser.add_argument("--max-deals", type=int, default=None)
    parser.add_argument("--target-deals", type=int, default=100)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute stages while retaining the respectful HTTP cache.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_deals is not None and args.max_deals < 1:
        print("--max-deals must be positive", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    if args.target_deals < 1:
        print("--target-deals must be positive", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    if not args.candidates.exists() or not args.raw_dir.exists():
        print("Candidate CSV or raw SDC directory is missing.", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    try:
        settings = load_settings(require_user_agent=True)
    except (RuntimeError, TypeError, FileNotFoundError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_CONFIG_ERROR
    with SecClient(
        settings.user_agent,
        settings.cache_dir,
        rate_per_second=settings.rate_per_second,
    ) as client:
        runner = OvernightRun(
            settings=settings,
            client=client,
            candidates_csv=args.candidates,
            raw_dir=args.raw_dir,
            out_dir=args.out_dir,
            max_deals=args.max_deals,
            target_deals=args.target_deals,
            refresh=args.refresh,
        )
        try:
            return runner.run()
        except Exception as error:  # noqa: BLE001 - preserve overnight failure state
            runner._record_failure("run", "pipeline", str(error))
            runner.save_state()
            print(f"Pipeline failed: {error}", file=sys.stderr)
            return EXIT_CONFIG_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
