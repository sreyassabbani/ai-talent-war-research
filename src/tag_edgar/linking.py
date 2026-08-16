from __future__ import annotations

from .models import Deal, DealFiling, Filing

_FORM_SCORES = {
    "8-K": 4,
    "8-K/A": 4,
    "S-4": 5,
    "S-4/A": 5,
    "424B3": 5,
    "PREM14A": 5,
    "PREM14A/A": 5,
    "DEFM14A": 5,
    "DEFM14A/A": 5,
    "SC 14D9": 5,
    "SC 14D9/A": 5,
    "SC TO-T": 5,
    "SC TO-T/A": 5,
    "SC TO-I": 5,
    "SC TO-I/A": 5,
}


def deal_filing_links(deal: Deal, filings: list[Filing]) -> list[DealFiling]:
    """Create traceable, review-pending links; score is only a document-triage priority."""
    return [
        DealFiling(
            deal_id=deal.deal_id,
            accession_number=filing.accession_number,
            discovery_route="acquirer_confirmed_cik",
            days_from_announcement=(filing.filing_date - deal.announcement_date).days,
            days_from_effective=(filing.filing_date - deal.effective_date).days
            if deal.effective_date is not None
            else None,
            automated_relevance_score=_FORM_SCORES.get(filing.form, 1),
            manual_status="pending",
            reviewer_note=None,
        )
        for filing in filings
    ]
