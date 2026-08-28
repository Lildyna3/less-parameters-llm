"""Market data providers.

MT5Provider     – real broker data via the managed MT5 adapter.
SimulatedProvider – deterministic random-walk feed for the safe demo/testing
environment (spec §47). It exists ONLY when explicitly enabled with
ARES_MARKET_DATA__MODE=simulation and every payload is labeled
source="SIMULATED" so it can never be mistaken for live prices.
"""

from __future__ import annotations

import math
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ..mt5.adapter import MT5Adapter, TIMEFRAME_MINUTES


class MarketDataProvider(ABC):
    source_label: str

    @abstractmethod
    async def available(self) -> bool: ...

    @abstractmethod
    async def get_symbols(self) -> list[dict]: ...

    @abstractmethod
    async def get_tick(self, symbol: str) -> dict | None: ...

    @abstractmethod
    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict]: ...


class MT5Provider(MarketDataProvider):
    source_label = "MT5"

    def __init__(self, adapter: MT5Adapter) -> None:
        self.adapter = adapter

    async def available(self) -> bool:
        return self.adapter.connected

    async def get_symbols(self) -> list[dict]:
        return await self.adapter.get_symbols()

    async def get_tick(self, symbol: str) -> dict | None:
        return await self.adapter.get_tick(symbol)

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict]:
        return await self.adapter.get_candles(symbol, timeframe, count)


# ---------------------------------------------------------------------------

_SIM_BASE_PRICES = {
    "EURUSD": (1.0850, 5), "GBPUSD": (1.2700, 5), "USDJPY": (148.50, 3),
    "USDCHF": (0.8800, 5), "AUDUSD": (0.6600, 5), "NZDUSD": (0.6100, 5),
    "USDCAD": (1.3600, 5), "EURGBP": (0.8550, 5), "EURJPY": (161.20, 3),
    "GBPJPY": (188.60, 3), "XAUUSD": (2350.00, 2), "XAGUSD": (28.50, 3),
    "US500": (5300.0, 1), "BTCUSD": (64000.0, 1),
}


class SimulatedProvider(MarketDataProvider):
    """Seeded random-walk generator. Candle history is deterministic per
    (symbol, timeframe) so charts and analysis are reproducible in tests."""

    source_label = "SIMULATED"

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self._live: dict[str, float] = {}

    async def available(self) -> bool:
        return True

    async def get_symbols(self) -> list[dict]:
        return [
            {"name": name, "description": f"Simulated {name}", "digits": digits,
             "point": 10 ** -digits, "trade_mode": 4}
            for name, (_, digits) in _SIM_BASE_PRICES.items()
        ]

    def _spread(self, symbol: str, price: float) -> float:
        return max(price * 0.00006, 10 ** -_SIM_BASE_PRICES.get(symbol, (0, 5))[1] * 8)

    async def get_tick(self, symbol: str) -> dict | None:
        if symbol not in _SIM_BASE_PRICES:
            return None
        base, digits = _SIM_BASE_PRICES[symbol]
        price = self._live.get(symbol)
        if price is None:
            candles = await self.get_candles(symbol, "M1", 2)
            price = candles[-1]["close"] if candles else base
        # small live wiggle
        price += price * random.gauss(0, 0.00004)
        self._live[symbol] = price
        half_spread = self._spread(symbol, price) / 2
        point = 10 ** -digits
        return {
            "symbol": symbol,
            "bid": round(price - half_spread, digits),
            "ask": round(price + half_spread, digits),
            "spread_points": round(2 * half_spread / point, 1),
            "time": datetime.now(timezone.utc).isoformat(),
            "source": self.source_label,
        }

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict]:
        if symbol not in _SIM_BASE_PRICES or timeframe not in TIMEFRAME_MINUTES:
            return []
        base, digits = _SIM_BASE_PRICES[symbol]
        minutes = TIMEFRAME_MINUTES[timeframe]
        now = int(time.time()) // (minutes * 60) * (minutes * 60)
        rng = random.Random(f"{self.seed}:{symbol}:{timeframe}")
        vol = base * 0.0008 * math.sqrt(minutes / 15)

        candles: list[dict] = []
        price = base
        # gentle trend + mean reversion so structure detection has real shape
        for i in range(count):
            t = now - (count - 1 - i) * minutes * 60
            drift = base * 0.00015 * math.sin(i / 24) - (price - base) * 0.01
            open_p = price
            close_p = open_p + drift + rng.gauss(0, vol)
            high_p = max(open_p, close_p) + abs(rng.gauss(0, vol * 0.6))
            low_p = min(open_p, close_p) - abs(rng.gauss(0, vol * 0.6))
            candles.append({
                "time": t,
                "open": round(open_p, digits), "high": round(high_p, digits),
                "low": round(low_p, digits), "close": round(close_p, digits),
                "volume": round(abs(rng.gauss(500, 200)) + 50),
            })
            price = close_p

        # Each (symbol, timeframe) walk is independently seeded, so the series
        # would end at different prices. Shift the whole series so every
        # timeframe converges on the one shared live price — otherwise the
        # live tick stream visually rips the last candle of other timeframes.
        anchor = self._live.setdefault(symbol, price)
        delta = anchor - candles[-1]["close"]
        if abs(delta) > 10 ** -digits:
            for c in candles:
                for key in ("open", "high", "low", "close"):
                    c[key] = round(c[key] + delta, digits)
        return candles
