"""ARES Market Scanner: rank watched instruments by measurable evidence."""

from __future__ import annotations

import asyncio

from ..analysis.engine import AnalysisEngine
from ..logging_setup import get_logger

log = get_logger("scanner")


class MarketScanner:
    def __init__(self, engine: AnalysisEngine, max_concurrency: int = 4) -> None:
        self.engine = engine
        self._sem = asyncio.Semaphore(max_concurrency)
        self.last_scan: list[dict] = []

    async def _analyze_one(self, symbol: str) -> dict | None:
        async with self._sem:
            try:
                analysis = await self.engine.analyze(symbol)
            except Exception as exc:  # noqa: BLE001
                log.error("scan failed for %s: %s", symbol, exc)
                return None
        if analysis is None:
            return None
        setup = analysis["scenarios"][0]["name"] if analysis["scenarios"] else "none"
        risk = "elevated" if analysis["risk_factors"] else "normal"
        return {
            "symbol": symbol,
            "bias": analysis["bias"],
            "setup": setup,
            "confidence": analysis["confidence"],
            "volatility": analysis["timeframes"]["M15"]["volatility"]["state"],
            "risk": risk,
            "alignment": analysis["timeframe_alignment"],
            "data_source": analysis["data_source"],
        }

    async def scan(self, symbols: list[str]) -> list[dict]:
        results = await asyncio.gather(*(self._analyze_one(s) for s in symbols))
        rows = [r for r in results if r]
        rows.sort(key=lambda r: (-r["confidence"], r["symbol"]))
        self.last_scan = rows
        return rows
