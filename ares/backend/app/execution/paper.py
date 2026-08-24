"""Paper (demo) trading engine.

A complete simulated execution environment: orders are validated, filled at
the real current bid/ask from the market-data service, marked to market on
every tick, and closed manually or by SL/TP. Positions and history live in
memory and are journaled to SQLite via the journal module.

This engine NEVER touches a broker. Live execution does not exist in this
build; ExecutionSettings.live_trading_enabled is checked and refused anyway
as a belt-and-braces guard.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import ExecutionSettings
from ..logging_setup import get_logger
from ..market_data.service import MarketDataService
from ..risk.engine import RiskEngine

log = get_logger("execution.paper")

# Contract sizes for P/L conversion (units of base per 1.0 lot).
CONTRACT_SIZES = {"XAUUSD": 100, "XAGUSD": 5000, "BTCUSD": 1, "US500": 10}
DEFAULT_CONTRACT_SIZE = 100_000  # FX standard lot


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class PaperPosition:
    id: str
    symbol: str
    direction: str            # "buy" | "sell"
    volume: float             # lots
    entry: float
    sl: float | None
    tp: float | None
    opened_at: str
    strategy: str | None = None
    confidence: int | None = None
    basket_id: str | None = None
    comment: str | None = None
    floating_pl: float = 0.0
    current_price: float | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ClosedTrade:
    id: str
    symbol: str
    direction: str
    volume: float
    entry: float
    exit: float
    sl: float | None
    tp: float | None
    pl: float
    opened_at: str
    closed_at: str
    close_reason: str
    strategy: str | None = None
    confidence: int | None = None
    basket_id: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class OrderResult:
    success: bool
    message: str
    position: dict | None = None
    risk: dict | None = None

    def as_dict(self) -> dict:
        return {"success": self.success, "message": self.message,
                "position": self.position, "risk": self.risk}


class PaperTradingEngine:
    def __init__(
        self,
        market_data: MarketDataService,
        risk: RiskEngine,
        settings: ExecutionSettings,
    ) -> None:
        self.market_data = market_data
        self.risk = risk
        self.settings = settings
        self.balance = settings.paper_starting_balance
        self.currency = settings.paper_currency
        self.positions: dict[str, PaperPosition] = {}
        self.history: list[ClosedTrade] = []
        self.peak_equity = self.balance
        self._ticket = itertools.count(1)
        self.on_trade_closed = None  # async callable (journal hook)
        self.on_update = None        # async callable (ws broadcast)

    # -- helpers -----------------------------------------------------------------

    def _contract_size(self, symbol: str) -> int:
        return CONTRACT_SIZES.get(symbol, DEFAULT_CONTRACT_SIZE)

    def _pl(self, pos: PaperPosition, price: float) -> float:
        direction = 1 if pos.direction == "buy" else -1
        raw = (price - pos.entry) * direction * pos.volume * self._contract_size(pos.symbol)
        # Approximation: P/L in quote currency treated as account currency.
        # Documented limitation for the paper environment.
        if pos.symbol.endswith("JPY"):
            raw /= price or 1
        return round(raw, 2)

    @property
    def equity(self) -> float:
        return round(self.balance + sum(p.floating_pl for p in self.positions.values()), 2)

    @property
    def total_exposure_lots(self) -> float:
        return round(sum(p.volume for p in self.positions.values()), 2)

    # -- order lifecycle -----------------------------------------------------------

    async def validate_order(
        self, symbol: str, direction: str, volume: float,
        sl: float | None, tp: float | None,
    ) -> OrderResult:
        if self.settings.live_trading_enabled:
            # Hard refusal: this build has no live execution path at all.
            return OrderResult(False, "Live trading is not available in this build. ARES runs in DEMO/PAPER mode only.")
        if direction not in ("buy", "sell"):
            return OrderResult(False, f"Invalid direction '{direction}'")

        tick = await self.market_data.get_tick(symbol)
        if tick is None:
            return OrderResult(False, f"DATA SOURCE OFFLINE — no market data for {symbol}; order refused")

        price = tick["ask"] if direction == "buy" else tick["bid"]
        if sl is not None:
            if direction == "buy" and sl >= price:
                return OrderResult(False, "SL must be below entry for a buy")
            if direction == "sell" and sl <= price:
                return OrderResult(False, "SL must be above entry for a sell")
        if tp is not None:
            if direction == "buy" and tp <= price:
                return OrderResult(False, "TP must be above entry for a buy")
            if direction == "sell" and tp >= price:
                return OrderResult(False, "TP must be below entry for a sell")

        estimated_risk = None
        if sl is not None:
            estimated_risk = abs(price - sl) * volume * self._contract_size(symbol)
            if symbol.endswith("JPY"):
                estimated_risk /= price or 1

        decision = self.risk.check_order(
            volume_lots=volume,
            open_positions=len(self.positions),
            total_exposure_lots=self.total_exposure_lots,
            account_balance=self.balance,
            account_equity=self.equity,
            spread_points=tick.get("spread_points"),
            estimated_risk=estimated_risk,
        )
        if not decision.allowed:
            return OrderResult(False, "Blocked by risk engine", risk=decision.as_dict())
        return OrderResult(True, "Order valid", risk=decision.as_dict(),
                           position={"expected_entry": price, "estimated_risk": estimated_risk})

    def position_size_for_risk(self, symbol: str, entry: float, sl: float, risk_amount: float) -> float:
        """Lots such that hitting SL loses ~risk_amount (capped by config)."""
        distance = abs(entry - sl)
        if distance <= 0:
            return 0.0
        per_lot_loss = distance * self._contract_size(symbol)
        if symbol.endswith("JPY"):
            per_lot_loss /= entry or 1
        lots = risk_amount / per_lot_loss if per_lot_loss else 0.0
        return round(min(lots, self.risk.settings.max_position_size_lots), 2)

    async def submit_order(
        self, symbol: str, direction: str, volume: float,
        sl: float | None = None, tp: float | None = None,
        strategy: str | None = None, confidence: int | None = None,
        basket_id: str | None = None, comment: str | None = None,
    ) -> OrderResult:
        validation = await self.validate_order(symbol, direction, volume, sl, tp)
        if not validation.success:
            return validation

        tick = await self.market_data.get_tick(symbol)
        if tick is None:
            return OrderResult(False, "Market data lost between validation and fill; order refused")
        price = tick["ask"] if direction == "buy" else tick["bid"]

        pos = PaperPosition(
            id=f"P{next(self._ticket)}-{uuid.uuid4().hex[:6]}",
            symbol=symbol, direction=direction, volume=volume,
            entry=price, sl=sl, tp=tp, opened_at=_utcnow(),
            strategy=strategy, confidence=confidence,
            basket_id=basket_id, comment=comment,
            current_price=price,
        )
        self.positions[pos.id] = pos
        self.risk.record_trade_opened()
        log.info("paper order filled: %s %s %.2f lots @ %s (id=%s)",
                 direction, symbol, volume, price, pos.id)
        if self.on_update:
            await self.on_update()
        return OrderResult(True, "Demo order filled", position=pos.as_dict())

    async def close_position(self, position_id: str, reason: str = "manual") -> OrderResult:
        pos = self.positions.get(position_id)
        if pos is None:
            return OrderResult(False, f"No open position {position_id}")
        tick = await self.market_data.get_tick(pos.symbol)
        if tick is None:
            return OrderResult(False, "DATA SOURCE OFFLINE — cannot price the close; position stays open")
        price = tick["bid"] if pos.direction == "buy" else tick["ask"]
        return await self._close_at(pos, price, reason)

    async def _close_at(self, pos: PaperPosition, price: float, reason: str) -> OrderResult:
        pl = self._pl(pos, price)
        trade = ClosedTrade(
            id=pos.id, symbol=pos.symbol, direction=pos.direction, volume=pos.volume,
            entry=pos.entry, exit=price, sl=pos.sl, tp=pos.tp, pl=pl,
            opened_at=pos.opened_at, closed_at=_utcnow(), close_reason=reason,
            strategy=pos.strategy, confidence=pos.confidence, basket_id=pos.basket_id,
        )
        del self.positions[pos.id]
        self.balance = round(self.balance + pl, 2)
        self.history.append(trade)
        self.risk.record_trade_closed(pl)
        self.peak_equity = max(self.peak_equity, self.equity)
        log.info("paper position closed: %s pl=%.2f reason=%s", pos.id, pl, reason)
        if self.on_trade_closed:
            await self.on_trade_closed(trade)
        if self.on_update:
            await self.on_update()
        return OrderResult(True, f"Position closed ({reason})", position=trade.as_dict())

    async def emergency_close_all(self, reason: str = "emergency stop") -> list[dict]:
        results = []
        for pos_id in list(self.positions):
            result = await self.close_position(pos_id, reason=reason)
            results.append(result.as_dict())
        return results

    # -- mark to market (called from the tick loop) ---------------------------------

    async def mark_to_market(self) -> None:
        sl_tp_hits: list[tuple[PaperPosition, float, str]] = []
        for pos in self.positions.values():
            tick = self.market_data.latest_ticks.get(pos.symbol)
            if not tick:
                continue
            price = tick["bid"] if pos.direction == "buy" else tick["ask"]
            pos.current_price = price
            pos.floating_pl = self._pl(pos, price)
            if pos.direction == "buy":
                if pos.sl is not None and price <= pos.sl:
                    sl_tp_hits.append((pos, pos.sl, "stop-loss hit"))
                elif pos.tp is not None and price >= pos.tp:
                    sl_tp_hits.append((pos, pos.tp, "take-profit hit"))
            else:
                if pos.sl is not None and price >= pos.sl:
                    sl_tp_hits.append((pos, pos.sl, "stop-loss hit"))
                elif pos.tp is not None and price <= pos.tp:
                    sl_tp_hits.append((pos, pos.tp, "take-profit hit"))
        for pos, level, reason in sl_tp_hits:
            if pos.id in self.positions:
                await self._close_at(pos, level, reason)
        self.peak_equity = max(self.peak_equity, self.equity)

    # -- reporting ---------------------------------------------------------------------

    def account_snapshot(self) -> dict:
        today = datetime.now(timezone.utc).date().isoformat()
        daily = sum(t.pl for t in self.history if t.closed_at.startswith(today))
        wins = [t for t in self.history if t.pl > 0]
        losses = [t for t in self.history if t.pl < 0]
        gross_win = sum(t.pl for t in wins)
        gross_loss = abs(sum(t.pl for t in losses))
        rs = []
        for t in self.history:
            if t.sl is not None and abs(t.entry - t.sl) > 0:
                risk_per_unit = abs(t.entry - t.sl)
                rs.append((t.exit - t.entry) / risk_per_unit * (1 if t.direction == "buy" else -1))
        return {
            "mode": "PAPER",
            "currency": self.currency,
            "balance": self.balance,
            "equity": self.equity,
            "floating_pl": round(self.equity - self.balance, 2),
            "daily_pl": round(daily, 2),
            "drawdown_percent": round(
                (self.peak_equity - self.equity) / self.peak_equity * 100, 2
            ) if self.peak_equity else 0.0,
            "open_positions": len(self.positions),
            "trades_closed": len(self.history),
            "win_rate": round(len(wins) / len(self.history) * 100, 1) if self.history else None,
            "average_r": round(sum(rs) / len(rs), 2) if rs else None,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
            "exposure_lots": self.total_exposure_lots,
        }
