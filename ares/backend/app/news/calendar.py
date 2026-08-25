"""Economic calendar + web intelligence gating.

There is no free, reliable, license-clean live calendar API bundled here, so
the calendar starts EMPTY and is populated either by the user (POST
/api/calendar/events) or by a future licensed feed integration. ARES never
fabricates news or events: an empty calendar is reported as exactly that.

Web intelligence is OFFLINE unless a provider is wired in; requests then get
the truthful "Web intelligence is currently unavailable."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..config import NewsSettings
from ..status import ComponentState, status_registry


@dataclass
class EconomicEvent:
    id: int
    title: str
    currency: str
    impact: str                 # low | medium | high
    scheduled_at: str           # ISO UTC
    previous: str | None = None
    forecast: str | None = None
    actual: str | None = None
    source: str = "user"

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def parse_when(value: str) -> datetime | None:
    """Parse an ISO timestamp defensively. Naive values are treated as UTC so
    aware/naive comparisons can never raise; unparseable values return None."""
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


class EconomicCalendar:
    def __init__(self, settings: NewsSettings) -> None:
        self.settings = settings
        self.events: list[EconomicEvent] = []
        self._next_id = 1
        status_registry.set(
            "web_intelligence", ComponentState.OFFLINE,
            "Web intelligence is currently unavailable (no research provider configured).",
        )

    def add_event(self, *, title: str, currency: str, impact: str, scheduled_at: str,
                  previous: str | None = None, forecast: str | None = None,
                  actual: str | None = None, source: str = "user") -> EconomicEvent:
        when = parse_when(scheduled_at)
        if when is None:
            raise ValueError(f"scheduled_at is not a valid ISO timestamp: {scheduled_at!r}")
        event = EconomicEvent(
            id=self._next_id, title=title, currency=currency.upper(),
            impact=impact.lower(), scheduled_at=when.isoformat(),
            previous=previous, forecast=forecast, actual=actual, source=source,
        )
        self._next_id += 1
        self.events.append(event)
        self.events.sort(key=lambda e: e.scheduled_at)
        return event

    def upcoming(self, hours: float = 48) -> list[dict]:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=hours)
        out = []
        for e in self.events:
            when = parse_when(e.scheduled_at)
            if when and now - timedelta(hours=2) <= when <= horizon:
                out.append(e.as_dict())
        return out

    def news_risk_for(self, symbol: str, now: datetime | None = None) -> dict | None:
        """High-impact event within the warning window touching one of the
        symbol's currencies → returns a warning payload, else None."""
        now = now or datetime.now(timezone.utc)
        window = timedelta(minutes=self.settings.calendar_warning_window_minutes)
        currencies = {symbol[:3].upper(), symbol[3:6].upper()} if len(symbol) >= 6 else {symbol.upper()}
        if symbol.upper().startswith("XAU") or symbol.upper().startswith("XAG"):
            currencies.add("USD")
        for e in self.events:
            if e.impact != "high" or e.currency not in currencies:
                continue
            when = parse_when(e.scheduled_at)
            if when is None:
                continue
            delta = when - now
            if timedelta(0) <= delta <= window:
                minutes = int(delta.total_seconds() // 60)
                return {
                    "event": e.as_dict(),
                    "minutes_until": minutes,
                    "warning": f"High-impact {e.currency} event in {minutes} minutes. Execution risk elevated.",
                }
        return None
