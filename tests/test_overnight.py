"""Offline integration tests for the resumable 100-deal runner."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from tag_edgar.overnight import EXIT_OK, INVENTORY_FIELDS, OvernightRun
from tag_edgar.sec_client import SecClient
from tag_edgar.settings import Settings
from tag_edgar.topics100 import TopicsConfig
from tag_edgar.universe import QUALIFYING_STATUS, CandidateRow, write_manifest


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_agent="offline-test test@example.com",
        cache_dir=tmp_path / "cache",
        rate_per_second=5,
        forms=frozenset({"8-K"}),
        document_prefixes=("EX-99",),
        patterns={},
    )


def _manifest_row(deal_id: str) -> dict[str, object]:
    return {
        "deal_id": deal_id,
        "target_name": f"Target {deal_id}",
        "acquirer_name": f"Acquirer {deal_id}",
        "announcement_date": "2021-01-01",
        "closing_date": "2021-02-01",
        "transaction_form": "stock acquisition",
        "talent_motive": "talent_signals_present",
        "ai_category": "ai_company",
        "ai_relevance_evidence": "artificial intelligence; machine learning",
        "supporting_excerpt": "Machine learning platform and team will join the acquirer.",
        "source_url": f"https://www.sec.gov/Archives/{deal_id}.htm",
        "source_accession": f"0000000000-21-{deal_id[-6:]}",
        "source_document_id": f"source_{deal_id}",
        "source_quality": "primary_sec_filing",
        "verification_status": QUALIFYING_STATUS,
        "confidence": "high",
        "missingness_reason": "",
        "deal_status": "completed",
        "candidate_score": 10,
        "matched_target_terms": "machine learning",
        "sdc_source_file": "synthetic.csv",
        "sdc_source_row": 2,
    }


def _write_inventory(out_dir: Path, texts: dict[tuple[str, str], str]) -> None:
    rows: list[dict[str, object]] = []
    for (deal_id, document_id), text in sorted(texts.items()):
        deal_dir = out_dir / "corpus_docs" / deal_id
        deal_dir.mkdir(parents=True, exist_ok=True)
        (deal_dir / f"{document_id}.txt").write_text(text, encoding="utf-8")
        rows.append(
            {
                "deal_id": deal_id,
                "document_id": document_id,
                "accession_number": f"accession_{document_id}",
                "form": "8-K",
                "document_type": "EX-99.1",
                "family": "press_release_exhibit",
                "url": f"https://www.sec.gov/Archives/{document_id}.htm",
                "status": "retrieved",
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "char_count": len(text),
                "error": "",
                "transaction_relevance_status": "target_linked",
            }
        )
    with (out_dir / "document_inventory.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(INVENTORY_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


class PreparedRun(OvernightRun):
    """Skip network retrieval while exercising every downstream runner stage."""

    prepared_manifest: list[dict[str, object]]

    def stage_freeze_universe(
        self,
    ) -> tuple[list[CandidateRow], list[dict[str, object]]]:
        return [], self.prepared_manifest


def _runner(tmp_path: Path, name: str) -> PreparedRun:
    out_dir = tmp_path / name
    out_dir.mkdir()
    manifest = [_manifest_row("deal_1"), _manifest_row("deal_2"), _manifest_row("deal_3")]
    write_manifest(out_dir, manifest, {"purpose": "offline_integration_test"})
    texts = {
        ("deal_1", "d1_retention"): (
            "Target deal one employees receive a retention bonus for continued employment "
            "and continued service with the founder team."
        ),
        ("deal_1", "d1_pay"): (
            "Target deal one employee salary wages compensation payroll and incentive award "
            "terms continue after closing."
        ),
        ("deal_1", "d1_equity"): (
            "Target deal one employees receive restricted stock units, equity awards, "
            "vesting terms, and forfeiture provisions."
        ),
        ("deal_1", "d1_exit"): (
            "Target deal one employee severance and termination without cause protections "
            "apply during the change in control period."
        ),
        ("deal_2", "d2_retention"): (
            "Target deal two workers receive a transaction bonus to remain employed and "
            "support workforce continuity."
        ),
        ("deal_2", "d2_pay"): (
            "Target deal two personnel salary compensation bonus and benefits continue "
            "during integration."
        ),
        ("deal_2", "d2_equity"): (
            "Target deal two employees hold stock options and restricted stock units with "
            "service-based vesting."
        ),
        ("deal_2", "d2_exit"): (
            "Target deal two employees have severance benefits after termination without "
            "cause or resignation for good reason."
        ),
        ("deal_3", "d3_zero"): (
            "Target deal three announced an artificial intelligence product launch."
        ),
    }
    _write_inventory(out_dir, texts)
    runner = PreparedRun(
        settings=_settings(tmp_path),
        client=Any,  # type: ignore[arg-type]
        candidates_csv=tmp_path / "unused.csv",
        raw_dir=tmp_path,
        out_dir=out_dir,
        target_deals=3,
        topics_config=TopicsConfig(k_range=(2,), min_df=1, max_features=200),
    )
    runner.prepared_manifest = manifest
    return runner


def test_end_to_end_runner_writes_required_outputs_and_zero_state(tmp_path: Path) -> None:
    runner = _runner(tmp_path, "first")
    assert runner.run() == EXIT_OK

    expected = {
        "passages.csv",
        "passage_sources.csv",
        "deduplication.csv",
        "employee_screen_results.csv",
        "zero_passage_deals.csv",
        "corpus_manifest.json",
        "topic_assignments.csv",
        "topic_summary.csv",
        "deal_by_topic.csv",
        "topic_stability.csv",
        "topic_review_queue.csv",
        "tone_summary.csv",
        "word_use_comparison.csv",
        "document_type_baselines.csv",
        "wordclouds.html",
        "analysis_manifest.json",
        "data_quality_report.md",
        "final_research_report.md",
        "morning_verification_summary.json",
        "state.json",
        "overnight_log.jsonl",
    }
    assert expected <= {path.name for path in runner.out_dir.iterdir()}

    zero_rows = list(
        csv.DictReader((runner.out_dir / "zero_passage_deals.csv").open(encoding="utf-8"))
    )
    assert [row["deal_id"] for row in zero_rows] == ["deal_3"]
    summary = json.loads(
        (runner.out_dir / "morning_verification_summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "complete"
    assert summary["qualifying_machine_rows_pending_human_review"] == 3
    assert summary["zero_passage_deals"] == 1
    report = (runner.out_dir / "final_research_report.md").read_text(encoding="utf-8")
    assert "pending human review" in report
    assert "does not establish that an employee stayed" in report


def test_repeatable_analysis_and_corpus_resume(tmp_path: Path) -> None:
    first = _runner(tmp_path, "first")
    second = _runner(tmp_path, "second")
    assert first.run() == EXIT_OK
    assert second.run() == EXIT_OK

    for name in (
        "passages.csv",
        "passage_sources.csv",
        "topic_assignments.csv",
        "topic_summary.csv",
        "deal_by_topic.csv",
        "tone_summary.csv",
        "word_use_comparison.csv",
        "wordclouds.html",
    ):
        assert (first.out_dir / name).read_bytes() == (second.out_dir / name).read_bytes()

    before = (first.out_dir / "passages.csv").read_bytes()
    source = first.out_dir / "corpus_docs" / "deal_1" / "d1_retention.txt"
    source.write_text("employee content changed after checkpoint", encoding="utf-8")
    resumed = first.stage_build_corpus(first.prepared_manifest)
    assert resumed
    assert (first.out_dir / "passages.csv").read_bytes() == before


def test_unresolved_cik_writes_explicit_row_and_resumes_without_network(
    tmp_path: Path,
) -> None:
    candidates = tmp_path / "candidates.csv"
    candidates.write_text(
        "deal_id,announcement_date,target_name,acquirer_name,source_file,"
        "source_row_number,candidate_score,matched_target_terms,selection_status\n"
        "deal_x,2021-01-01,WidgetMind,Private Buyer,ma_test.csv,2,5,ai,"
        "selected_candidate\n",
        encoding="utf-8",
    )
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "ma_test.csv").write_text(
        "Source: test,,,,\n"
        "Deal Number,Date Announced,Date Effective,Target Name,Form\n"
        '"deal_x","01/01/21","02/01/21","WidgetMind","Merger"\n',
        encoding="utf-8-sig",
    )

    class RegistryOnlyClient:
        calls = 0

        def get_json(self, _url: str) -> dict[str, object]:
            self.calls += 1
            return {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [["1", "Unrelated Public Corp", "UPC", "NYSE"]],
            }

    fake = RegistryOnlyClient()
    out_dir = tmp_path / "unresolved"
    run = OvernightRun(
        settings=_settings(tmp_path),
        client=cast(SecClient, fake),
        candidates_csv=candidates,
        raw_dir=raw_dir,
        out_dir=out_dir,
        target_deals=1,
    )
    _, rows = run.stage_freeze_universe()
    assert fake.calls == 1
    assert rows[0]["verification_status"] == "not_qualifying_no_primary_source_found"
    assert rows[0]["missingness_reason"] == "acquirer_not_resolved_on_edgar"
    assert (out_dir / "document_inventory.csv").exists()

    resumed_client = RegistryOnlyClient()
    resumed = OvernightRun(
        settings=_settings(tmp_path),
        client=cast(SecClient, resumed_client),
        candidates_csv=candidates,
        raw_dir=raw_dir,
        out_dir=out_dir,
        target_deals=1,
    )
    _, resumed_rows = resumed.stage_freeze_universe()
    assert resumed_client.calls == 0
    assert resumed_rows[0]["deal_id"] == "deal_x"
