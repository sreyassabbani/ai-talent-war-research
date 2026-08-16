import csv
from pathlib import Path

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
