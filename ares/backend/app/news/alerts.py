"""Alert system: price levels, structure/setup alerts, risk & connection
events. Alerts are stored (ring buffer), broadcast over the WebSocket hub,
and surfaced by the frontend (browser notifications where permitted)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PriceAlert:
    id: int
    symbol: str
    level: float
    condition: str              # "above" | "below"
    note: str | None = None
    triggered: bool = False


@dataclass
class AlertEvent:
    id: int
    kind: str                   # price | setup | risk | connection | execution | news
    severity: str               # info | warning | danger
    message: str
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class AlertManager:
    def __init__(self, max_events: int = 200) -> None:
        self.price_alerts: dict[int, PriceAlert] = {}
        self.events: list[AlertEvent] = []
        self.max_events = max_events
        self._alert_ids = itertools.count(1)
        self._event_ids = itertools.count(1)
        self.broadcast = None  # async callable injected by main

    def add_price_alert(self, symbol: str, level: float, condition: str, note: str | None = None) -> dict:
        alert = PriceAlert(id=next(self._alert_ids), symbol=symbol.upper(),
                           level=level, condition=condition, note=note)
        self.price_alerts[alert.id] = alert
        return alert.__dict__.copy()

    def remove_price_alert(self, alert_id: int) -> bool:
        return self.price_alerts.pop(alert_id, None) is not None

    async def emit(self, kind: str, severity: str, message: str, data: dict | None = None) -> AlertEvent:
        event = AlertEvent(id=next(self._event_ids), kind=kind, severity=severity,
                           message=message, data=data or {})
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
        if self.broadcast:
            await self.broadcast({"type": "alert", "data": event.as_dict()})
        return event

    async def check_price_alerts(self, ticks: dict[str, dict]) -> None:
        for alert in list(self.price_alerts.values()):
            if alert.triggered:
                continue
            tick = ticks.get(alert.symbol)
            if not tick:
                continue
            mid = (tick["bid"] + tick["ask"]) / 2
            hit = mid >= alert.level if alert.condition == "above" else mid <= alert.level
            if hit:
                alert.triggered = True
                await self.emit(
                    "price", "info",
                    f"{alert.symbol} crossed {alert.condition} {alert.level}"
                    + (f" — {alert.note}" if alert.note else ""),
                    {"alert_id": alert.id, "price": mid},
                )

    def list_state(self) -> dict:
        return {
            "price_alerts": [a.__dict__.copy() for a in self.price_alerts.values()],
            "events": [e.as_dict() for e in reversed(self.events[-50:])],
        }
