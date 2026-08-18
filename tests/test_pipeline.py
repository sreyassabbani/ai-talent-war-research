import csv
from datetime import date
from pathlib import Path
from typing import Self

from tag_edgar import pipeline
from tag_edgar.models import Deal, Filing
from tag_edgar.settings import Settings


class _FakeSecClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def test_vertical_slice_retrieves_confirmed_acquirer_and_target(
    monkeypatch, tmp_path: Path
) -> None:
    acquirer_filing = Filing(
        "0000789019-21-000001", "0000789019", "8-K", date(2021, 4, 12), None, "msft.htm"
    )
    target_filing = Filing(
        "0001002517-21-000002",
        "0001002517",
        "DEFM14A",
        date(2021, 5, 10),
        None,
        "nuance.htm",
    )

    def fake_fetch(_client: _FakeSecClient, cik: str) -> list[Filing]:
        return [acquirer_filing] if cik == "0000789019" else [target_filing]

    monkeypatch.setattr(pipeline, "SecClient", _FakeSecClient)
    monkeypatch.setattr(pipeline, "fetch_filings", fake_fetch)
    monkeypatch.setattr(pipeline, "enumerate_documents", lambda _client, _filing: [])

    settings = Settings(
        user_agent="Researcher test@example.com",
        cache_dir=tmp_path / "cache",
        rate_per_second=5,
        forms=frozenset({"8-K", "DEFM14A"}),
        document_prefixes=("EX-2.",),
        patterns={},
    )
    deal = Deal(
        deal_id="microsoft-nuance",
        acquirer_cik="789019",
        announcement_date=date(2021, 4, 12),
        effective_date=date(2022, 3, 4),
        target_name="Nuance Communications",
        target_cik="1002517",
    )

    counts = pipeline.run_vertical_slice(deal, settings, tmp_path / "run")

    assert counts["acquirer_filings"] == 1
    assert counts["target_filings"] == 1
    assert counts["filings"] == 2
    assert {row["cik"] for row in _rows(tmp_path / "run" / "filings.csv")} == {
        "0000789019",
        "0001002517",
    }
    assert {row["discovery_route"] for row in _rows(tmp_path / "run" / "deal_filings.csv")} == {
        "acquirer_confirmed_cik",
        "target_confirmed_cik",
    }
    deal_row = _rows(tmp_path / "run" / "deals.csv")[0]
    assert deal_row["target_cik"] == "0001002517"
