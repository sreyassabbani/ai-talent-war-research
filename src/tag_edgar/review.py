from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .models import Deal


def approved_deals(review_csv: Path) -> list[Deal]:
    """Load only human-approved pilot cases for SEC retrieval.

    A row must record all three decisions explicitly. This avoids treating a fuzzy CIK match or a
    classifier's technology label as authorization to query EDGAR at scale.
    """
    required = {
        "deal_id",
        "candidate_cik",
        "announcement_date",
        "effective_date",
        "target_name",
        "cik_manual_status",
        "technology_scope_status",
        "pilot_status",
    }
    approved: list[Deal] = []
    with review_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Review CSV needs deal, CIK, date, target, and three human-decision columns. "
                "Regenerate it with make-pilot-queue."
            )
        for row in reader:
            if not (
                row["cik_manual_status"].strip().lower() == "confirmed"
                and row["technology_scope_status"].strip().lower() == "in_scope"
                and row["pilot_status"].strip().lower() == "selected"
            ):
                continue
            effective = row["effective_date"].strip()
            target_cik: str | None = None
            target_status = row.get("target_cik_manual_status", "").strip().lower()
            target_candidate = row.get("target_candidate_cik", "").strip()
            if target_status == "confirmed":
                if not target_candidate:
                    raise ValueError(
                        f"Deal {row['deal_id']} confirms a target CIK but has no target_candidate_cik."
                    )
                target_cik = target_candidate
            approved.append(
                Deal(
                    deal_id=row["deal_id"].strip(),
                    acquirer_cik=row["candidate_cik"].strip(),
                    announcement_date=date.fromisoformat(row["announcement_date"]),
                    effective_date=date.fromisoformat(effective) if effective else None,
                    target_name=row["target_name"].strip() or None,
                    target_cik=target_cik,
                )
            )
    return approved
