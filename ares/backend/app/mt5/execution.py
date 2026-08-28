"""Real MetaTrader 5 order execution — DEMO accounts only.

This is the one place in ARES that sends an order to a broker. Every guard is
deliberate:

  * The account must report itself as a DEMO account. A live account is refused
    outright, with no override flag, because this build has no live-money path.
  * A pre-trade check runs first and returns READY or BLOCKED with the exact
    reason — spread, stop distance, volume step, margin, risk limits, news.
  * An order is only reported as executed when MT5 returns a success retcode
    AND a ticket. `order_send` returning None, or any other retcode, is a
    failure and is reported verbatim with the broker's own comment.
  * Positions and closes are read back from the terminal, never assumed.

Nothing here fabricates a fill, a ticket, or a position.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..logging_setup import get_logger

log = get_logger("mt5.execution")

# MT5 retcodes that mean the order actually went through.
SUCCESS_RETCODES = {10009, 10008}  # TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str


@dataclass
class PreTradeResult:
    ready: bool
    items: list[CheckItem] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    plan: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "verdict": "READY" if self.ready else "BLOCKED",
            "items": [item.__dict__ for item in self.items],
            "blocked_by": self.blocked_by,
            "plan": self.plan,
        }


@dataclass
class ExecutionResult:
    success: bool
    message: str
    retcode: int | None = None
    ticket: int | None = None
    broker_comment: str | None = None
    position: dict | None = None
    check: dict | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class MT5Executor:
    """Sends orders to the terminal the adapter owns. Requires that adapter to
    be genuinely connected to a verified demo account."""

    def __init__(self, adapter, risk) -> None:
        self.adapter = adapter
        self.risk = risk
        self.last_check: PreTradeResult | None = None

    # -- guards ---------------------------------------------------------------

    def _unavailable(self) -> str | None:
        """Why execution cannot happen right now, or None if it can."""
        if not getattr(self.adapter, "connected", False):
            return ("MT5 is not connected. " +
                    (self.adapter.last_error or "No terminal is attached."))
        if getattr(self.adapter, "_mt5", None) is None:
            # Order placement currently requires ARES to run on the same
            # Windows machine as the terminal (the direct adapter). Routing
            # orders over the bridge is not implemented, and pretending
            # otherwise would risk a silent no-op.
            return ("Order placement requires ARES to run on the same Windows machine "
                    "as MetaTrader 5. This backend reaches MT5 through the bridge, "
                    "which does not carry orders yet.")
        account = self.adapter.account
        if account is None:
            return "MT5 is connected but no account information was received."
        if not account.is_demo:
            return ("The connected MT5 account is NOT a demo account. ARES refuses "
                    "to place orders on it: this build has no live-money path.")
        if not account.trade_allowed:
            return "The broker reports trading is not allowed on this account."
        return None

    # -- pre-trade check --------------------------------------------------------

    async def pre_trade_check(
        self, symbol: str, direction: str, volume: float,
        sl: float | None, tp: float | None, news_warning: dict | None = None,
    ) -> PreTradeResult:
        """Verify everything before an order is allowed. Reads live symbol and
        account facts from the terminal — no assumptions."""
        items: list[CheckItem] = []
        blocked: list[str] = []

        def check(name: str, ok: bool, detail: str) -> None:
            items.append(CheckItem(name, ok, detail))
            if not ok:
                blocked.append(f"{name}: {detail}")

        unavailable = self._unavailable()
        check("MT5 connection", unavailable is None,
              unavailable or f"connected to {self.adapter.account.broker} (DEMO)")
        if unavailable:
            result = PreTradeResult(False, items, blocked)
            self.last_check = result
            return result

        check("Direction", direction in ("buy", "sell"),
              direction if direction in ("buy", "sell") else f"invalid: {direction!r}")

        info = await asyncio.to_thread(self._symbol_info_sync, symbol)
        if info is None:
            check("Symbol", False, f"{symbol} is not available from this broker")
            result = PreTradeResult(False, items, blocked)
            self.last_check = result
            return result
        check("Symbol", True, f"{symbol} · digits {info['digits']} · "
                              f"volume {info['volume_min']}–{info['volume_max']} "
                              f"step {info['volume_step']}")

        # Volume must respect the broker's own min/max/step.
        step = info["volume_step"] or 0.01
        steps = round(volume / step)
        normalised = round(steps * step, 8)
        volume_ok = (info["volume_min"] <= normalised <= info["volume_max"]
                     and abs(normalised - volume) < step / 2)
        check("Volume", volume_ok,
              f"{volume} lots" if volume_ok else
              f"{volume} is outside {info['volume_min']}–{info['volume_max']} "
              f"or not a multiple of {step} (nearest valid: {normalised})")

        tick = await self.adapter.get_tick(symbol)
        if tick is None:
            check("Live quote", False, "no tick available; refusing to price the order")
            result = PreTradeResult(False, items, blocked)
            self.last_check = result
            return result
        entry = tick["ask"] if direction == "buy" else tick["bid"]
        check("Live quote", True, f"bid {tick['bid']} / ask {tick['ask']}")

        spread_points = tick.get("spread_points")
        spread_ok = spread_points is None or spread_points <= self.risk.settings.max_spread_points
        check("Spread", spread_ok,
              f"{spread_points} points (limit {self.risk.settings.max_spread_points})")

        # Stops must respect the broker's minimum distance.
        min_distance = info["stops_level"] * info["point"]
        if sl is not None:
            distance = abs(entry - sl)
            side_ok = (sl < entry) if direction == "buy" else (sl > entry)
            far_enough = distance >= min_distance
            check("Stop loss", side_ok and far_enough,
                  f"{sl} ({distance / (info['point'] or 1):.0f} points)"
                  if side_ok and far_enough else
                  ("on the wrong side of entry" if not side_ok else
                   f"too close: broker requires at least {info['stops_level']} points"))
        else:
            check("Stop loss", True, "none set (allowed, but risk is uncapped)")

        if tp is not None:
            distance = abs(tp - entry)
            side_ok = (tp > entry) if direction == "buy" else (tp < entry)
            check("Take profit", side_ok and distance >= min_distance,
                  f"{tp}" if side_ok else "on the wrong side of entry")

        # Risk/reward, when both levels are present.
        rr = None
        if sl is not None and tp is not None and abs(entry - sl) > 0:
            rr = abs(tp - entry) / abs(entry - sl)
            check("Risk/reward", True, f"1 : {rr:.2f}")

        # Margin, asked of the broker rather than estimated.
        margin = await asyncio.to_thread(
            self._margin_sync, symbol, direction, normalised, entry)
        account = self.adapter.account
        if margin is None:
            check("Margin", False, "the broker could not calculate margin for this order")
        else:
            affordable = margin <= account.margin_free
            check("Margin", affordable,
                  f"{margin:.2f} {account.currency} required, "
                  f"{account.margin_free:.2f} free")

        # ARES's own risk limits still apply to real orders.
        positions = await self.adapter.get_positions()
        exposure = sum(p.get("volume", 0.0) for p in positions)
        estimated_risk = None
        if sl is not None and margin is not None:
            estimated_risk = abs(entry - sl) / (info["point"] or 1) * \
                info["trade_tick_value"] * (normalised / (info["volume_min"] or 0.01)) \
                * (info["volume_min"] or 0.01) / (info["trade_tick_size"] or info["point"] or 1) \
                if info["trade_tick_value"] else None
        decision = self.risk.check_order(
            volume_lots=normalised,
            open_positions=len(positions),
            total_exposure_lots=exposure,
            account_balance=account.balance,
            account_equity=account.equity,
            spread_points=spread_points,
        )
        check("ARES risk limits", decision.allowed,
              "within all limits" if decision.allowed else "; ".join(decision.reasons))

        if news_warning:
            check("News risk", False, news_warning["warning"])
        else:
            check("News risk", True, "no high-impact event inside the warning window")

        result = PreTradeResult(
            ready=not blocked, items=items, blocked_by=blocked,
            plan={
                "symbol": symbol, "direction": direction,
                "volume": normalised, "entry": entry, "sl": sl, "tp": tp,
                "risk_reward": round(rr, 2) if rr else None,
                "margin_required": margin,
                "account_mode": "DEMO",
                "broker": account.broker, "server": account.server,
            },
        )
        self.last_check = result
        return result

    def _symbol_info_sync(self, symbol: str) -> dict | None:
        mt5 = self.adapter._mt5
        if mt5 is None:
            return None
        with self.adapter._lock:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            return {
                "digits": info.digits, "point": info.point,
                "volume_min": info.volume_min, "volume_max": info.volume_max,
                "volume_step": info.volume_step, "stops_level": info.trade_stops_level,
                "filling_mode": info.filling_mode,
                "trade_tick_value": getattr(info, "trade_tick_value", 0.0),
                "trade_tick_size": getattr(info, "trade_tick_size", info.point),
            }

    def _margin_sync(self, symbol: str, direction: str, volume: float, price: float):
        mt5 = self.adapter._mt5
        if mt5 is None:
            return None
        order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL
        with self.adapter._lock:
            return mt5.order_calc_margin(order_type, symbol, volume, price)

    # -- execution -----------------------------------------------------------------

    async def place_order(
        self, symbol: str, direction: str, volume: float,
        sl: float | None = None, tp: float | None = None,
        comment: str = "ARES", news_warning: dict | None = None,
        skip_check: bool = False,
    ) -> ExecutionResult:
        """Send a market order. Reports success only on a success retcode with
        a ticket."""
        check = None
        if not skip_check:
            check = await self.pre_trade_check(symbol, direction, volume, sl, tp, news_warning)
            if not check.ready:
                return ExecutionResult(
                    False, "Blocked by pre-trade check: " + "; ".join(check.blocked_by),
                    check=check.as_dict())
            volume = check.plan["volume"]

        unavailable = self._unavailable()
        if unavailable:
            return ExecutionResult(False, unavailable,
                                   check=check.as_dict() if check else None)

        try:
            raw = await asyncio.to_thread(
                self._order_send_sync, symbol, direction, volume, sl, tp, comment)
        except Exception as exc:  # noqa: BLE001
            log.error("order_send raised: %s", exc)
            return ExecutionResult(False, f"MT5 order_send raised {type(exc).__name__}: {exc}",
                                   check=check.as_dict() if check else None)

        if raw is None:
            return ExecutionResult(
                False,
                "MT5 returned no result for order_send. The order was NOT placed. "
                f"Terminal last_error: {raw}",
                check=check.as_dict() if check else None)

        retcode = int(raw["retcode"])
        if retcode not in SUCCESS_RETCODES or not raw.get("order"):
            return ExecutionResult(
                False,
                f"MT5 rejected the order (retcode {retcode}): {raw.get('comment') or 'no comment'}",
                retcode=retcode, broker_comment=raw.get("comment"),
                check=check.as_dict() if check else None)

        ticket = int(raw["order"])
        self.risk.record_trade_opened()
        log.info("MT5 order executed: %s %s %.2f ticket=%s retcode=%s",
                 direction, symbol, volume, ticket, retcode)

        # Read the position back from the terminal rather than assuming it.
        position = await self._find_position(ticket, symbol)
        return ExecutionResult(
            True,
            f"Order executed on {self.adapter.account.broker} (DEMO). Ticket {ticket}.",
            retcode=retcode, ticket=ticket, broker_comment=raw.get("comment"),
            position=position, check=check.as_dict() if check else None)

    def _order_send_sync(self, symbol: str, direction: str, volume: float,
                         sl: float | None, tp: float | None, comment: str) -> dict | None:
        mt5 = self.adapter._mt5
        with self.adapter._lock:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            tick = mt5.symbol_info_tick(symbol)
            if info is None or tick is None:
                return None

            price = tick.ask if direction == "buy" else tick.bid
            order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL

            # Filling mode must match what the symbol actually permits; the
            # wrong one is a common "Unsupported filling mode" rejection.
            filling = mt5.ORDER_FILLING_IOC
            mode = info.filling_mode
            if mode & 1:        # SYMBOL_FILLING_FOK
                filling = mt5.ORDER_FILLING_FOK
            elif mode & 2:      # SYMBOL_FILLING_IOC
                filling = mt5.ORDER_FILLING_IOC
            else:
                filling = mt5.ORDER_FILLING_RETURN

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(volume),
                "type": order_type,
                "price": price,
                "deviation": 20,
                "magic": 20260825,
                "comment": comment[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }
            if sl is not None:
                request["sl"] = round(float(sl), info.digits)
            if tp is not None:
                request["tp"] = round(float(tp), info.digits)

            result = mt5.order_send(request)
            if result is None:
                code, message = mt5.last_error()
                log.error("order_send returned None (%s): %s", code, message)
                return None
            return {
                "retcode": result.retcode, "order": result.order, "deal": result.deal,
                "volume": result.volume, "price": result.price,
                "comment": result.comment, "request_id": result.request_id,
            }

    async def _find_position(self, ticket: int, symbol: str) -> dict | None:
        for _ in range(4):
            positions = await self.adapter.get_positions()
            for position in positions:
                if position.get("ticket") == ticket:
                    return position
            await asyncio.sleep(0.3)
        # The order succeeded but no position is visible: report that honestly
        # rather than inventing one (it may have filled and closed instantly).
        log.info("order %s executed but no open position found for %s", ticket, symbol)
        return None

    async def close_position(self, ticket: int) -> ExecutionResult:
        """Close an open MT5 position by ticket, verified against the terminal."""
        unavailable = self._unavailable()
        if unavailable:
            return ExecutionResult(False, unavailable)

        positions = await self.adapter.get_positions()
        target = next((p for p in positions if p.get("ticket") == ticket), None)
        if target is None:
            return ExecutionResult(False, f"No open MT5 position with ticket {ticket}.")

        try:
            raw = await asyncio.to_thread(self._close_sync, target)
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(False, f"MT5 close raised {type(exc).__name__}: {exc}")

        if raw is None:
            return ExecutionResult(False, "MT5 returned no result for the close request.")
        retcode = int(raw["retcode"])
        if retcode not in SUCCESS_RETCODES:
            return ExecutionResult(
                False, f"MT5 rejected the close (retcode {retcode}): {raw.get('comment')}",
                retcode=retcode, broker_comment=raw.get("comment"))

        self.risk.record_trade_closed(float(target.get("profit", 0.0)))
        return ExecutionResult(
            True, f"Position {ticket} closed on the broker.",
            retcode=retcode, ticket=ticket, broker_comment=raw.get("comment"))

    def _close_sync(self, position: dict) -> dict | None:
        mt5 = self.adapter._mt5
        symbol = position["symbol"]
        with self.adapter._lock:
            info = mt5.symbol_info(symbol)
            tick = mt5.symbol_info_tick(symbol)
            if info is None or tick is None:
                return None
            closing_buy = position["direction"] == "sell"
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(position["volume"]),
                "type": mt5.ORDER_TYPE_BUY if closing_buy else mt5.ORDER_TYPE_SELL,
                "position": int(position["ticket"]),
                "price": tick.ask if closing_buy else tick.bid,
                "deviation": 20,
                "magic": 20260825,
                "comment": "ARES close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": (mt5.ORDER_FILLING_FOK if info.filling_mode & 1
                                 else mt5.ORDER_FILLING_IOC),
            }
            result = mt5.order_send(request)
            if result is None:
                return None
            return {"retcode": result.retcode, "comment": result.comment}

    # -- outcome tracking ------------------------------------------------------------

    async def closed_deals(self, hours: float = 72) -> list[dict]:
        """Closed deals straight from MT5 history, for outcome tracking."""
        if not getattr(self.adapter, "connected", False):
            return []
        try:
            return await asyncio.to_thread(self._history_sync, hours)
        except Exception as exc:  # noqa: BLE001
            log.warning("history fetch failed: %s", exc)
            return []

    def _history_sync(self, hours: float) -> list[dict]:
        from datetime import timedelta

        mt5 = self.adapter._mt5
        if mt5 is None:
            return []
        now = datetime.now(timezone.utc)
        with self.adapter._lock:
            deals = mt5.history_deals_get(now - timedelta(hours=hours), now)
        if deals is None:
            return []
        out = []
        for deal in deals:
            # entry==1 (DEAL_ENTRY_OUT) is a closing deal, which carries the P/L.
            if getattr(deal, "entry", None) != 1:
                continue
            out.append({
                "ticket": deal.ticket,
                "position_ticket": deal.position_id,
                "symbol": deal.symbol,
                "volume": float(deal.volume),
                "price": float(deal.price),
                "profit": float(deal.profit),
                "commission": float(deal.commission),
                "swap": float(deal.swap),
                "closed_at": datetime.fromtimestamp(deal.time, tz=timezone.utc).isoformat(),
                "comment": deal.comment,
            })
        return out
