import type { Analysis, TakeoverSession, Tick } from "../lib/types";

export const tick = (symbol: string, bid = 1.1, ask = 1.10008): Tick => ({
  symbol, bid, ask, spread_points: 8, time: new Date().toISOString(),
  source: "SIMULATED", change: 0.001, change_percent: 0.09,
});

export const analysis: Analysis = {
  symbol: "EURUSD",
  bias: "bullish",
  confidence: 4,
  confidence_label: "Strong confluence",
  confidence_factors: [
    { name: "timeframe_alignment", points: 1.0, reason: "3/3 timeframes aligned bullish" },
    { name: "liquidity", points: 0.6, reason: "sell-side liquidity swept" },
    { name: "volatility", points: -0.3, reason: "volatility elevated" },
  ],
  market_state: "trending",
  timeframe_alignment: "aligned bullish",
  timeframes: {
    H4: { trend: { direction: "bullish", score: 0.8, evidence: [] }, last_structure_event: null, dealing_range: { high: 1.2, low: 1.0, equilibrium: 1.1, position: 0.3, zone: "discount" }, volatility: { state: "normal", atr: 0.001, ratio: 1 } },
    H1: { trend: { direction: "bullish", score: 0.6, evidence: [] }, last_structure_event: null, dealing_range: null, volatility: { state: "normal", atr: 0.001, ratio: 1 } },
    M15: { trend: { direction: "bullish", score: 0.5, evidence: [] }, last_structure_event: null, dealing_range: null, volatility: { state: "elevated", atr: 0.001, ratio: 1.5 } },
  },
  structure: "H4 bullish; H1 bullish; M15 bullish",
  liquidity: { pools: [], sweeps: [{ side: "sell-side", level: 1.09, note: "sweep" }] },
  key_levels: [
    { price: 1.12, kind: "resistance", origin: "swing high" },
    { price: 1.08, kind: "support", origin: "swing low" },
  ],
  scenarios: [{ name: "continuation long", description: "Hold above the last swing low." }],
  invalidations: ["H1 close below 1.08 invalidates the bullish read"],
  risk_factors: ["volatility is elevated vs its recent baseline"],
  price: 1.1,
  data_source: "SIMULATED",
  generated_at: "2026-08-25T10:00:00+00:00",
};

export const takeoverSession: TakeoverSession = {
  id: "TK-abc12345",
  symbol: "XAUUSD",
  direction: "buy",
  reason: "bullish aligned bullish; confidence 4/5",
  confidence: 4,
  proposed_trades: [{ symbol: "XAUUSD", direction: "buy", volume: 0.05, sl: 2300, tp: 2400, executed: false }],
  max_loss: 150,
  max_trades: 1,
  duration_seconds: 3600,
  state: "REQUESTED",
  basket_id: null,
  trades_executed: 0,
  log: ["Takeover requested — awaiting explicit user authorization."],
};
