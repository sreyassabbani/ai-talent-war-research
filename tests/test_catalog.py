import csv
import json
from datetime import date
from pathlib import Path

from tag_edgar.catalog import build_catalog, create_review_queue


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
        "1,acquirer,2,Wrong,WRONG,Nasdaq,name,medium,pending,\n"
        "1,acquirer,1,Buyer Inc,BUY,Nasdaq,ticker_and_name,high,confirmed,ok\n",
        encoding="utf-8",
    )

    rows = build_catalog(seed, additional, matches, metadata_rows=1)

    assert rows[0]["target_public_status"] == "Public"
    assert rows[0]["candidate_cik"] == "1"
    assert rows[0]["sdc_form"] == "Merger"


def test_review_queue_balances_available_strata(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    fields = [
        "deal_id",
        "announcement_date",
        "cik_match_confidence",
        "sdc_form",
        "target_public_status",
        "transaction_value_mil",
    ]
    rows = [
        {
            "deal_id": "1",
            "announcement_date": "2022-01-01",
            "cik_match_confidence": "high",
            "sdc_form": "Merger",
            "target_public_status": "Public",
            "transaction_value_mil": "10",
        },
        {
            "deal_id": "2",
            "announcement_date": "2022-01-02",
            "cik_match_confidence": "medium",
            "sdc_form": "Tender Offer",
            "target_public_status": "Private",
            "transaction_value_mil": "",
        },
    ]
    with catalog.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    queue = create_review_queue(
        catalog,
        date(2022, 1, 1),
        date(2022, 12, 31),
        2,
    )

    assert [row["deal_id"] for row in queue] == ["2", "1"]
    assert all(row["pilot_status"] == "review" for row in queue)
