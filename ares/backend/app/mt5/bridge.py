"""ARES MT5 Bridge — server side.

Root cause this solves: the official `MetaTrader5` Python package is a thin
wrapper over the Windows MT5 terminal IPC. It exists only for Windows and can
never run on a Linux/cloud host, no matter how it is installed. Pretending
otherwise is impossible, so ARES splits the problem:

    phone / laptop
        -> ARES web app
        -> ARES backend            (Linux / cloud, this process)
        -> authenticated WebSocket (bridge connects OUT to the backend)
        -> ARES MT5 bridge         (Windows, runs beside the terminal)
        -> MetaTrader 5 terminal
        -> broker

The bridge dials the backend, so the Windows machine needs no inbound ports
or public IP. Every message is correlated request/response with timeouts, and
a heartbeat drives an honest connection state. Nothing here fabricates data:
with no bridge attached, every accessor returns empty and the status is a real
DISCONNECTED with the reason.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..config import BridgeSettings
from ..logging_setup import get_logger, register_secret
from ..status import ComponentState, status_registry
from .adapter import AccountInfo, ConnectionState, mask_login

log = get_logger("mt5.bridge")

PROTOCOL_VERSION = 1


@dataclass
class BridgeInfo:
    """What the bridge told us about itself and its terminal. Every field is
    reported by the bridge from the real terminal — never assumed."""

    bridge_version: str = ""
    host: str = ""
    terminal_connected: bool = False
    terminal_path: str | None = None
    broker: str | None = None
    server: str | None = None
    mt5_state: str = "DISCONNECTED"
    detail: str = ""
    connected_at: float = 0.0
    last_heartbeat: float = 0.0

    def as_dict(self) -> dict:
        return {
            "bridge_version": self.bridge_version,
            "host": self.host,
            "terminal_connected": self.terminal_connected,
            "terminal_path": self.terminal_path,
            "broker": self.broker,
            "server": self.server,
            "mt5_state": self.mt5_state,
            "detail": self.detail,
        }


class BridgeDisconnected(RuntimeError):
    """Raised when a request is made with no live bridge session."""


class MT5BridgeServer:
    """Accepts exactly one active bridge session and brokers RPC to it."""

    def __init__(self, settings: BridgeSettings) -> None:
        self.settings = settings
        if settings.token:
            register_secret(settings.token)
        self._ws: WebSocket | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self.info = BridgeInfo()
        self.state: ConnectionState = ConnectionState.DISCONNECTED
        self.last_error: str | None = None
        self.account: AccountInfo | None = None
        self.connected_since: datetime | None = None
        self.on_state_change = None  # async callable(connected: bool)

    # -- connection state ---------------------------------------------------

    @property
    def attached(self) -> bool:
        """A bridge socket is present and its heartbeat is recent."""
        if self._ws is None:
            return False
        age = time.monotonic() - self.info.last_heartbeat
        return age <= self.settings.stale_after_seconds

    @property
    def connected(self) -> bool:
        """Bridge attached AND its MT5 terminal reports a live connection."""
        return self.attached and self.info.terminal_connected

    def publish_status(self) -> None:
        payload = self.status_payload()
        if self.connected:
            status_registry.set("mt5", ComponentState.ONLINE,
                                f"Connected via Windows bridge ({self.info.host})", payload)
        elif self.attached:
            status_registry.set(
                "mt5", ComponentState.DEGRADED,
                f"Bridge attached but MT5 is {self.info.mt5_state}: {self.info.detail}",
                payload)
        else:
            reason = self.last_error or (
                "No MT5 bridge attached. Run the ARES MT5 bridge on a Windows machine "
                "with MetaTrader 5 installed (see docs/MT5_BRIDGE.md)."
            )
            status_registry.set("mt5", ComponentState.OFFLINE, reason, payload)

    def status_payload(self) -> dict:
        return {
            "mode": "bridge",
            "attached": self.attached,
            "connected": self.connected,
            "state": self.ui_state,
            "bridge": self.info.as_dict(),
            "account": self.account.as_dict() if self.account else None,
            "last_error": self.last_error,
            "connected_since": self.connected_since.isoformat() if self.connected_since else None,
            "token_configured": bool(self.settings.token),
        }

    @property
    def ui_state(self) -> str:
        """The precise state the UI must show — never a euphemism."""
        if not self.settings.enabled:
            return "DISABLED"
        if not self.settings.token:
            return "AUTHENTICATION REQUIRED"
        if self._ws is None:
            return "DISCONNECTED"
        if not self.attached:
            return "ERROR"  # socket present but heartbeats stopped
        reported = self.info.mt5_state.upper()
        if reported in ("TERMINAL_NOT_RUNNING", "MT5_TERMINAL_NOT_RUNNING"):
            return "MT5 TERMINAL NOT RUNNING"
        if reported == "BROKER_DISCONNECTED":
            return "BROKER DISCONNECTED"
        if reported in ("AUTH_REQUIRED", "AUTHENTICATION_REQUIRED"):
            return "AUTHENTICATION REQUIRED"
        if reported == "CONNECTING":
            return "CONNECTING"
        if self.info.terminal_connected:
            return "CONNECTED"
        return "ERROR"

    # -- session handling ---------------------------------------------------

    async def serve(self, ws: WebSocket) -> None:
        """Handle one bridge session end-to-end."""
        await ws.accept()
        if not self.settings.enabled:
            await ws.close(code=4403, reason="bridge disabled")
            return
        if not self.settings.token:
            await ws.close(code=4401, reason="no bridge token configured on server")
            return

        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
            hello = json.loads(raw)
        except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
            await ws.close(code=4400, reason="invalid handshake")
            return

        token = str(hello.get("token", ""))
        if not hmac.compare_digest(token, self.settings.token):
            log.warning("bridge handshake rejected: bad token from %s", hello.get("host"))
            await ws.close(code=4401, reason="unauthorized")
            return

        if self._ws is not None:
            # One bridge at a time; the newest wins and the old one is dropped.
            log.info("replacing existing bridge session")
            try:
                await self._ws.close(code=4409, reason="replaced by new bridge session")
            except Exception:  # noqa: BLE001
                pass

        self._ws = ws
        self.info = BridgeInfo(
            bridge_version=str(hello.get("bridge_version", "unknown")),
            host=str(hello.get("host", "unknown")),
            terminal_path=hello.get("terminal_path"),
            mt5_state=str(hello.get("mt5_state", "CONNECTING")),
            detail=str(hello.get("detail", "")),
            terminal_connected=bool(hello.get("terminal_connected", False)),
            connected_at=time.monotonic(),
            last_heartbeat=time.monotonic(),
        )
        self.state = ConnectionState.CONNECTED if self.info.terminal_connected else ConnectionState.CONNECTING
        self.connected_since = datetime.now(timezone.utc)
        self.last_error = None
        await ws.send_text(json.dumps({"type": "hello_ack", "protocol": PROTOCOL_VERSION,
                                       "heartbeat": self.settings.heartbeat_interval_seconds}))
        log.info("MT5 bridge attached from %s (mt5_state=%s)", self.info.host, self.info.mt5_state)
        self.publish_status()
        if self.on_state_change:
            await self.on_state_change(self.connected)

        try:
            while True:
                message = json.loads(await ws.receive_text())
                await self._handle_message(message)
        except WebSocketDisconnect:
            log.info("MT5 bridge disconnected")
        except Exception as exc:  # noqa: BLE001
            log.warning("bridge session error: %s", exc)
        finally:
            await self._teardown(ws)

    async def _handle_message(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "heartbeat":
            self.info.last_heartbeat = time.monotonic()
            self.info.terminal_connected = bool(message.get("terminal_connected", False))
            self.info.mt5_state = str(message.get("mt5_state", self.info.mt5_state))
            self.info.detail = str(message.get("detail", ""))
            self.info.broker = message.get("broker")
            self.info.server = message.get("server")
            account = message.get("account")
            if account:
                self.account = AccountInfo(
                    login_masked=mask_login(account.get("login", "")),
                    broker=account.get("broker", ""),
                    server=account.get("server", ""),
                    currency=account.get("currency", ""),
                    balance=float(account.get("balance", 0.0)),
                    equity=float(account.get("equity", 0.0)),
                    margin_free=float(account.get("margin_free", 0.0)),
                    leverage=int(account.get("leverage", 0)),
                    trade_allowed=bool(account.get("trade_allowed", False)),
                    is_demo=bool(account.get("is_demo", False)),
                )
            else:
                self.account = None
            self.publish_status()
        elif kind == "response":
            future = self._pending.pop(str(message.get("id")), None)
            if future and not future.done():
                future.set_result(message)
        else:
            log.debug("unknown bridge message type: %s", kind)

    async def _teardown(self, ws: WebSocket) -> None:
        if self._ws is ws:
            self._ws = None
            self.state = ConnectionState.DISCONNECTED
            self.account = None
            self.info.terminal_connected = False
            self.last_error = "Bridge session ended (Windows bridge disconnected)."
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(BridgeDisconnected("bridge disconnected"))
            self._pending.clear()
            self.publish_status()
            if self.on_state_change:
                await self.on_state_change(False)

    # -- RPC ----------------------------------------------------------------

    async def call(self, method: str, params: dict | None = None) -> Any:
        """Send an RPC to the bridge and await its response.

        Raises BridgeDisconnected when no live bridge is attached — callers
        translate that into an honest offline state rather than a fake value.
        """
        ws = self._ws
        if ws is None or not self.attached:
            raise BridgeDisconnected("no MT5 bridge attached")

        request_id = uuid.uuid4().hex[:12]
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await ws.send_text(json.dumps({"type": "request", "id": request_id,
                                           "method": method, "params": params or {}}))
            message = await asyncio.wait_for(future, timeout=self.settings.request_timeout_seconds)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise BridgeDisconnected(f"bridge did not answer '{method}' within "
                                     f"{self.settings.request_timeout_seconds}s")
        finally:
            self._pending.pop(request_id, None)

        if message.get("error"):
            raise RuntimeError(f"bridge error on {method}: {message['error']}")
        return message.get("result")


class BridgeMT5Adapter:
    """Adapter with the same surface as MT5Adapter, backed by the bridge.

    Every accessor returns empty/None when the bridge is not connected, so the
    market-data service reports DATA SOURCE OFFLINE instead of inventing data.
    """

    def __init__(self, server: MT5BridgeServer) -> None:
        self.server = server

    # -- state mirrors MT5Adapter -------------------------------------------

    @property
    def connected(self) -> bool:
        return self.server.connected

    @property
    def state(self) -> ConnectionState:
        return ConnectionState.CONNECTED if self.server.connected else self.server.state

    @property
    def account(self) -> AccountInfo | None:
        return self.server.account

    @property
    def last_error(self) -> str | None:
        return self.server.last_error

    def status_payload(self) -> dict:
        return self.server.status_payload()

    async def connect(self) -> bool:
        # The bridge dials us; there is nothing to initiate from this side.
        return self.server.connected

    async def disconnect(self) -> None:
        return None

    async def health_check(self) -> bool:
        return self.server.connected

    # -- data ----------------------------------------------------------------

    async def _safe_call(self, method: str, params: dict | None = None, default: Any = None) -> Any:
        try:
            return await self.server.call(method, params)
        except BridgeDisconnected as exc:
            self.server.last_error = str(exc)
            return default
        except Exception as exc:  # noqa: BLE001
            log.warning("bridge call %s failed: %s", method, exc)
            self.server.last_error = str(exc)
            return default

    async def get_symbols(self) -> list[dict]:
        return await self._safe_call("symbols", default=[]) or []

    async def get_tick(self, symbol: str) -> dict | None:
        tick = await self._safe_call("tick", {"symbol": symbol})
        if not tick:
            return None
        tick["source"] = "MT5"
        return tick

    async def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> list[dict]:
        return await self._safe_call(
            "candles", {"symbol": symbol, "timeframe": timeframe, "count": count},
            default=[],
        ) or []

    async def get_positions(self) -> list[dict]:
        return await self._safe_call("positions", default=[]) or []
