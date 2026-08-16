from datetime import date

from tag_edgar.linking import deal_filing_links
from tag_edgar.models import Deal, Filing


def test_deal_filing_link_is_explicit_and_review_pending() -> None:
    deal = Deal("deal-1", "0000789019", date(2024, 1, 10), date(2024, 4, 10))
    filing = Filing("0000000000-24-000001", "0000789019", "424B3", date(2024, 2, 9), None, None)

    links = deal_filing_links(deal, [filing])

    assert len(links) == 1
    assert links[0].deal_id == "deal-1"
    assert links[0].days_from_announcement == 30
    assert links[0].days_from_effective == -61
    assert links[0].automated_relevance_score == 5
    assert links[0].manual_status == "pending"
