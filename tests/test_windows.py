from datetime import date

from tag_edgar.windows import event_window


def test_window_uses_closing_date_when_available() -> None:
    window = event_window(date(2024, 1, 10), date(2024, 4, 10))
    assert window.start == date(2023, 12, 11)
    assert window.end == date(2024, 5, 10)
    assert window.status == "closing_observed"


def test_window_marks_missing_closing_date() -> None:
    window = event_window(date(2024, 1, 10), None)
    assert window.end == date(2025, 1, 9)
    assert window.status == "closing_missing"
