"""Offline tests for universe freezing and document retrieval."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tag_edgar.deal_retrieval import (
    candidate_documents,
    document_family,
    html_to_text,
    retrieve_deal_documents,
)
from tag_edgar.models import Document as EdgarDocument
from tag_edgar.models import Filing
from tag_edgar.universe import (
    CandidateRow,
    DocumentText,
    assess_deal_documents,
    assessment_window,
    filings_in_window,
    load_sdc_form,
    manifest_row,
)

AI_BODY = (
    "Acme Corp today announced the acquisition of WidgetMind, whose machine learning "
    "platform helps enterprises deploy artificial intelligence applications. "
    "WidgetMind's founding team will join Acme's cloud division."
)
PLAIN_BODY = "Acme Corp announced a routine quarterly update about office facilities."


def _doc_text(document_id: str, text: str) -> DocumentText:
    return DocumentText(
        document_id=document_id,
        accession_number="0001234567-21-000001",
        url=f"https://www.sec.gov/Archives/ex{document_id}.htm",
        document_type="EX-99.1",
        text=text,
    )


def _candidate() -> CandidateRow:
    return CandidateRow(
        deal_id="3312269020",
        announcement_date=date(2021, 6, 15),
        target_name="WidgetMind",
        acquirer_name="Acme Corp",
        source_file="ma_1520.csv",
        source_row_number=34461,
        candidate_score=10,
        matched_terms="machine learning",
        selection_status="selected_candidate",
    )


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content


INDEX_HTML = """<html><body><table>
<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr>
<tr><td>1</td><td>8-K</td><td><a href="body.htm">body.htm</a></td><td>8-K</td></tr>
<tr><td>2</td><td>Press release</td><td><a href="ex991.htm">ex991.htm</a></td><td>EX-99.1</td></tr>
</table></body></html>"""


class FakeClient:
    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.requested.append(url)
        if url not in self.pages:
            raise RuntimeError(f"404 for {url}")
        return FakeResponse(self.pages[url])


def test_assessment_qualifies_with_name_and_excerpt() -> None:
    documents = [_doc_text("doc_a", AI_BODY), _doc_text("doc_b", PLAIN_BODY)]
    assessment = assess_deal_documents(
        "deal_1", documents, target_name="WidgetMind", sdc_form="Merger"
    )
    assert assessment.qualifies
    assert assessment.confidence in {"high", "medium"}
    assert "artificial intelligence" in "".join(assessment.distinct_terms)
    assert assessment.transaction_form == "statutory merger"
    assert "machine learning" in assessment.supporting_excerpt
    assert assessment.source_accession == "0001234567-21-000001"


def test_assessment_nonqualifying_records_missingness() -> None:
    documents = [_doc_text("doc_b", PLAIN_BODY)]
    assessment = assess_deal_documents("deal_2", documents, target_name="WidgetMind", sdc_form=None)
    assert not assessment.qualifies
    assert assessment.verification_status.endswith("no_primary_source_found")
    assert assessment.missingness_reason == "no_target_mention_in_retrieved_documents"
    row = manifest_row(_candidate(), assessment, None)
    assert row["closing_date"] == "unknown"
    assert row["deal_status"] == "unclear"
    assert row["source_quality"] == "not_applicable"


def test_manifest_row_fields_complete() -> None:
    documents = [_doc_text("doc_a", AI_BODY)]
    assessment = assess_deal_documents(
        "deal_1", documents, target_name="WidgetMind", sdc_form="Merger"
    )
    row = manifest_row(_candidate(), assessment, date(2021, 7, 1))
    expected = {
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
    }
    assert expected <= set(row)


def test_assessment_window_bounds() -> None:
    start, end = assessment_window(date(2021, 6, 15), date(2021, 7, 1))
    assert start == date(2021, 5, 16)
    assert end == date(2021, 7, 31)


def test_filings_in_window_filters_forms_and_dates() -> None:
    filings = [
        Filing("a", "1", "10-Q", date(2021, 5, 1), None, None),
        Filing("b", "1", "8-K", date(2021, 6, 14), None, None),
        Filing("c", "1", "8-K", date(2021, 9, 1), None, None),
    ]
    selected = filings_in_window(filings, date(2021, 5, 16), date(2021, 7, 31), frozenset({"8-K"}))
    assert [filing.accession_number for filing in selected] == ["b"]


def test_document_families() -> None:
    assert document_family("8-K", "EX-2.1") == "merger_agreement"
    assert document_family("8-K", "EX-99.1") == "press_release_exhibit"
    assert document_family("8-K", "EX-10.3") == "employment_or_plan"
    assert document_family("DEFM14A", "DEFM14A") == "proxy_statement"
    assert document_family("8-K", "8-K") == "current_report_body"
    assert document_family("10-K", "") == "other"


def test_candidate_documents_priority_order() -> None:
    primary = EdgarDocument("d1", "a", "1", "1", None, "body.htm", "8-K", "u/body.htm", True)
    exhibit99 = EdgarDocument(
        "d2", "a", "1", "2", None, "ex991.htm", "EX-99.1", "u/e991.htm", False
    )
    exhibit10 = EdgarDocument(
        "d3", "a", "1", "3", None, "ex103.htm", "EX-10.3", "u/e103.htm", False
    )
    ordered = candidate_documents([exhibit10, primary, exhibit99])
    types = [item.document_type for item in ordered]
    assert types == ["EX-99.1", "EX-10.3", "8-K"]


def test_html_to_text_strips_markup() -> None:
    body = b"<html><body><p>Artificial intelligence platform</p></body></html>"
    text = html_to_text(body, "text/html")
    assert "Artificial intelligence platform" in text
    assert "<p>" not in text


def test_html_to_text_detects_late_html_inside_sec_submission_text() -> None:
    body = (
        b"<SEC-DOCUMENT>\n"
        + (b"metadata line\n" * 150)
        + b'<TABLE style="margin-top:0pt"><TR><TD valign="bottom">Employees</TD></TR></TABLE>'
    )
    text = html_to_text(body, "text/plain")
    assert "Employees" in text
    assert "valign" not in text
    assert "margin-top" not in text


def test_retrieve_deal_documents_statuses_and_texts() -> None:
    filing = Filing(
        "0001234567-21-000001", "0001234567", "8-K", date(2021, 6, 16), None, "body.htm"
    )
    base = "https://www.sec.gov/Archives/edgar/data/1234567/000123456721000001"
    client = FakeClient(
        {
            f"{base}/0001234567-21-000001-index.html": INDEX_HTML.encode(),
            f"{base}/body.htm": b"<html><body><p>Quarterly results discussion.</p></body></html>",
            f"{base}/ex991.htm": AI_BODY.encode(),
        }
    )
    texts, records = retrieve_deal_documents(client, deal_id="deal_1", filings=[filing])
    assert all(record.status == "retrieved" for record in records)
    joined = " ".join(text for _, text in texts)
    assert "machine learning" in joined
    assert any(record.content_sha256 for record in records)


def test_retrieve_deal_documents_records_failures() -> None:
    filing = Filing(
        "0001234567-21-000002", "0001234567", "8-K", date(2021, 6, 16), None, "body.htm"
    )
    client = FakeClient({})  # everything fails
    texts, records = retrieve_deal_documents(client, deal_id="deal_x", filings=[filing])
    assert texts == []
    assert records
    assert all(record.status.startswith("failed:") for record in records)


def test_load_sdc_form_recovers_form_and_effective_date(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    content = (
        "Source: Thomson Reuters   Date: 12/06/2022,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "Deal Number,Date Announced,Date Effective,Target Name,Form\n"
        '"123","06/15/21","07/01/21","WidgetMind","Merger"\n'
        '"124","06/15/21","","OtherCo","Acq. of Assets"\n'
    )
    (raw_dir / "ma_1520.csv").write_text(content, encoding="utf-8-sig")
    form, effective = load_sdc_form(raw_dir, "ma_1520.csv", 2)
    assert form == "Merger"
    assert effective == date(2021, 7, 1)
    form_none, effective_none = load_sdc_form(raw_dir, "ma_1520.csv", 3)
    assert form_none == "Acq. of Assets"
    assert effective_none is None
