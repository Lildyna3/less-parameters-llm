"""MT5 adapter: one managed connection, verified state, no fakery.

The adapter wraps the (Windows-only) MetaTrader5 package behind an interface
the rest of ARES consumes. Connection state transitions are strict:

  DISCONNECTED -> CONNECTING -> CONNECTED   (only after account info AND a
                                             real tick were retrieved)

Any failure records the actual reason. When the platform/package/terminal or
credentials are missing, connect() returns a truthful failure instead of
pretending. Nothing in this module ever fabricates prices, candles, account
data, or execution results.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..config import MT5Settings
from ..logging_setup import get_logger, register_secret
from .detect import MT5Detection, detect_mt5

log = get_logger("mt5")

# Every timeframe the MetaTrader5 package exposes natively. Nothing here is
# aggregated or invented: if MT5 does not provide it, ARES does not offer it.
TIMEFRAME_MINUTES = {
    "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M6": 6, "M10": 10,
    "M12": 12, "M15": 15, "M20": 20, "M30": 30,
    "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360, "H8": 480, "H12": 720,
    "D1": 1440, "W1": 10080, "MN1": 43200,
}


class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


@dataclass
class AccountInfo:
    login_masked: str
    broker: str
    server: str
    currency: str
    balance: float
    equity: float
    margin_free: float
    leverage: int
    trade_allowed: bool
    is_demo: bool

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def mask_login(login: int | str) -> str:
    text = str(login)
    return "*" * max(0, len(text) - 4) + text[-4:]


class MT5Adapter:
    """Single managed MT5 connection. All MetaTrader5 calls run in a lock-
    guarded thread executor because the underlying library is synchronous and
    not thread-safe across concurrent calls."""

    def __init__(self, settings: MT5Settings) -> None:
        self.settings = settings
        if settings.password:
            register_secret(settings.password)
        self.state = ConnectionState.DISCONNECTED
        self.auth_mode = "login" if settings.credentials_configured else "attach"
        self.last_error: str | None = None
        self.last_connected_at: datetime | None = None
        self.detection: MT5Detection = detect_mt5(settings.path)
        self.account: AccountInfo | None = None
        self._mt5: Any = None
        self._lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> bool:
        """Full verified connection flow. Returns True only after account info
        and live market data were both retrieved successfully."""
        self.detection = detect_mt5(self.settings.path)

        if not self.detection.platform_supported or not self.detection.package_available:
            self.state = ConnectionState.DISCONNECTED
            self.last_error = "; ".join(self.detection.notes) or "MT5 unavailable"
            log.info("MT5 unavailable on this host: %s", self.last_error)
            return False

        # Two legitimate ways in, in order of preference:
        #   1. attach  - the terminal is already open and logged in. No password
        #                is stored anywhere, which is the safer default.
        #   2. login   - MT5_LOGIN/PASSWORD/SERVER are configured, so ARES can
        #                bring the terminal up unattended (headless/VPS).
        # Either way CONNECTED is only reported after account info AND a real
        # tick are retrieved, so neither path can fake a connection.
        self.auth_mode = "login" if self.settings.credentials_configured else "attach"

        self.state = ConnectionState.CONNECTING
        try:
            ok = await asyncio.to_thread(self._connect_sync)
        except Exception as exc:  # noqa: BLE001 - report the actual failure
            self.state = ConnectionState.ERROR
            self.last_error = f"MT5 connection error: {exc}"
            log.error("MT5 connect failed: %s", exc)
            return False

        if ok:
            self.state = ConnectionState.CONNECTED
            self.last_connected_at = datetime.now(timezone.utc)
            self.last_error = None
            log.info("MT5 connected and verified (server=%s)", self.settings.server)
        return ok

    def _connect_sync(self) -> bool:
        import MetaTrader5 as mt5  # imported lazily; Windows-only

        with self._lock:
            kwargs: dict[str, Any] = {}
            if self.settings.credentials_configured:
                kwargs.update({
                    "login": self.settings.login,
                    "password": self.settings.password,
                    "server": self.settings.server,
                })
            if self.detection.terminal_path:
                kwargs["path"] = self.detection.terminal_path

            if not mt5.initialize(**kwargs):
                code, message = mt5.last_error()
                if self.auth_mode == "attach":
                    self.last_error = (
                        f"MT5 initialize failed ({code}): {message}. No credentials are "
                        "configured, so ARES tried to attach to an already-running "
                        "terminal. Open MetaTrader 5 and log into your demo account, or "
                        "set MT5_LOGIN / MT5_PASSWORD / MT5_SERVER in your local .env."
                    )
                else:
                    self.last_error = f"MT5 initialize failed ({code}): {message}"
                self.state = ConnectionState.ERROR
                return False

            info = mt5.account_info()
            if info is None:
                self.last_error = "MT5 initialized but account_info() returned nothing"
                self.state = ConnectionState.ERROR
                mt5.shutdown()
                return False

            # Verify market data genuinely flows before declaring CONNECTED.
            probe = None
            for symbol in ("EURUSD", "XAUUSD"):
                if mt5.symbol_select(symbol, True):
                    probe = mt5.symbol_info_tick(symbol)
                    if probe is not None:
                        break
            if probe is None:
                self.last_error = "MT5 authenticated but no market data tick could be retrieved"
                self.state = ConnectionState.ERROR
                mt5.shutdown()
                return False

            self._mt5 = mt5
            self.account = AccountInfo(
                login_masked=mask_login(info.login),
                broker=info.company,
                server=info.server,
                currency=info.currency,
                balance=float(info.balance),
                equity=float(info.equity),
                margin_free=float(info.margin_free),
                leverage=int(info.leverage),
                trade_allowed=bool(info.trade_allowed),
                is_demo=(getattr(info, "trade_mode", None) == mt5.ACCOUNT_TRADE_MODE_DEMO),
            )
            return True

    async def disconnect(self) -> None:
        if self._mt5 is not None:
            await asyncio.to_thread(self._shutdown_sync)
        self.state = ConnectionState.DISCONNECTED
        self.account = None

    def _shutdown_sync(self) -> None:
        with self._lock:
            try:
                self._mt5.shutdown()
            finally:
                self._mt5 = None

    @property
    def connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED and self._mt5 is not None

    async def health_check(self) -> bool:
        """Cheap liveness probe used by the connection monitor."""
        if not self.connected:
            return False
        try:
            info = await asyncio.to_thread(self._account_info_sync)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"MT5 health check failed: {exc}"
            self.state = ConnectionState.ERROR
            return False
        if info is None:
            self.last_error = "MT5 terminal no longer responding (account_info empty)"
            self.state = ConnectionState.ERROR
            return False
        return True

    def _account_info_sync(self):
        with self._lock:
            return self._mt5.account_info() if self._mt5 else None

    # -- data access (all return None/[] and record errors when offline) ------

    async def get_symbols(self) -> list[dict]:
        if not self.connected:
            return []
        def _sync() -> list[dict]:
            with self._lock:
                symbols = self._mt5.symbols_get() or []
                return [
                    {"name": s.name, "description": s.description, "digits": s.digits,
                     "point": s.point, "trade_mode": s.trade_mode}
                    for s in symbols
                ]
        return await asyncio.to_thread(_sync)

    async def get_tick(self, symbol: str) -> dict | None:
        if not self.connected:
            return None
        def _sync() -> dict | None:
            with self._lock:
                self._mt5.symbol_select(symbol, True)
                tick = self._mt5.symbol_info_tick(symbol)
                info = self._mt5.symbol_info(symbol)
                if tick is None or info is None:
                    return None
                return {
                    "symbol": symbol,
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "spread_points": round((tick.ask - tick.bid) / info.point, 1) if info.point else None,
                    "time": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
                    "source": "MT5",
                }
        return await asyncio.to_thread(_sync)

    async def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> list[dict]:
        if not self.connected or timeframe not in TIMEFRAME_MINUTES:
            return []
        def _sync() -> list[dict]:
            import MetaTrader5 as mt5
            # Resolved from the package itself, so an MT5 build lacking a
            # constant simply omits that timeframe rather than erroring.
            tf_map = {
                name: getattr(mt5, f"TIMEFRAME_{name}")
                for name in TIMEFRAME_MINUTES
                if hasattr(mt5, f"TIMEFRAME_{name}")
            }
            if timeframe not in tf_map:
                return []
            with self._lock:
                rates = self._mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, count)
            if rates is None:
                return []
            return [
                {
                    "time": int(r["time"]),
                    "open": float(r["open"]), "high": float(r["high"]),
                    "low": float(r["low"]), "close": float(r["close"]),
                    "volume": float(r["tick_volume"]),
                }
                for r in rates
            ]
        return await asyncio.to_thread(_sync)

    def status_payload(self) -> dict:
        return {
            "mode": "direct",
            "state": self.state.value,
            "auth_mode": self.auth_mode,
            "detection": self.detection.as_dict(),
            "credentials_configured": self.settings.credentials_configured,
            "last_error": self.last_error,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "account": self.account.as_dict() if self.account else None,
        }
