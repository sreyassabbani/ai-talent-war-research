import csv
from pathlib import Path

import pytest

from tag_edgar.review import approved_deals


def test_approved_deals_requires_each_human_decision(tmp_path: Path) -> None:
    source = tmp_path / "review.csv"
    fields = [
        "deal_id",
        "candidate_cik",
        "announcement_date",
        "effective_date",
        "target_name",
        "cik_manual_status",
        "target_candidate_cik",
        "target_cik_manual_status",
        "technology_scope_status",
        "pilot_status",
    ]
    rows = [
        {
            "deal_id": "approved",
            "candidate_cik": "789019",
            "announcement_date": "2022-01-01",
            "effective_date": "",
            "target_name": "Target",
            "cik_manual_status": "confirmed",
            "target_candidate_cik": "1002517",
            "target_cik_manual_status": "confirmed",
            "technology_scope_status": "in_scope",
            "pilot_status": "selected",
        },
        {
            "deal_id": "not-approved",
            "candidate_cik": "1",
            "announcement_date": "2022-01-02",
            "effective_date": "",
            "target_name": "Other",
            "cik_manual_status": "pending",
            "target_candidate_cik": "",
            "target_cik_manual_status": "pending",
            "technology_scope_status": "in_scope",
            "pilot_status": "selected",
        },
    ]
    with source.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    deals = approved_deals(source)

    assert [deal.deal_id for deal in deals] == ["approved"]
    assert deals[0].effective_date is None
    assert deals[0].target_cik == "1002517"


def test_approved_deals_rejects_confirmed_target_without_cik(tmp_path: Path) -> None:
    source = tmp_path / "review.csv"
    source.write_text(
        "deal_id,candidate_cik,announcement_date,effective_date,target_name,cik_manual_status,"
        "target_candidate_cik,target_cik_manual_status,technology_scope_status,pilot_status\n"
        "bad,789019,2022-01-01,,Target,confirmed,,confirmed,in_scope,selected\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no target_candidate_cik"):
        approved_deals(source)
