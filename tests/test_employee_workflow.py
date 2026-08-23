import csv
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tag_edgar.cli import app
from tag_edgar.employee_topics import (
    AssignmentRow,
    DiagnosticRow,
    EmployeeTopicResult,
    TopicRow,
)
from tag_edgar.employee_workflow import (
    _document_eligibility,
    _normalize_party_names,
    _passage_eligibility,
    _provision_family_ids,
    analyze_employee_topics_workflow,
    build_employee_corpus_workflow,
    summarize_employee_topics_workflow,
)


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _review(path: Path) -> None:
    _write(
        path,
        ["deal_id", "acquirer_name", "target_name", "pilot_status"],
        [
            {
                "deal_id": "deal-1",
                "acquirer_name": "Buyer One",
                "target_name": "Target One",
                "pilot_status": "selected",
            },
            {
                "deal_id": "deal-2",
                "acquirer_name": "Buyer Two",
                "target_name": "Target Two",
                "pilot_status": "selected",
            },
            {
                "deal_id": "deal-3",
                "acquirer_name": "Buyer Three",
                "target_name": "Target Three",
                "pilot_status": "selected",
            },
        ],
    )


def _cached_document(runs: Path, cache: Path, deal_id: str, document_id: str, body: bytes) -> None:
    url = f"https://www.sec.gov/Archives/{document_id}.htm"
    _write(
        runs / deal_id / "documents.csv",
        [
            "document_id",
            "accession_number",
            "description",
            "document_name",
            "document_type",
            "url",
            "is_primary",
        ],
        [
            {
                "document_id": document_id,
                "accession_number": f"accession-{document_id}",
                "description": "Merger agreement",
                "document_name": f"{document_id}.htm",
                "document_type": "EX-2.1",
                "url": url,
                "is_primary": "False",
            }
        ],
    )
    digest = hashlib.sha256(url.encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{digest}.body").write_bytes(body)
    (cache / f"{digest}.json").write_text(
        json.dumps({"content_type": "text/html"}), encoding="utf-8"
    )


def test_workflows_deduplicate_globally_but_propagate_topics_to_each_deal(
    monkeypatch, tmp_path: Path
) -> None:
    review = tmp_path / "review.csv"
    runs = tmp_path / "runs"
    cache = tmp_path / "cache"
    corpus_dir = tmp_path / "corpus"
    analysis_dir = tmp_path / "analysis"
    report_dir = tmp_path / "report"
    _review(review)
    body = b"<h2>Employee Matters</h2><p>Key employees receive a retention bonus.</p>"
    _cached_document(runs, cache, "deal-1", "doc-1", body)
    _cached_document(runs, cache, "deal-2", "doc-2", body)

    corpus_summary = build_employee_corpus_workflow(review, runs, corpus_dir, cache)

    passages = _rows(corpus_dir / "passages.csv")
    sources = _rows(corpus_dir / "passage_sources.csv")
    assert corpus_summary.counts["deals"] == 3
    assert len(passages) == 1
    assert len(sources) == 2
    assert {row["deal_id"] for row in sources} == {"deal-1", "deal-2"}
    assert passages[0]["inclusion_status"] == "included"
    assert passages[0]["raw_text"] == passages[0]["text"]
    corpus_manifest = json.loads((corpus_dir / "corpus_manifest.json").read_text())
    assert corpus_manifest["schema_version"] == 2
    assert corpus_manifest["screened_candidate_passages"] == 1
    assert corpus_manifest["included_screened_passages"] == 1
    assert corpus_manifest["excluded_screened_passages"] == 0
    assert "canonical_passages" not in corpus_manifest

    passage = passages[0]
    fake_result = EmployeeTopicResult(
        status="modeled",
        reason=None,
        assignments=(
            AssignmentRow(
                passage_id=passage["passage_id"],
                deal_id=passage["deal_id"],
                document_id=passage["document_id"],
                document_family_id=passage["document_family_id"],
                source_url=passage["source_url"],
                topic_id="topic_1",
                topic_weight=1.0,
                primary_topic=True,
            ),
        ),
        topics=(
            TopicRow(
                topic_id="topic_1",
                top_terms=("retention bonus", "employees"),
                primary_passage_count=1,
                document_family_count=1,
                deal_count=1,
                coherence=0.4,
                stability_median_cosine=0.9,
                stability_recovery_rate=0.8,
                assignment_specificity=0.75,
                top_positive_residual_terms=("service", "continuity"),
                top_positive_residual_scores=(0.12, 0.08),
            ),
        ),
        deal_topics=(),
        diagnostics=(
            DiagnosticRow("stability", "overall_recovery_rate", 0.8, "pass", "Measured."),
        ),
        sensitivity_assignments=(),
        stability=(),
    )
    monkeypatch.setattr(
        "tag_edgar.employee_workflow.analyze_employee_topics_csv",
        lambda _path, _config: fake_result,
    )

    analysis_summary = analyze_employee_topics_workflow(review, corpus_dir, analysis_dir)

    assert analysis_summary.status == "modeled"
    deal_topics = _rows(analysis_dir / "deal_topic_matrix.csv")
    assert {(row["deal_id"], row["topic_id"]) for row in deal_topics} == {
        ("deal-1", "topic_1"),
        ("deal-2", "topic_1"),
        ("deal-3", ""),
    }
    assert (
        next(row for row in deal_topics if row["deal_id"] == "deal-2")["normalized_weight"] == "1"
    )
    assert (
        next(row for row in deal_topics if row["deal_id"] == "deal-3")["zero_state"]
        == "no_employee_passages"
    )
    assert (
        (analysis_dir / "deal_topic_heatmap.svg")
        .read_text(encoding="utf-8")
        .startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    )
    analysis_manifest = json.loads((analysis_dir / "analysis_manifest.json").read_text())
    assert analysis_manifest["status"] == "modeled"
    assert analysis_manifest["schema_version"] == 3
    assert analysis_manifest["config"]["bootstrap_replicates"] == 100
    assert analysis_manifest["bootstrap_design"] == {
        "alignment": "one_to_one_maximum_total_cosine",
        "fit_universe": "same_deal_balanced_family_level_rows_as_full_nmf_fit",
        "per_deal_sample_size": "preserve_original_fit_row_count",
        "projected_passages_included": False,
        "purpose": "complementary_robustness_diagnostic_not_model_selection",
        "recovery_cosine_threshold": 0.7,
        "replacement": True,
        "sampling_scope": "within_deal",
        "sampling_unit": "deal_provision_family_representative",
        "seed_formula": "config.seed + 1700003 + replicate_id",
        "vocabulary": "fixed_from_full_fit",
    }
    assert _rows(analysis_dir / "bootstrap_stability.csv") == []
    assert _rows(analysis_dir / "bootstrap_summary.csv") == []
    assert _rows(analysis_dir / "embedding_robustness_assignments.csv") == []
    assert analysis_manifest["embedding_robustness_design"]["input_features"] == (
        "word_bigram_tfidf"
    )
    assert analysis_manifest["embedding_robustness_design"]["methods"][0]["name"] == (
        "sklearn_hdbscan"
    )
    assert analysis_manifest["reporting_metric_definitions"] == {
        "assignment_specificity": (
            "mean normalized top-topic minus runner-up weight margin among passages whose "
            "primary assignment is the topic; model concentration, not substantive certainty"
        ),
        "disclosure_salience": (
            "mean deal-normalized topic share across every selected deal; explicit-zero deals "
            "contribute zero; comparative disclosure share, not importance, concern, or outcome"
        ),
        "top_positive_residual_terms": (
            "highest mean positive TF-IDF reconstruction residual max(X-WH,0) within the "
            "topic's primary passages"
        ),
    }
    summary_row = _rows(analysis_dir / "topic_summary.csv")[0]
    assert float(summary_row["disclosure_salience"]) == pytest.approx(2 / 3)
    assert summary_row["assignment_specificity"] == "0.75"
    assert summary_row["top_positive_residual_terms"] == "service|continuity"
    assert summary_row["top_positive_residual_scores"] == "0.12|0.08"
    assert {
        row["disclosure_salience"] for row in _rows(analysis_dir / "topic_assignments.csv")
    } == {summary_row["disclosure_salience"]}

    report_summary = summarize_employee_topics_workflow(
        review, corpus_dir, analysis_dir, report_dir
    )

    assert report_summary.status == "pass"
    report = (report_dir / "employee_topics_report.md").read_text(encoding="utf-8")
    assert "Buyer Two–Target Two" in report
    assert "no employee passages" in report
    assert _rows(report_dir / "topic_review.csv")[0]["topic_id"] == "topic_1"


def test_employee_workflow_commands_are_exposed() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "build-employee-corpus" in result.stdout
    assert "analyze-employee-topics" in result.stdout
    assert "summarize-employee-topics" in result.stdout


def test_near_duplicate_legal_provisions_share_a_deterministic_family() -> None:
    base = (
        "employee matters continuing employees shall receive salary bonus benefits equity awards "
        "and vesting treatment under the agreement after closing subject to applicable law and "
        "company policies"
    )
    passages = [
        {"passage_id": "passage-a", "model_text": base},
        {"passage_id": "passage-b", "model_text": base.replace("company", "buyer")},
        {
            "passage_id": "passage-c",
            "model_text": "founder leadership reporting lines remain after closing",
        },
    ]

    first = _provision_family_ids(passages)
    second = _provision_family_ids(list(reversed(passages)))

    assert first == second
    assert first["passage-a"] == first["passage-b"]
    assert first["passage-a"] != first["passage-c"]


def test_document_gate_excludes_unrelated_earnings_and_validates_positive_source(
    tmp_path: Path,
) -> None:
    review = tmp_path / "review.csv"
    runs = tmp_path / "runs"
    cache = tmp_path / "cache"
    output = tmp_path / "corpus"
    _review(review)
    announcement_url = "https://www.sec.gov/Archives/announcement.htm"
    earnings_url = "https://www.sec.gov/Archives/earnings.htm"
    _write(
        runs / "deal-1" / "documents.csv",
        [
            "document_id",
            "accession_number",
            "description",
            "document_name",
            "document_type",
            "url",
            "is_primary",
        ],
        [
            {
                "document_id": "announcement",
                "accession_number": "accession-announcement",
                "description": "Acquisition announcement",
                "document_name": "announcement.htm",
                "document_type": "EX-99.1",
                "url": announcement_url,
                "is_primary": "False",
            },
            {
                "document_id": "earnings",
                "accession_number": "accession-earnings",
                "description": "Quarterly earnings",
                "document_name": "earnings.htm",
                "document_type": "EX-99.1",
                "url": earnings_url,
                "is_primary": "False",
            },
        ],
    )
    _write(
        runs / "deal-1" / "filings.csv",
        ["accession_number", "form"],
        [
            {"accession_number": "accession-announcement", "form": "8-K"},
            {"accession_number": "accession-earnings", "form": "8-K"},
        ],
    )
    _write(runs / "deal-1" / "evidence.csv", ["document_id", "category"], [])
    bodies = {
        announcement_url: (
            b"<h2>Acquisition</h2><p>Buyer One will acquire Target One. Its chief executive "
            b"officer will remain and report to Buyer One.</p>"
        ),
        earnings_url: (
            b"<h2>Quarterly results</h2><p>Stock-based compensation expense increased in the "
            b"three months ended.</p>"
        ),
    }
    cache.mkdir(parents=True)
    for url, body in bodies.items():
        digest = hashlib.sha256(url.encode()).hexdigest()
        (cache / f"{digest}.body").write_bytes(body)
        (cache / f"{digest}.json").write_text(
            json.dumps({"content_type": "text/html"}), encoding="utf-8"
        )
    manual = tmp_path / "manual.csv"
    _write(
        manual,
        ["deal_id", "source_url", "manual_employee_term_code"],
        [
            {
                "deal_id": "deal-1",
                "source_url": announcement_url,
                "manual_employee_term_code": "leadership_continuity",
            }
        ],
    )

    summary = build_employee_corpus_workflow(
        review,
        runs,
        output,
        cache,
        manual_coding_csv=manual,
    )

    eligibility = {row["document_id"]: row for row in _rows(output / "document_eligibility.csv")}
    assert eligibility["announcement"]["decision_reason"] == (
        "included_target_transaction_proximity"
    )
    assert eligibility["earnings"]["decision_reason"] == (
        "excluded_unrelated_event_window_document"
    )
    assert _rows(output / "manual_source_validation.csv")[0]["validation_status"] == "pass"
    assert summary.counts["documents_included"] == 1


def test_8k_transaction_accession_does_not_blanket_include_unrelated_exhibits() -> None:
    row = {"document_type": "EX-10.1", "accession_number": "transaction-accession"}

    excluded = _document_eligibility(
        row,
        "8-K",
        frozenset({"transaction-accession"}),
        0,
        "Target One",
        "Target One acquisition amended and restated credit agreement with the lenders.",
    )
    included = _document_eligibility(
        row,
        "8-K",
        frozenset({"transaction-accession"}),
        0,
        "Target One",
        "After the Target One acquisition, continuing employees receive transaction bonuses.",
    )

    assert excluded[:2] == (False, "excluded_nontransaction_8k_exhibit")
    assert included[:2] == (True, "included_transaction_employee_action_exhibit")


def test_manual_positive_source_requires_an_included_passage_and_persists_diagnostic(
    tmp_path: Path,
) -> None:
    review = tmp_path / "review.csv"
    runs = tmp_path / "runs"
    cache = tmp_path / "cache"
    output = tmp_path / "corpus"
    _review(review)
    source_url = "https://www.sec.gov/Archives/safe-harbor.htm"
    _write(
        runs / "deal-1" / "documents.csv",
        [
            "document_id",
            "accession_number",
            "description",
            "document_name",
            "document_type",
            "url",
            "is_primary",
        ],
        [
            {
                "document_id": "safe-harbor",
                "accession_number": "accession-safe-harbor",
                "description": "Merger agreement",
                "document_name": "safe-harbor.htm",
                "document_type": "EX-2.1",
                "url": source_url,
                "is_primary": "False",
            }
        ],
    )
    body = b"<h2>Forward-Looking Statements</h2><p>Employee retention risks may increase.</p>"
    digest = hashlib.sha256(source_url.encode()).hexdigest()
    cache.mkdir(parents=True)
    (cache / f"{digest}.body").write_bytes(body)
    (cache / f"{digest}.json").write_text(
        json.dumps({"content_type": "text/html"}), encoding="utf-8"
    )
    manual = tmp_path / "manual.csv"
    _write(
        manual,
        ["deal_id", "source_url", "manual_employee_term_code"],
        [
            {
                "deal_id": "deal-1",
                "source_url": source_url,
                "manual_employee_term_code": "retention",
            }
        ],
    )

    with pytest.raises(ValueError, match="positive_source_has_no_qualifying_passage"):
        build_employee_corpus_workflow(
            review,
            runs,
            output,
            cache,
            manual_coding_csv=manual,
        )

    diagnostic = _rows(output / "manual_source_validation.csv")[0]
    assert diagnostic["document_inclusion_status"] == "included"
    assert diagnostic["qualifying_passage_count"] == "0"
    assert diagnostic["validation_status"] == "positive_source_has_no_qualifying_passage"


def test_passage_gate_removes_safe_harbor_accounting_and_uncontextualized_generic_hits() -> None:
    assert _passage_eligibility(
        ("retention",), "forward-looking statements discuss employee retention risks"
    ) == (False, "excluded_safe_harbor_or_forward_looking_context")
    assert _passage_eligibility(
        ("employee", "compensation"),
        "employee stock-based compensation expense for the three months ended",
    ) == (False, "excluded_accounting_or_financial_context")
    assert _passage_eligibility(("executive officer",), "chief executive officer address") == (
        False,
        "excluded_generic_term_without_people_context",
    )
    assert _passage_eligibility(
        ("executive officer",), "the chief executive officer will remain and report to the buyer"
    ) == (True, "included_employee_context")


def test_passage_gate_disambiguates_retention_and_nonemployee_ip_contexts() -> None:
    assert _passage_eligibility(
        ("retention",),
        "privacy policies govern the retention and use of personal information from individuals",
    ) == (False, "excluded_nonemployee_privacy_or_ip_context")
    assert _passage_eligibility(
        ("retain",), "the combined company will retain a strong office presence in israel"
    ) == (False, "excluded_generic_term_without_people_context")
    assert _passage_eligibility(
        ("personnel",),
        "personnel with source code access sign confidentiality agreements protecting trade secrets",
    ) == (False, "excluded_nonemployee_privacy_or_ip_context")
    assert _passage_eligibility(
        ("retention", "bonus"), "each key employee receives a retention bonus after closing"
    ) == (True, "included_employee_context")


def test_passage_gate_preserves_leadership_continuity_and_equity_treatment() -> None:
    assert _passage_eligibility(
        ("executive officer",),
        "the chief executive officer will continue to serve and report to the buyer",
    ) == (True, "included_employee_context")
    assert _passage_eligibility(
        ("restricted stock unit", "vesting"),
        "each unvested restricted stock unit will be assumed at the effective time",
    ) == (True, "included_employee_context")


def test_passage_gate_excludes_generic_proxy_litigation_and_representative_language() -> None:
    assert _passage_eligibility(
        ("employees",),
        "proxies may be solicited by directors officers and employees by mail telephone or facsimile",
    ) == (False, "excluded_proxy_solicitation_logistics")
    assert _passage_eligibility(
        ("employees",),
        "the individual defendants controlled the company and all employees and are liable pursuant to the exchange act",
    ) == (False, "excluded_litigation_allegation_context")
    assert _passage_eligibility(
        ("employees",),
        "representative shall mean a person's directors officers employees agents advisors and consultants",
    ) == (False, "excluded_generic_representative_definition")
    assert _passage_eligibility(
        ("employees",),
        "the merger may divert the attention of management and employee teams toward completion of the transaction",
    ) == (False, "excluded_generic_term_without_people_context")
    assert _passage_eligibility(
        ("employees", "benefit plan"),
        "continuing employees will receive benefits under the parent benefit plan after closing",
    ) == (True, "included_employee_context")


def test_model_text_masks_party_names_without_changing_other_words() -> None:
    normalized = _normalize_party_names(
        "unity software and ironsource employees will remain with unity after closing",
        "Unity Software Inc",
        "ironSource Ltd",
    )

    assert normalized == (
        "entitytoken and entitytoken employees will remain with entitytoken after closing"
    )
