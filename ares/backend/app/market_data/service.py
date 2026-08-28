"""Market data service.

One service owns the active provider, a tick/candle cache, and a broadcast
loop that pushes quote updates over the WebSocket hub. It never fabricates
data: when the provider is unavailable it reports DATA SOURCE OFFLINE and
returns nothing.
"""

from __future__ import annotations

import asyncio
import time

from ..config import MarketDataSettings
from ..logging_setup import get_logger
from ..status import ComponentState, status_registry
from .providers import MarketDataProvider

log = get_logger("market_data")

# Candle cache TTLs per timeframe (seconds) — short enough to stay live,
# long enough to avoid hammering the provider.
_CANDLE_TTL = {
    "M1": 5, "M2": 8, "M3": 10, "M4": 12, "M5": 15, "M6": 18, "M10": 25,
    "M12": 28, "M15": 30, "M20": 45, "M30": 60,
    "H1": 120, "H2": 180, "H3": 240, "H4": 300, "H6": 400, "H8": 500, "H12": 600,
    "D1": 600, "W1": 1800, "MN1": 3600,
}


class MarketDataService:
    def __init__(self, provider: MarketDataProvider, settings: MarketDataSettings) -> None:
        self.provider = provider
        self.settings = settings
        self.watched_symbols: list[str] = list(settings.default_symbols)
        self.latest_ticks: dict[str, dict] = {}
        self._tick_times: dict[str, float] = {}  # monotonic receipt time per symbol
        self._prev_day_close: dict[str, float] = {}
        self._daily_refs_checked_at: float = -3600.0
        self._daily_refs_failed: set[str] = set()
        self._candle_cache: dict[tuple[str, str, int], tuple[float, list[dict]]] = {}
        self._symbols_cache: tuple[float, list[dict]] | None = None
        self._task: asyncio.Task | None = None
        self.broadcast = None  # async callable injected by main (ws hub)

    # -- status ---------------------------------------------------------------

    async def refresh_status(self) -> None:
        if await self.provider.available():
            label = self.provider.source_label
            reason = "Streaming live MT5 data" if label == "MT5" else \
                "Simulation mode (explicitly enabled) — prices are SIMULATED, not live"
            state = ComponentState.ONLINE if label == "MT5" else ComponentState.DEGRADED
            status_registry.set("market_data", state, reason, {"source": label})
        else:
            status_registry.set(
                "market_data", ComponentState.OFFLINE,
                "DATA SOURCE OFFLINE — MT5 is not connected and simulation mode is not enabled",
                {"source": None},
            )

    # -- lifecycle --------------------------------------------------------------

    async def start(self) -> None:
        await self.refresh_status()
        self._task = asyncio.create_task(self._tick_loop(), name="market-data-loop")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _tick_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.settings.tick_interval_seconds)
                if not await self.provider.available():
                    continue
                await self._ensure_daily_references()
                updates = []
                for symbol in self.watched_symbols:
                    tick = await self.provider.get_tick(symbol)
                    if tick:
                        tick.update(self._change_stats(symbol, tick))
                        self._store_tick(symbol, tick)
                        updates.append(tick)
                if updates and self.broadcast:
                    await self.broadcast({"type": "ticks", "data": updates})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error("tick loop error: %s", exc)

    async def _ensure_daily_references(self) -> None:
        """Load previous-day closes for watched symbols so change/change_percent
        populate without anyone opening a D1 chart. Refreshed hourly; at most a
        few symbols per tick to keep the loop responsive."""
        now = time.monotonic()
        if now - self._daily_refs_checked_at < 3600:
            return
        missing = [s for s in self.watched_symbols if s not in self._prev_day_close][:4]
        if not missing:
            self._daily_refs_checked_at = now
            return
        for symbol in missing:
            candles = await self.provider.get_candles(symbol, "D1", 3)
            if len(candles) >= 2:
                self._prev_day_close[symbol] = candles[-2]["close"]
            else:
                # Provider has no D1 for this symbol; don't retry every tick.
                self._daily_refs_failed.add(symbol)
        if all(
            s in self._prev_day_close or s in self._daily_refs_failed
            for s in self.watched_symbols
        ):
            self._daily_refs_checked_at = now

    def _change_stats(self, symbol: str, tick: dict) -> dict:
        ref = self._prev_day_close.get(symbol)
        if ref is None:
            return {"change": None, "change_percent": None}
        mid = (tick["bid"] + tick["ask"]) / 2
        return {
            "change": round(mid - ref, 6),
            "change_percent": round((mid - ref) / ref * 100, 3),
        }

    # -- data access -------------------------------------------------------------

    async def get_symbols(self) -> list[dict]:
        if self._symbols_cache and time.monotonic() - self._symbols_cache[0] < 300:
            return self._symbols_cache[1]
        symbols = await self.provider.get_symbols()
        if symbols:
            self._symbols_cache = (time.monotonic(), symbols)
        return symbols

    def _store_tick(self, symbol: str, tick: dict) -> None:
        self.latest_ticks[symbol] = tick
        self._tick_times[symbol] = time.monotonic()

    @property
    def _tick_max_age(self) -> float:
        # A cached tick is "fresh" for a few loop intervals; beyond that the
        # data source has genuinely stopped and consumers must not price
        # anything off it.
        return max(5.0, self.settings.tick_interval_seconds * 3)

    def fresh_tick(self, symbol: str) -> dict | None:
        """Cached tick only if it is recent; None otherwise. Never returns a
        price from before the data source went quiet."""
        tick = self.latest_ticks.get(symbol)
        if tick is None:
            return None
        if time.monotonic() - self._tick_times.get(symbol, 0.0) > self._tick_max_age:
            return None
        return tick

    def fresh_ticks(self) -> dict[str, dict]:
        return {s: t for s, t in self.latest_ticks.items() if self.fresh_tick(s)}

    async def get_tick(self, symbol: str) -> dict | None:
        cached = self.fresh_tick(symbol)
        if cached:
            return cached
        tick = await self.provider.get_tick(symbol)
        if tick:
            tick.update(self._change_stats(symbol, tick))
            self._store_tick(symbol, tick)
            if symbol not in self.watched_symbols:
                self.watched_symbols.append(symbol)
        return tick

    _MAX_CANDLE_CACHE_ENTRIES = 64

    async def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> list[dict]:
        count = min(count, self.settings.candle_cache_size)
        key = (symbol, timeframe, count)
        ttl = _CANDLE_TTL.get(timeframe, 60)
        cached = self._candle_cache.get(key)
        if cached and time.monotonic() - cached[0] < ttl:
            return cached[1]
        candles = await self.provider.get_candles(symbol, timeframe, count)
        if candles:
            self._candle_cache[key] = (time.monotonic(), candles)
            if len(self._candle_cache) > self._MAX_CANDLE_CACHE_ENTRIES:
                oldest = min(self._candle_cache, key=lambda k: self._candle_cache[k][0])
                del self._candle_cache[oldest]
            if timeframe == "D1" and len(candles) >= 2:
                self._prev_day_close[symbol] = candles[-2]["close"]
        return candles

    @property
    def source_label(self) -> str:
        return self.provider.source_label
