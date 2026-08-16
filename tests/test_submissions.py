from datetime import date

from tag_edgar.models import Filing
from tag_edgar.submissions import _records, normalized_cik, relevant_filings, submissions_url


def test_cik_is_normalized_to_ten_digits() -> None:
    assert normalized_cik("789019") == "0000789019"
    assert submissions_url("789019").endswith("CIK0000789019.json")


def test_filter_keeps_exact_forms_and_window() -> None:
    filings = [
        Filing("a", "0000000001", "8-K", date(2024, 1, 10), None, None),
        Filing("b", "0000000001", "10-K", date(2024, 1, 12), None, None),
        Filing("c", "0000000001", "424B3", date(2024, 2, 1), None, None),
    ]
    found = relevant_filings(
        filings, frozenset({"8-K", "424B3"}), date(2024, 1, 1), date(2024, 1, 31)
    )
    assert [filing.accession_number for filing in found] == ["a"]


def test_historical_submission_file_uses_top_level_arrays() -> None:
    payload: dict[str, object] = {
        "accessionNumber": ["0000000001-24-000001"],
        "filingDate": ["2024-01-10"],
        "reportDate": [""],
        "form": ["8-K"],
        "primaryDocument": ["form8k.htm"],
        "items": ["1.01,2.01,9.01"],
    }
    filings = _records(payload, "1")
    assert len(filings) == 1
    assert filings[0].items == "1.01,2.01,9.01"
