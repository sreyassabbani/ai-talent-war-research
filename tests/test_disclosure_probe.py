from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

from tag_edgar.disclosure_pool import load_disclosure_pool_config
from tag_edgar.disclosure_probe import (
    PROBE_FIELDS,
    PROBE_STATUS_RANK,
    ProbeOutcome,
    distinctive_target_tokens,
    probe_deal,
    probe_row,
    target_named_in,
    write_probe_results,
)
from tag_edgar.models import Document, Filing
from tag_edgar.sec_client import SecClient

CONFIG = load_disclosure_pool_config(
    Path(__file__).resolve().parents[1] / "config" / "disclosure_pool.toml"
)
FORMS = frozenset(
    {"8-K", "8-K/A", "S-4", "S-4/A", "DEFM14A", "PREM14A", "SC 14D9", "SC TO-T", "424B3"}
)


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "deal_id": "deal_1",
        "announcement_date": "2021-04-01",
        "effective_date": "2021-09-01",
        "acquirer_name": "Buyer Inc",
        "target_name": "Mailchimp Rocket Science",
        "candidate_cik": "0000000001",
        "transaction_value_mil": "1000",
        "target_public_status": "Priv.",
        "target_candidate_cik": "",
    }
    base.update(overrides)
    return base


def _filing(form: str, day: str, accession: str = "0001-21-000001") -> Filing:
    return Filing(
        accession_number=accession,
        cik="0000000001",
        form=form,
        filing_date=date.fromisoformat(day),
        report_date=None,
        primary_document="primary.htm",
        items=None,
    )


def _document(document_type: str, name: str = "ex21.htm", primary: bool = False) -> Document:
    return Document(
        document_id=f"doc_{name}",
        accession_number="0001-21-000001",
        cik="0000000001",
        sequence="1",
        description=document_type,
        document_name=name,
        document_type=document_type,
        url=f"https://www.sec.gov/Archives/edgar/data/1/000121000001/{name}",
        is_primary=primary,
    )


class FakeClient:
    """Stands in for SecClient: canned submissions, index pages, and document bodies."""

    def __init__(
        self,
        filings: list[Filing],
        documents: dict[str, list[Document]] | None = None,
        bodies: dict[str, bytes] | None = None,
    ) -> None:
        self.filings = filings
        self.documents = documents or {}
        self.bodies = bodies or {}
        self.fetched: list[str] = []

    def get(self, url: str, refresh: bool = False) -> Any:
        self.fetched.append(url)
        body = self.bodies.get(url)
        if body is None:
            raise RuntimeError(f"no body for {url}")

        class _Response:
            content = body

        return _Response()


def _patch(monkeypatch: Any, client: FakeClient) -> None:
    monkeypatch.setattr(
        "tag_edgar.disclosure_probe.fetch_filings", lambda _client, _cik: client.filings
    )
    monkeypatch.setattr(
        "tag_edgar.disclosure_probe.enumerate_documents",
        lambda _client, filing: client.documents.get(filing.accession_number, []),
    )


def test_agreement_exhibit_is_detected_from_the_filing_index(monkeypatch: Any) -> None:
    filing = _filing("8-K", "2021-04-02")
    client = FakeClient(
        [filing],
        {"0001-21-000001": [_document("EX-2.1"), _document("EX-99.1", "ex991.htm")]},
        {
            "https://www.sec.gov/Archives/edgar/data/1/000121000001/ex21.htm": (
                b"Agreement and Plan of Merger with Mailchimp"
            )
        },
    )
    _patch(monkeypatch, client)
    outcome = probe_deal(cast(SecClient, client), _row(), CONFIG, FORMS)
    assert outcome.status == "agreement_exhibit"
    assert outcome.agreement_exhibit_types == ("EX-2.1",)
    assert outcome.target_name_hit == "yes"
    assert outcome.windowed_filings == 1


def test_proxy_without_agreement_is_merger_proxy(monkeypatch: Any) -> None:
    filings = [_filing("8-K", "2021-04-02"), _filing("DEFM14A", "2021-07-15", "0001-21-000002")]
    client = FakeClient(
        filings,
        {"0001-21-000001": [_document("EX-99.1", "ex991.htm")]},
        {
            "https://www.sec.gov/Archives/edgar/data/1/000121000002/primary.htm": (
                b"Proxy statement concerning Mailchimp"
            )
        },
    )
    _patch(monkeypatch, client)
    outcome = probe_deal(cast(SecClient, client), _row(), CONFIG, FORMS)
    assert outcome.status == "merger_proxy"
    # Corroboration falls back to the proxy itself when no agreement exhibit exists.
    assert outcome.target_name_hit == "yes"


def test_announcement_only_and_empty_window(monkeypatch: Any) -> None:
    client = FakeClient([_filing("8-K", "2021-04-02")], {"0001-21-000001": []})
    _patch(monkeypatch, client)
    assert probe_deal(cast(SecClient, client), _row(), CONFIG, FORMS).status == "announcement_only"

    empty = FakeClient([])
    _patch(monkeypatch, empty)
    outcome = probe_deal(cast(SecClient, empty), _row(), CONFIG, FORMS)
    assert outcome.status == "no_transaction_filing"
    assert outcome.windowed_filings == 0


def test_probe_uses_the_retrieval_event_window_not_a_short_window(monkeypatch: Any) -> None:
    """A tender offer 133 days after announcement must still be seen, as Take-Two/Zynga was."""
    late = _filing("SC TO-T", "2021-08-12", "0001-21-000009")
    client = FakeClient([late], {}, {})
    _patch(monkeypatch, client)
    outcome = probe_deal(cast(SecClient, client), _row(), CONFIG, FORMS, confirm_target_name=False)
    assert outcome.status == "merger_proxy"
    assert outcome.window_start == "2021-03-02"
    assert outcome.window_end == "2021-10-01"


def test_unparsable_announcement_date_fails_loudly(monkeypatch: Any) -> None:
    client = FakeClient([])
    _patch(monkeypatch, client)
    outcome = probe_deal(cast(SecClient, client), _row(announcement_date="not-a-date"), CONFIG, FORMS)
    assert outcome.status == "probe_failed"
    assert "unparsable" in outcome.note


def test_generic_tokens_cannot_corroborate_a_deal() -> None:
    assert distinctive_target_tokens("Systems Technologies Inc") == ()
    assert distinctive_target_tokens("Zynga Inc") == ("zynga",)
    assert target_named_in("merger with Zynga Inc.", "Zynga Inc")
    assert not target_named_in("merger with Glu Mobile", "Zynga Inc")


def test_target_name_unconfirmable_is_not_reported_as_a_miss(monkeypatch: Any) -> None:
    filing = _filing("8-K", "2021-04-02")
    client = FakeClient(
        [filing],
        {"0001-21-000001": [_document("EX-2.1")]},
        {"https://www.sec.gov/Archives/edgar/data/1/000121000001/ex21.htm": b"Agreement"},
    )
    _patch(monkeypatch, client)
    outcome = probe_deal(cast(SecClient, client), _row(target_name="Holdings Group Ltd"), CONFIG, FORMS)
    assert outcome.target_name_hit == "no_distinctive_target_tokens"


def test_probe_row_records_confirmation_basis_and_schema(tmp_path: Path) -> None:
    filing_row = _row()
    confirmed = probe_row(
        filing_row,
        ProbeOutcome(
            status="agreement_exhibit",
            window_start="2021-03-02",
            window_end="2021-10-01",
            windowed_filings=4,
            forms=("8-K",),
            agreement_accession="0001-21-000001",
            agreement_exhibit_types=("EX-2.1",),
            target_name_hit="yes",
            note="",
        ),
    )
    assert confirmed["cik_confirmation_basis"] == "machine_target_name_in_acquirer_filing"
    assert set(confirmed) == set(PROBE_FIELDS)

    write_probe_results(tmp_path, [confirmed], {"probed_deals": 1})
    manifest = json.loads((tmp_path / "probe_manifest.json").read_text(encoding="utf-8"))
    assert manifest["probed_deals"] == 1
    assert (tmp_path / "probe_results.csv").read_text(encoding="utf-8").startswith("deal_id,")


def test_status_rank_orders_richest_disclosure_first() -> None:
    assert PROBE_STATUS_RANK["agreement_exhibit"] < PROBE_STATUS_RANK["merger_proxy"]
    assert PROBE_STATUS_RANK["merger_proxy"] < PROBE_STATUS_RANK["announcement_only"]
    assert PROBE_STATUS_RANK["announcement_only"] < PROBE_STATUS_RANK["no_transaction_filing"]
