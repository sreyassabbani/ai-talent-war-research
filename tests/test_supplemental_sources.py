from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, cast

import pytest

from tag_edgar.overnight import OvernightRun
from tag_edgar.sec_client import CachedResponse, SecClient
from tag_edgar.settings import Settings
from tag_edgar.supplemental_sources import (
    load_supplemental_sources,
    retrieve_supplemental_documents,
)
from tag_edgar.universe import QUALIFYING_STATUS


def _source_csv(path: Path, *, url: str = "https://buyer.example/news/target") -> Path:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "deal_id",
                "source_url",
                "source_quality",
                "publisher",
                "publication_date",
                "source_title",
                "review_status",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "deal_id": "deal_x",
                "source_url": url,
                "source_quality": "official_company_announcement",
                "publisher": "Private Buyer",
                "publication_date": "2021-01-01",
                "source_title": "Private Buyer acquires WidgetMind",
                "review_status": "approved_for_machine_screening",
                "notes": "",
            }
        )
    return path


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_agent="offline-test test@example.com",
        cache_dir=tmp_path / "cache",
        rate_per_second=5,
        forms=frozenset({"8-K"}),
        document_prefixes=("EX-99",),
        patterns={},
    )


class SourceClient:
    def get_json(self, _url: str) -> dict[str, object]:
        return {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [["1", "Unrelated Public Corp", "UPC", "NYSE"]],
        }

    def get(self, url: str) -> CachedResponse:
        return CachedResponse(
            url=url,
            content=(
                b"<html><body>Private Buyer acquired WidgetMind, an artificial intelligence "
                b"and machine learning platform. The WidgetMind engineering team will join "
                b"Private Buyer after closing.</body></html>"
            ),
            content_type="text/html",
            from_cache=False,
        )


def test_load_sources_rejects_non_https_approved_rows(tmp_path: Path) -> None:
    path = _source_csv(tmp_path / "sources.csv", url="http://buyer.example/news/target")
    with pytest.raises(ValueError, match="HTTPS"):
        load_supplemental_sources(path)


def test_retrieve_source_records_provenance(tmp_path: Path) -> None:
    sources = load_supplemental_sources(_source_csv(tmp_path / "sources.csv"))["deal_x"]
    texts, records, quality = retrieve_supplemental_documents(
        SourceClient(), deal_id="deal_x", sources=sources
    )
    assert len(texts) == 1
    assert records[0].status == "retrieved"
    assert records[0].family == "official_announcement"
    assert quality[records[0].document_id] == "official_company_announcement"


def test_private_buyer_can_qualify_from_approved_official_source(tmp_path: Path) -> None:
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
    out_dir = tmp_path / "out"
    runner = OvernightRun(
        settings=_settings(tmp_path),
        client=cast(SecClient, cast(Any, SourceClient())),
        candidates_csv=candidates,
        raw_dir=raw_dir,
        out_dir=out_dir,
        target_deals=1,
        supplemental_sources_csv=_source_csv(tmp_path / "sources.csv"),
    )
    _, rows = runner.stage_freeze_universe()
    assert rows[0]["verification_status"] == QUALIFYING_STATUS
    assert rows[0]["source_quality"] == "official_company_announcement"
    assert rows[0]["talent_motive"] == "documented_team_join_language"
    assert "WidgetMind" in str(rows[0]["supporting_excerpt"])
