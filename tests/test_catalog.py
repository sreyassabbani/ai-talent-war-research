import csv
import json
from datetime import date
from pathlib import Path

from tag_edgar.catalog import _best_acquirer_matches, build_catalog, create_review_queue
from tag_edgar.technology import TechnologyScreen


def test_build_catalog_joins_supplement_and_best_acquirer_match(tmp_path: Path) -> None:
    seed = tmp_path / "seed.csv"
    with seed.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "deal_id",
                "announcement_date",
                "effective_date",
                "acquirer_name",
                "acquirer_ticker",
                "target_name",
                "target_ticker",
                "raw_source_row",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "deal_id": "1",
                "announcement_date": "2022-01-10",
                "effective_date": "2022-04-10",
                "acquirer_name": "Buyer",
                "acquirer_ticker": "BUY",
                "target_name": "Target",
                "target_ticker": "TGT",
                "raw_source_row": json.dumps({"Form": "Merger", "Target Primary SIC Code": "7372"}),
            }
        )
    additional = tmp_path / "additional.csv"
    additional.write_text(
        "Source: Thomson Reuters,\nDeal Number,Target Public Status,Consideration Structure,Number of Bidders\n1,Public,Cash,2\n",
        encoding="utf-8",
    )
    matches = tmp_path / "matches.csv"
    matches.write_text(
        "deal_id,party_role,candidate_cik,sec_name,sec_ticker,exchange,match_method,confidence,manual_status,reviewer_note\n"
        "1,acquirer,2,Buyer Inc,BUY,Nasdaq,name,medium,confirmed,ok\n"
        "1,acquirer,1,Wrong,WRONG,Nasdaq,ticker_and_name,high,pending,\n",
        encoding="utf-8",
    )

    rows = build_catalog(seed, additional, matches, metadata_rows=1)

    assert rows[0]["target_public_status"] == "Public"
    assert rows[0]["candidate_cik"] == "2"
    assert rows[0]["cik_manual_status"] == "confirmed"
    assert rows[0]["sdc_form"] == "Merger"


def test_best_acquirer_match_preserves_an_unconfirmed_tie_as_ambiguous(tmp_path: Path) -> None:
    matches = tmp_path / "matches.csv"
    matches.write_text(
        "deal_id,party_role,candidate_cik,sec_name,sec_ticker,exchange,match_method,confidence,manual_status,reviewer_note\n"
        "1,acquirer,1,Buyer One,ONE,Nasdaq,name,medium,pending,\n"
        "1,acquirer,2,Buyer Two,TWO,NYSE,name,medium,pending,\n",
        encoding="utf-8",
    )

    best = _best_acquirer_matches(matches)["1"]

    assert best["candidate_cik"] == ""
    assert best["confidence"] == "ambiguous"
    assert best["match_method"] == "ambiguous_candidates"


def test_review_queue_balances_available_strata(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    fields = [
        "deal_id",
        "announcement_date",
        "cik_match_confidence",
        "sdc_form",
        "target_public_status",
        "transaction_value_mil",
        "target_primary_sic",
    ]
    rows = [
        {
            "deal_id": "1",
            "announcement_date": "2022-01-01",
            "cik_match_confidence": "high",
            "sdc_form": "Merger",
            "target_public_status": "Public",
            "transaction_value_mil": "10",
            "target_primary_sic": "7372",
        },
        {
            "deal_id": "2",
            "announcement_date": "2022-01-02",
            "cik_match_confidence": "medium",
            "sdc_form": "Tender Offer",
            "target_public_status": "Private",
            "transaction_value_mil": "",
            "target_primary_sic": "7372",
        },
    ]
    with catalog.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    queue = create_review_queue(
        catalog,
        TechnologyScreen("test-v1", "test-source", {"7372": "Software"}),
        date(2022, 1, 1),
        date(2022, 12, 31),
        2,
    )

    assert [row["deal_id"] for row in queue] == ["2", "1"]
    assert all(row["pilot_status"] == "review" for row in queue)
    assert all(row["technology_screen_version"] == "test-v1" for row in queue)
