"""ARES Command Center brain.

Deterministic intent parsing + orchestration over the real subsystems.
The optional LLM provider only narrates structured evidence; intent handling,
confidence, and every execution pathway are code, so a natural-language
message can never bypass safety controls (execution intents return an
authorization requirement instead of acting).

Responses carry optional `actions` (e.g. open_chart, set_symbol) that the
frontend applies — that is how the Command Center controls the app.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..analysis.engine import AnalysisEngine
from ..execution.baskets import BasketManager
from ..execution.paper import PaperTradingEngine
from ..execution.takeover import TakeoverManager
from ..logging_setup import get_logger
from ..market_data.service import MarketDataService
from ..market_data.sessions import current_sessions
from ..news.calendar import EconomicCalendar
from ..risk.engine import RiskEngine
from ..scanner.scanner import MarketScanner
from ..status import status_registry
from .provider import AIProvider

log = get_logger("command")

_SYMBOL_RE = re.compile(r"\b([A-Z]{6}|XAUUSD|XAGUSD|US500|BTCUSD|GOLD|SILVER)\b", re.IGNORECASE)
_TF_RE = re.compile(r"\b(M1|M5|M15|M30|H1|H4|D1|W1)\b", re.IGNORECASE)
_ALIASES = {"GOLD": "XAUUSD", "SILVER": "XAGUSD"}


def deterministic_narrative(analysis: dict, news_warning: dict | None = None) -> str:
    """Render the structured analysis in ARES's voice without an LLM."""
    a = analysis
    lines = [
        f"{a['symbol']} — {a['bias'].capitalize()} bias — Confidence {a['confidence']}/5 ({a['confidence_label']}).",
        "",
        a["structure"] + ".",
    ]
    sweeps = a["liquidity"].get("sweeps", [])
    if sweeps:
        s = sweeps[-1]
        lines.append(f"Liquidity: {s['side']} swept at {s['level']} — {s['note']}.")
    pools = a["liquidity"].get("pools", [])
    if pools:
        p = pools[-1]
        lines.append(f"Resting liquidity: {p['note']} near {p['level']} ({p['side']}).")
    dr = a["timeframes"]["H1"].get("dealing_range")
    if dr:
        lines.append(f"Price is in the {dr['zone']} of the H1 dealing range "
                     f"({dr['low']}–{dr['high']}, position {dr['position']}).")
    if a["invalidations"]:
        lines.append(f"Invalidation: {a['invalidations'][0]}.")
    if a["risk_factors"]:
        lines.append("Risk: " + "; ".join(a["risk_factors"]) + ".")
    if news_warning:
        lines.append(f"⚠ {news_warning['warning']}")
    lines.append("")
    top = sorted(a["confidence_factors"], key=lambda f: -abs(f["points"]))[:3]
    lines.append("Why this confidence: " + "; ".join(f["reason"] for f in top) + ".")
    if a["data_source"] == "SIMULATED":
        lines.append("Note: this analysis runs on the SIMULATED demo feed, not live prices.")
    lines.append("Action: monitor for confirmation rather than blindly entering.")
    return "\n".join(lines)


class CommandCenter:
    def __init__(
        self,
        market_data: MarketDataService,
        engine: AnalysisEngine,
        scanner: MarketScanner,
        paper: PaperTradingEngine,
        baskets: BasketManager,
        takeover: TakeoverManager,
        risk: RiskEngine,
        calendar: EconomicCalendar,
        provider: AIProvider | None = None,
    ) -> None:
        self.market_data = market_data
        self.engine = engine
        self.scanner = scanner
        self.paper = paper
        self.baskets = baskets
        self.takeover = takeover
        self.risk = risk
        self.calendar = calendar
        self.provider = provider
        self.last_analysis: dict[str, dict] = {}
        self.previous_analysis: dict[str, dict] = {}

    def remember(self, analysis: dict) -> None:
        symbol = analysis["symbol"]
        if symbol in self.last_analysis:
            self.previous_analysis[symbol] = self.last_analysis[symbol]
        self.last_analysis[symbol] = analysis

    def _extract_symbol(self, text: str) -> str | None:
        m = _SYMBOL_RE.search(text)
        if not m:
            return None
        sym = m.group(1).upper()
        return _ALIASES.get(sym, sym)

    async def _narrate(self, analysis: dict, question: str | None) -> str:
        news_warning = self.calendar.news_risk_for(analysis["symbol"])
        if self.provider is not None:
            try:
                return await self.provider.narrate(analysis, question)
            except Exception as exc:  # noqa: BLE001
                log.warning("AI narration failed, using deterministic narrator: %s", exc)
        return deterministic_narrative(analysis, news_warning)

    async def handle(self, message: str) -> dict:
        """Returns {reply, analysis?, actions?, data?}."""
        text = message.strip()
        lower = text.lower()
        symbol = self._extract_symbol(text)

        # ---- market scan -----------------------------------------------------
        if any(k in lower for k in ("scan the market", "scan markets", "market scan",
                                    "across the market", "scan")) and "scanner" not in lower:
            rows = await self.scanner.scan(self.market_data.watched_symbols[:12])
            if not rows:
                return {"reply": "Market scan came back empty — DATA SOURCE OFFLINE. "
                                 "Connect MT5 (or explicitly enable simulation mode) and try again."}
            top = rows[:5]
            summary = "\n".join(
                f"• {r['symbol']}: {r['bias']} ({r['alignment']}), {r['setup']}, "
                f"confidence {r['confidence']}/5, volatility {r['volatility']}"
                for r in top
            )
            return {"reply": f"Scanned {len(rows)} instruments. Strongest evidence right now:\n{summary}",
                    "data": {"scan": rows}, "actions": [{"type": "open_section", "section": "scanner"}]}

        # ---- positions / trades / account ------------------------------------
        if any(k in lower for k in ("my positions", "show positions", "open positions")):
            positions = [p.as_dict() for p in self.paper.positions.values()]
            reply = (f"You have {len(positions)} open paper position(s)."
                     if positions else "No open positions.")
            return {"reply": reply, "data": {"positions": positions},
                    "actions": [{"type": "open_section", "section": "positions"}]}

        if any(k in lower for k in ("show risk", "risk status", "my risk")):
            snap = self.risk.snapshot()
            reply = (f"Risk state: daily P/L {snap['daily_pl']}, {snap['session_trades']} trades this session, "
                     f"emergency stop {'ENGAGED' if snap['emergency_stop'] else 'off'}, "
                     f"{snap['blocks_issued']} orders blocked so far.")
            return {"reply": reply, "data": {"risk": snap}}

        if "account" in lower or "balance" in lower or "equity" in lower:
            snap = self.paper.account_snapshot()
            return {"reply": f"Paper account: balance {snap['balance']} {snap['currency']}, "
                             f"equity {snap['equity']}, floating P/L {snap['floating_pl']}, "
                             f"daily P/L {snap['daily_pl']}.",
                    "data": {"account": snap}}

        # ---- basket control -----------------------------------------------------
        basket_close = re.search(r"close\s+basket\s+#?([A-Za-z0-9-]+)", lower)
        if basket_close:
            result = await self.baskets.close_basket(basket_close.group(1))
            return {"reply": result["message"], "data": result}

        # ---- takeover: request only; authorization is a separate explicit API ----
        if "takeover" in lower:
            if any(k in lower for k in ("stop", "cancel", "abort")):
                result = await self.takeover.stop(reason="user command")
                return {"reply": result["message"], "data": result}
            if any(k in lower for k in ("authorize", "approve", "go ahead", "confirm")):
                return {"reply": "For safety, Takeover Mode can't be authorized from chat. "
                                 "Use the explicit Authorize control on the takeover panel.",
                        "actions": [{"type": "open_section", "section": "positions"}]}
            if symbol:
                return await self._takeover_request(symbol)
            return {"reply": "Tell me the instrument — e.g. “request takeover on XAUUSD”. "
                             "I'll propose trades; you authorize explicitly."}

        # ---- emergency stop -------------------------------------------------------
        if "emergency stop" in lower or "stop everything" in lower:
            self.risk.engage_emergency_stop("user command")
            closed = await self.paper.emergency_close_all()
            await self.takeover.stop(reason="emergency stop")
            return {"reply": f"EMERGENCY STOP engaged. Closed {len(closed)} open position(s); "
                             "all execution is blocked until you release it in Settings → Risk.",
                    "data": {"closed": closed}}

        # ---- open chart / switch symbol -------------------------------------------
        if symbol and any(k in lower for k in ("open", "switch to", "show", "chart")) and \
                not any(k in lower for k in ("analyz", "analys", "what")):
            tf = _TF_RE.search(text)
            actions = [{"type": "set_symbol", "symbol": symbol}, {"type": "open_section", "section": "chart"}]
            if tf:
                actions.append({"type": "set_timeframe", "timeframe": tf.group(1).upper()})
            return {"reply": f"Opening {symbol}" + (f" on {tf.group(1).upper()}" if tf else "") + ".",
                    "actions": actions}

        # ---- time/session awareness ------------------------------------------------
        if "session" in lower or "market open" in lower or "what time" in lower:
            s = current_sessions()
            active = ", ".join(s["active_sessions"]) or "none"
            return {"reply": f"UTC {s['utc_time']}. FX market is {'open' if s['fx_market_open'] else 'closed'}. "
                             f"Active sessions: {active}"
                             + (f" ({s['overlap']})." if s["overlap"] else "."),
                    "data": {"sessions": s}}

        # ---- system status ------------------------------------------------------------
        if "status" in lower or "online" in lower or "connected" in lower:
            snapshot = status_registry.snapshot()
            mt5_state = snapshot["mt5"]["state"]
            md = snapshot["market_data"]
            reply = f"ARES is up. MT5 is {mt5_state}"
            if mt5_state != "ONLINE":
                reply += f" ({snapshot['mt5']['reason']})"
            reply += f". Market data: {md['state']} — {md['reason']}."
            return {"reply": reply, "data": {"status": snapshot}}

        # ---- news / web intelligence ---------------------------------------------------
        if any(k in lower for k in ("news", "cpi", "nfp", "fomc", "rate decision")):
            upcoming = self.calendar.upcoming()
            web = status_registry.get("web_intelligence")
            reply = ""
            if upcoming:
                lines = [f"• {e['scheduled_at']} {e['currency']} {e['title']} (impact: {e['impact']})"
                         for e in upcoming[:5]]
                reply = "Upcoming calendar events:\n" + "\n".join(lines) + "\n\n"
            else:
                reply = "The economic calendar is currently empty (no feed configured; events can be added in the News section).\n\n"
            reply += f"Web intelligence is currently unavailable." if web.state.value != "ONLINE" else ""
            return {"reply": reply.strip(), "actions": [{"type": "open_section", "section": "news"}]}

        # ---- comparison -------------------------------------------------------------------
        compare = re.search(r"compare\s+([A-Za-z]{6})\s+(?:and|vs\.?|with)\s+([A-Za-z]{6})", lower)
        if compare:
            s1, s2 = compare.group(1).upper(), compare.group(2).upper()
            a1, a2 = await self.engine.analyze(s1), await self.engine.analyze(s2)
            if not a1 or not a2:
                return {"reply": "I can't compare those — DATA SOURCE OFFLINE for at least one symbol."}
            self.remember(a1)
            self.remember(a2)
            reply = (f"{s1}: {a1['bias']} ({a1['timeframe_alignment']}), confidence {a1['confidence']}/5.\n"
                     f"{s2}: {a2['bias']} ({a2['timeframe_alignment']}), confidence {a2['confidence']}/5.\n"
                     f"Stronger evidence: {s1 if a1['confidence'] >= a2['confidence'] else s2}.")
            return {"reply": reply, "data": {"analyses": [a1, a2]}}

        # ---- "what changed?" — diff a fresh analysis against the previous one ----------------
        if "what changed" in lower or "what's changed" in lower or "whats changed" in lower:
            target = symbol or (list(self.last_analysis)[-1] if self.last_analysis else None)
            if target is None or target not in self.last_analysis:
                return {"reply": "Nothing to compare yet — run an analysis first (e.g. “Analyze EURUSD”)."}
            baseline = self.last_analysis[target]
            fresh = await self.engine.analyze(target)
            if fresh is None:
                return {"reply": f"Can't re-analyze {target} — DATA SOURCE OFFLINE."}
            self.remember(fresh)
            changes: list[str] = []
            if fresh["bias"] != baseline["bias"]:
                changes.append(f"bias shifted {baseline['bias']} → {fresh['bias']}")
            if fresh["confidence"] != baseline["confidence"]:
                changes.append(f"confidence {baseline['confidence']}/5 → {fresh['confidence']}/5")
            if fresh["timeframe_alignment"] != baseline["timeframe_alignment"]:
                changes.append(
                    f"alignment {baseline['timeframe_alignment']} → {fresh['timeframe_alignment']}")
            old_event = baseline["timeframes"]["M15"]["last_structure_event"]
            new_event = fresh["timeframes"]["M15"]["last_structure_event"]
            if new_event and new_event != old_event:
                changes.append(f"new M15 {new_event['kind']} {new_event['direction']} at {new_event['level']}")
            if baseline.get("price"):
                move = fresh["price"] - baseline["price"]
                pct = move / baseline["price"] * 100
                changes.append(
                    f"price {move:+.5g} ({pct:+.3f}%) since the last read at {baseline['generated_at']}")
            body = "\n".join(f"• {c}" for c in changes) if changes else "• no material change"
            return {"reply": f"{target} since your last analysis:\n{body}", "analysis": fresh}

        # ---- follow-up questions about the last analysis ------------------------------------
        if not symbol and self.last_analysis and any(
            k in lower for k in ("why", "confidence", "invalidat", "what changed", "watch", "liquidity")
        ):
            analysis = list(self.last_analysis.values())[-1]
            if "invalidat" in lower:
                inv = analysis["invalidations"] or ["no explicit invalidation level identified"]
                return {"reply": f"Invalidation for {analysis['symbol']}: " + "; ".join(inv)}
            if "confidence" in lower or "why" in lower:
                factors = "\n".join(
                    f"• {f['name']}: {f['points']:+.1f} — {f['reason']}"
                    for f in analysis["confidence_factors"]
                )
                return {"reply": f"{analysis['symbol']} confidence {analysis['confidence']}/5 breaks down as:\n{factors}"}
            if "liquidity" in lower:
                liq = analysis["liquidity"]
                parts = [f"• {p['note']} at {p['level']} ({p['side']})" for p in liq.get("pools", [])]
                parts += [f"• swept: {s['note']} at {s['level']}" for s in liq.get("sweeps", [])]
                return {"reply": f"Liquidity picture on {analysis['symbol']}:\n" + ("\n".join(parts) or "nothing notable detected.")}

        # ---- analysis (default when a symbol is present) --------------------------------------
        if symbol:
            news_warning = self.calendar.news_risk_for(symbol)
            analysis = await self.engine.analyze(symbol, news_risk=news_warning is not None)
            if analysis is None:
                return {"reply": f"I can't analyze {symbol} right now — DATA SOURCE OFFLINE. "
                                 f"{status_registry.get('market_data').reason}"}
            self.remember(analysis)
            reply = await self._narrate(analysis, text)
            return {"reply": reply, "analysis": analysis,
                    "actions": [{"type": "set_symbol", "symbol": symbol}]}

        # ---- fallback / help --------------------------------------------------------------------
        return {"reply": (
            "I'm ARES. Try: “Analyze XAUUSD”, “Scan the market”, “Show my positions”, "
            "“Show risk”, “Compare EURUSD and GBPUSD”, “Open GBPJPY H1”, “What session is it?”, "
            "or “Request takeover on EURUSD” (execution always needs your explicit authorization)."
        )}

    async def _takeover_request(self, symbol: str) -> dict:
        analysis = await self.engine.analyze(symbol)
        if analysis is None:
            return {"reply": f"Can't build a takeover plan for {symbol} — DATA SOURCE OFFLINE."}
        self.remember(analysis)
        if analysis["confidence"] < 4 or analysis["bias"] == "neutral":
            return {"reply": (f"Not requesting takeover: {symbol} evidence is only "
                              f"{analysis['confidence']}/5 ({analysis['bias']}). "
                              "I only request takeover at 4/5 or better with a clear direction."),
                    "analysis": analysis}

        tick = await self.market_data.get_tick(symbol)
        if tick is None:
            return {"reply": "Tick unavailable — cannot size the trade."}
        direction = "buy" if analysis["bias"] == "bullish" else "sell"
        entry = tick["ask"] if direction == "buy" else tick["bid"]
        atr_val = analysis["timeframes"]["M15"]["volatility"]["atr"] or entry * 0.001
        sl = entry - 2 * atr_val if direction == "buy" else entry + 2 * atr_val
        tp = entry + 3 * atr_val if direction == "buy" else entry - 3 * atr_val
        risk_amount = min(self.takeover.settings.max_total_risk / 2, 50.0)
        volume = max(self.paper.position_size_for_risk(symbol, entry, sl, risk_amount), 0.01)

        digits = 3 if symbol.endswith("JPY") else 2 if symbol.startswith("XAU") else 5
        result = self.takeover.request(
            symbol=symbol, direction=direction,
            reason=f"{analysis['bias']} {analysis['timeframe_alignment']}; "
                   f"confidence {analysis['confidence']}/5",
            confidence=analysis["confidence"],
            proposed_trades=[{
                "symbol": symbol, "direction": direction, "volume": volume,
                "sl": round(sl, digits), "tp": round(tp, digits),
            }],
        )
        if not result["success"]:
            return {"reply": result["message"]}
        session = result["session"]
        trade = session["proposed_trades"][0]
        return {
            "reply": (f"Confidence {analysis['confidence']}/5 — strong setup on {symbol}. "
                      f"Requesting authorization for Takeover Mode:\n"
                      f"• {direction.upper()} {trade['volume']} lots @ ~{entry}\n"
                      f"• SL {trade['sl']} / TP {trade['tp']}\n"
                      f"• Max loss {session['max_loss']} | max trades {session['max_trades']} | "
                      f"time limit {session['duration_seconds'] // 60} min\n"
                      f"Reason: {session['reason']}\n\n"
                      "Authorize it explicitly on the takeover panel — I can't approve it myself."),
            "data": {"takeover": session}, "analysis": analysis,
            "actions": [{"type": "takeover_requested"}],
        }
