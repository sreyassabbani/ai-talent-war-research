from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class EventWindow:
    start: date
    end: date
    status: str


def event_window(announcement: date, effective: date | None) -> EventWindow:
    start = announcement - timedelta(days=30)
    if effective is not None:
        if effective < announcement:
            return EventWindow(
                start=start, end=announcement + timedelta(days=365), status="invalid_effective_date"
            )
        return EventWindow(
            start=start, end=effective + timedelta(days=30), status="closing_observed"
        )
    return EventWindow(
        start=start, end=announcement + timedelta(days=365), status="closing_missing"
    )
