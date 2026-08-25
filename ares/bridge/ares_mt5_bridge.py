#!/usr/bin/env python3
"""ARES MT5 Bridge — Windows side.

Runs on a Windows machine (PC, VM or VPS) that has the MetaTrader 5 terminal
installed. It connects OUT to your ARES backend over an authenticated
WebSocket and answers RPC requests using the official MetaTrader5 package.

Why this exists: the `MetaTrader5` Python package wraps the Windows terminal's
IPC. There is no Linux build and no way to install one, so a cloud/Linux ARES
backend can never talk to MT5 directly. This bridge is the supported path.

Install (on the Windows machine):

    py -m pip install MetaTrader5 websockets python-dotenv

Configure a .env next to this file (never commit it):

    ARES_BACKEND_URL=wss://your-ares-host/bridge/ws
    ARES_BRIDGE_TOKEN=<same value as the backend's ARES_BRIDGE_TOKEN>
    MT5_LOGIN=12345678
    MT5_PASSWORD=your-demo-password
    MT5_SERVER=Your-Broker-Demo
    MT5_PATH=C:\\Program Files\\MetaTrader 5\\terminal64.exe   # optional

Run:

    py ares_mt5_bridge.py

The bridge never sends your password anywhere: it is used only for the local
terminal login call. Only non-sensitive account facts (masked login, broker,
server, balance, equity, permissions) are reported to ARES.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import socket
import sys
from datetime import datetime, timezone

BRIDGE_VERSION = "1.0.0"

try:
    import websockets
except ImportError:  # pragma: no cover - guidance for the operator
    sys.exit("Missing dependency: py -m pip install websockets")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional; env vars still work
    pass

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - Windows-only package
    mt5 = None

TIMEFRAMES = {}
if mt5 is not None:
    TIMEFRAMES = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
    }


class TerminalSession:
    """Owns the local MT5 terminal connection and reports its honest state."""

    def __init__(self) -> None:
        self.login = os.getenv("MT5_LOGIN")
        self.password = os.getenv("MT5_PASSWORD")
        self.server = os.getenv("MT5_SERVER")
        self.path = os.getenv("MT5_PATH") or None
        self.state = "CONNECTING"
        self.detail = ""
        self.initialized = False

    def connect(self) -> bool:
        if mt5 is None:
            self.state = "ERROR"
            self.detail = ("MetaTrader5 package not installed. Run this bridge on Windows "
                           "with: py -m pip install MetaTrader5")
            return False
        if not (self.login and self.password and self.server):
            self.state = "AUTH_REQUIRED"
            self.detail = "MT5_LOGIN / MT5_PASSWORD / MT5_SERVER are not all set in .env"
            return False

        kwargs = {"login": int(self.login), "password": self.password, "server": self.server}
        if self.path:
            kwargs["path"] = self.path

        if not mt5.initialize(**kwargs):
            code, message = mt5.last_error()
            self.initialized = False
            if code in (-10005, -10003):
                self.state = "MT5_TERMINAL_NOT_RUNNING" if code == -10003 else "ERROR"
            else:
                self.state = "ERROR"
            self.detail = f"initialize failed ({code}): {message}"
            return False

        self.initialized = True
        info = mt5.account_info()
        if info is None:
            self.state = "AUTH_REQUIRED"
            self.detail = "terminal initialized but account_info() is empty (login rejected?)"
            return False

        # Verify real market data flows before claiming CONNECTED.
        probe = None
        for symbol in ("EURUSD", "XAUUSD", "USDJPY"):
            if mt5.symbol_select(symbol, True):
                probe = mt5.symbol_info_tick(symbol)
                if probe is not None:
                    break
        if probe is None:
            self.state = "BROKER_DISCONNECTED"
            self.detail = "authenticated but no tick could be retrieved from the broker"
            return False

        self.state = "CONNECTED"
        self.detail = ""
        return True

    def ensure(self) -> bool:
        if self.state == "CONNECTED" and mt5 is not None:
            info = mt5.account_info()
            if info is not None:
                return True
            self.state = "BROKER_DISCONNECTED"
            self.detail = "account_info() stopped responding"
            try:
                mt5.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self.initialized = False
        return self.connect()

    def account_payload(self) -> dict | None:
        if mt5 is None or self.state != "CONNECTED":
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login,          # masked on the ARES side
            "broker": info.company,
            "server": info.server,
            "currency": info.currency,
            "balance": float(info.balance),
            "equity": float(info.equity),
            "margin_free": float(info.margin_free),
            "leverage": int(info.leverage),
            "trade_allowed": bool(info.trade_allowed),
            "is_demo": getattr(info, "trade_mode", None) == mt5.ACCOUNT_TRADE_MODE_DEMO,
        }

    # -- RPC handlers --------------------------------------------------------

    def symbols(self) -> list[dict]:
        if not self.ensure():
            return []
        out = []
        for s in mt5.symbols_get() or []:
            out.append({"name": s.name, "description": s.description,
                        "digits": s.digits, "point": s.point, "trade_mode": s.trade_mode})
        return out

    def tick(self, symbol: str) -> dict | None:
        if not self.ensure():
            return None
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            return None
        return {
            "symbol": symbol,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "spread_points": round((tick.ask - tick.bid) / info.point, 1) if info.point else None,
            "time": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
        }

    def candles(self, symbol: str, timeframe: str, count: int) -> list[dict]:
        if not self.ensure() or timeframe not in TIMEFRAMES:
            return []
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAMES[timeframe], 0, int(count))
        if rates is None:
            return []
        return [
            {"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["tick_volume"])}
            for r in rates
        ]

    def positions(self) -> list[dict]:
        if not self.ensure():
            return []
        return [
            {"ticket": p.ticket, "symbol": p.symbol,
             "direction": "buy" if p.type == mt5.POSITION_TYPE_BUY else "sell",
             "volume": float(p.volume), "entry": float(p.price_open),
             "current_price": float(p.price_current), "sl": float(p.sl) or None,
             "tp": float(p.tp) or None, "profit": float(p.profit),
             "opened_at": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat()}
            for p in (mt5.positions_get() or [])
        ]


HANDLERS = {
    "symbols": lambda session, params: session.symbols(),
    "tick": lambda session, params: session.tick(params["symbol"]),
    "candles": lambda session, params: session.candles(
        params["symbol"], params.get("timeframe", "M15"), params.get("count", 300)),
    "positions": lambda session, params: session.positions(),
    "ping": lambda session, params: {"pong": True, "state": session.state},
}


async def heartbeat_loop(ws, session: TerminalSession, interval: float) -> None:
    while True:
        session.ensure()
        account = session.account_payload()
        await ws.send(json.dumps({
            "type": "heartbeat",
            "terminal_connected": session.state == "CONNECTED",
            "mt5_state": session.state,
            "detail": session.detail,
            "broker": account["broker"] if account else None,
            "server": account["server"] if account else None,
            "account": account,
        }))
        await asyncio.sleep(interval)


async def serve_requests(ws, session: TerminalSession) -> None:
    async for raw in ws:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if message.get("type") != "request":
            continue
        handler = HANDLERS.get(message.get("method", ""))
        response = {"type": "response", "id": message.get("id")}
        if handler is None:
            response["error"] = f"unknown method {message.get('method')}"
        else:
            try:
                # MT5 calls are blocking; keep the event loop responsive.
                response["result"] = await asyncio.to_thread(
                    handler, session, message.get("params", {}))
            except Exception as exc:  # noqa: BLE001
                response["error"] = f"{type(exc).__name__}: {exc}"
        await ws.send(json.dumps(response))


async def run_once(url: str, token: str, session: TerminalSession) -> None:
    async with websockets.connect(url, max_size=8 * 1024 * 1024) as ws:
        session.ensure()
        await ws.send(json.dumps({
            "type": "hello",
            "token": token,
            "bridge_version": BRIDGE_VERSION,
            "host": f"{socket.gethostname()} ({platform.system()} {platform.release()})",
            # ARES uses these to tell a real Windows bridge apart from a
            # protocol test client. Report them honestly.
            "platform": platform.system(),
            "mt5_package": mt5 is not None,
            "terminal_path": session.path,
            "terminal_connected": session.state == "CONNECTED",
            "mt5_state": session.state,
            "detail": session.detail,
        }))
        ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if ack.get("type") != "hello_ack":
            raise RuntimeError(f"backend rejected handshake: {ack}")
        interval = float(ack.get("heartbeat", 15))
        print(f"[ares-bridge] attached to {url} | MT5 state: {session.state} {session.detail}")

        heartbeat = asyncio.create_task(heartbeat_loop(ws, session, interval))
        try:
            await serve_requests(ws, session)
        finally:
            heartbeat.cancel()


async def main() -> None:
    url = os.getenv("ARES_BACKEND_URL", "ws://127.0.0.1:8000/bridge/ws")
    token = os.getenv("ARES_BRIDGE_TOKEN", "")
    if not token:
        sys.exit("ARES_BRIDGE_TOKEN is not set. It must match the backend's token.")

    session = TerminalSession()
    if mt5 is None:
        print("[ares-bridge] WARNING: MetaTrader5 package unavailable on this host. "
              "The bridge will attach and report its real state, but cannot serve data.")

    backoff = 2.0
    while True:
        try:
            await run_once(url, token, session)
            backoff = 2.0
        except Exception as exc:  # noqa: BLE001 - keep the bridge alive
            print(f"[ares-bridge] connection lost ({type(exc).__name__}: {exc}); "
                  f"retrying in {backoff:.0f}s")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[ares-bridge] stopped")
