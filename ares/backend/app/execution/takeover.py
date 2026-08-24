"""Takeover Mode — heavily permission-controlled autonomous demo execution.

State machine:

  IDLE -> REQUESTED -> AUTHORIZED -> ACTIVE -> COMPLETED / STOPPED / EXPIRED

Rules enforced here (in addition to the risk engine, which still checks every
order):
  * a request must be explicitly authorized by the user (separate API call —
    a natural-language message can request, never authorize);
  * authorizations expire if unused (TTL);
  * hard caps: max trades, max total risk, max duration;
  * the session auto-shuts down at its deadline;
  * duplicate-order protection (one order per proposed trade, ever);
  * emergency stop kills the session and closes its basket immediately.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ..config import TakeoverSettings
from ..logging_setup import get_logger
from .baskets import BasketManager
from .paper import PaperTradingEngine

log = get_logger("execution.takeover")


class TakeoverState(str, Enum):
    IDLE = "IDLE"
    REQUESTED = "REQUESTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    EXPIRED = "EXPIRED"


@dataclass
class ProposedTrade:
    symbol: str
    direction: str
    volume: float
    sl: float
    tp: float | None
    executed: bool = False


@dataclass
class TakeoverSession:
    id: str
    symbol: str
    direction: str
    reason: str
    confidence: int
    proposed_trades: list[ProposedTrade]
    max_loss: float
    max_trades: int
    duration_seconds: int
    state: TakeoverState = TakeoverState.REQUESTED
    requested_at: float = field(default_factory=time.monotonic)
    authorized_at: float | None = None
    basket_id: str | None = None
    trades_executed: int = 0
    log_lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "symbol": self.symbol, "direction": self.direction,
            "reason": self.reason, "confidence": self.confidence,
            "proposed_trades": [t.__dict__ for t in self.proposed_trades],
            "max_loss": self.max_loss, "max_trades": self.max_trades,
            "duration_seconds": self.duration_seconds,
            "state": self.state.value, "basket_id": self.basket_id,
            "trades_executed": self.trades_executed,
            "log": self.log_lines[-20:],
            "requested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


class TakeoverManager:
    def __init__(
        self,
        paper: PaperTradingEngine,
        baskets: BasketManager,
        settings: TakeoverSettings,
    ) -> None:
        self.paper = paper
        self.baskets = baskets
        self.settings = settings
        self.session: TakeoverSession | None = None
        self.history: list[dict] = []

    # -- request / authorize / stop -------------------------------------------

    def request(
        self, *, symbol: str, direction: str, reason: str, confidence: int,
        proposed_trades: list[dict], max_loss: float | None = None,
        duration_seconds: int | None = None,
    ) -> dict:
        if self.session and self.session.state in (TakeoverState.REQUESTED, TakeoverState.ACTIVE):
            return {"success": False,
                    "message": f"A takeover session is already {self.session.state.value.lower()}. Stop it first."}
        if not proposed_trades:
            return {"success": False, "message": "A takeover request must include at least one proposed trade."}

        trades = [ProposedTrade(**{k: t[k] for k in ("symbol", "direction", "volume", "sl")},
                                tp=t.get("tp")) for t in proposed_trades]
        session = TakeoverSession(
            id=f"TK-{uuid.uuid4().hex[:8]}",
            symbol=symbol, direction=direction, reason=reason, confidence=confidence,
            proposed_trades=trades[: self.settings.max_trades],
            max_loss=min(max_loss or self.settings.max_total_risk, self.settings.max_total_risk),
            max_trades=min(len(trades), self.settings.max_trades),
            duration_seconds=min(duration_seconds or self.settings.max_duration_seconds,
                                 self.settings.max_duration_seconds),
        )
        self.session = session
        session.log_lines.append("Takeover requested — awaiting explicit user authorization.")
        log.info("takeover requested: %s %s (%d proposed trades)", symbol, direction, len(trades))
        return {"success": True, "message": "Takeover requested. Explicit authorization required.",
                "session": session.as_dict()}

    def authorize(self, session_id: str) -> dict:
        session = self.session
        if session is None or session.id != session_id:
            return {"success": False, "message": "No matching takeover request to authorize."}
        if session.state != TakeoverState.REQUESTED:
            return {"success": False, "message": f"Session is {session.state.value}, not awaiting authorization."}
        if time.monotonic() - session.requested_at > self.settings.authorization_ttl_seconds:
            session.state = TakeoverState.EXPIRED
            session.log_lines.append("Authorization window expired before approval.")
            return {"success": False, "message": "Authorization window expired. Request takeover again."}

        session.state = TakeoverState.ACTIVE
        session.authorized_at = time.monotonic()
        basket = self.baskets.create(
            strategy=f"Takeover {session.id}", symbol=session.symbol,
            direction=session.direction, max_loss=session.max_loss,
        )
        session.basket_id = basket.id
        session.log_lines.append(f"Authorized by user. Basket {basket.id} created. Executing within limits.")
        log.info("takeover authorized: %s basket=%s", session.id, basket.id)
        return {"success": True, "message": "Takeover authorized.", "session": session.as_dict()}

    async def stop(self, reason: str = "user stop") -> dict:
        session = self.session
        if session is None or session.state not in (TakeoverState.REQUESTED, TakeoverState.ACTIVE):
            return {"success": False, "message": "No active takeover session to stop."}
        was_active = session.state == TakeoverState.ACTIVE
        session.state = TakeoverState.STOPPED
        session.log_lines.append(f"Stopped: {reason}")
        closed = None
        if was_active and session.basket_id:
            closed = await self.baskets.close_basket(session.basket_id)
        self._archive()
        log.info("takeover stopped: %s", reason)
        return {"success": True, "message": f"Takeover stopped ({reason}).", "closed": closed}

    def _archive(self) -> None:
        if self.session:
            self.history.append(self.session.as_dict())
            self.session = None

    # -- execution tick (driven by the app's periodic loop) --------------------

    async def tick(self) -> None:
        session = self.session
        if session is None:
            return

        if session.state == TakeoverState.REQUESTED:
            if time.monotonic() - session.requested_at > self.settings.authorization_ttl_seconds:
                session.state = TakeoverState.EXPIRED
                session.log_lines.append("Request expired without authorization.")
                self._archive()
            return

        if session.state != TakeoverState.ACTIVE:
            return

        # Deadline enforcement.
        if time.monotonic() - (session.authorized_at or 0) > session.duration_seconds:
            await self.stop(reason="execution time limit reached — automatic shutdown")
            return

        # Basket max-loss enforcement.
        if session.basket_id:
            basket = self.baskets.find(session.basket_id)
            if basket:
                view = self.baskets.basket_view(basket)
                if view["combined_pl"] <= -abs(session.max_loss):
                    await self.stop(reason="maximum loss reached — automatic shutdown")
                    return

        # Execute remaining proposed trades (each exactly once).
        for trade in session.proposed_trades:
            if trade.executed or session.trades_executed >= session.max_trades:
                continue
            trade.executed = True  # duplicate-order protection, even on failure
            result = await self.paper.submit_order(
                symbol=trade.symbol, direction=trade.direction, volume=trade.volume,
                sl=trade.sl, tp=trade.tp,
                strategy=f"Takeover {session.id}", confidence=session.confidence,
                basket_id=session.basket_id, comment=session.reason[:80],
            )
            if result.success:
                session.trades_executed += 1
                session.log_lines.append(
                    f"Executed {trade.direction} {trade.symbol} {trade.volume} lots "
                    f"(verified fill @ {result.position['entry']})."
                )
            else:
                session.log_lines.append(f"Order refused: {result.message}")

        # Complete when everything proposed has been handled and closed.
        all_done = all(t.executed for t in session.proposed_trades)
        open_in_basket = any(
            p.basket_id == session.basket_id for p in self.paper.positions.values()
        )
        if all_done and not open_in_basket and session.trades_executed >= 0:
            session.state = TakeoverState.COMPLETED
            session.log_lines.append("All takeover trades executed and closed. Session complete.")
            self._archive()

    def status(self) -> dict:
        return {
            "session": self.session.as_dict() if self.session else None,
            "history": self.history[-10:],
        }
