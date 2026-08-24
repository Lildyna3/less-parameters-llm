export interface Tick {
  symbol: string;
  bid: number;
  ask: number;
  spread_points: number | null;
  time: string;
  source: string;
  change?: number | null;
  change_percent?: number | null;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ComponentStatus {
  state: "ONLINE" | "DEGRADED" | "OFFLINE";
  reason: string;
  detail: Record<string, unknown>;
  updated_at: string;
}

export type StatusMap = Record<string, ComponentStatus>;

export interface ConfidenceFactor {
  name: string;
  points: number;
  reason: string;
}

export interface Analysis {
  symbol: string;
  bias: string;
  confidence: number;
  confidence_label: string;
  confidence_factors: ConfidenceFactor[];
  market_state: string;
  timeframe_alignment: string;
  timeframes: Record<string, {
    trend: { direction: string; score: number; evidence: string[] };
    last_structure_event: { kind: string; direction: string; level: number; note: string } | null;
    dealing_range: { high: number; low: number; equilibrium: number; position: number; zone: string } | null;
    volatility: { state: string; atr: number; ratio: number | null };
  }>;
  structure: string;
  liquidity: {
    pools: { side: string; level: number; note: string }[];
    sweeps: { side: string; level: number; note: string }[];
  };
  key_levels: { price: number; kind: string; origin: string }[];
  scenarios: { name: string; description: string }[];
  invalidations: string[];
  risk_factors: string[];
  price: number;
  data_source: string;
  generated_at: string;
}

export interface Position {
  id: string;
  symbol: string;
  direction: string;
  volume: number;
  entry: number;
  sl: number | null;
  tp: number | null;
  opened_at: string;
  strategy: string | null;
  confidence: number | null;
  basket_id: string | null;
  floating_pl: number;
  current_price: number | null;
}

export interface Basket {
  id: string;
  strategy: string;
  symbol: string;
  direction: string;
  max_loss: number;
  status: string;
  open_trades: number;
  closed_trades: number;
  combined_exposure_lots: number;
  combined_pl: number;
  positions: Position[];
}

export interface Trade {
  id: string;
  symbol: string;
  direction: string;
  volume: number;
  entry: number;
  exit: number;
  sl: number | null;
  tp: number | null;
  pl: number;
  opened_at: string;
  closed_at: string;
  close_reason: string;
  strategy: string | null;
  confidence: number | null;
}

export interface AccountSnapshot {
  mode: string;
  currency: string;
  balance: number;
  equity: number;
  floating_pl: number;
  daily_pl: number;
  drawdown_percent: number;
  open_positions: number;
  trades_closed: number;
  win_rate: number | null;
  average_r: number | null;
  profit_factor: number | null;
  exposure_lots: number;
}

export interface ScanRow {
  symbol: string;
  bias: string;
  setup: string;
  confidence: number;
  volatility: string;
  risk: string;
  alignment: string;
  data_source: string;
}

export interface AlertEvent {
  id: number;
  kind: string;
  severity: string;
  message: string;
  at: string;
}

export interface TakeoverSession {
  id: string;
  symbol: string;
  direction: string;
  reason: string;
  confidence: number;
  proposed_trades: { symbol: string; direction: string; volume: number; sl: number; tp: number | null; executed: boolean }[];
  max_loss: number;
  max_trades: number;
  duration_seconds: number;
  state: string;
  basket_id: string | null;
  trades_executed: number;
  log: string[];
}

export interface CommandAction {
  type: string;
  symbol?: string;
  timeframe?: string;
  section?: string;
}

export interface CommandResponse {
  reply: string;
  analysis?: Analysis;
  actions?: CommandAction[];
  data?: Record<string, unknown>;
}

export interface ChatMessage {
  role: "user" | "ares";
  text: string;
  at: number;
  analysis?: Analysis;
}

export interface CalendarEvent {
  id: number;
  title: string;
  currency: string;
  impact: string;
  scheduled_at: string;
  previous: string | null;
  forecast: string | null;
  actual: string | null;
}

export interface JournalEntry extends Trade {
  trade_id: string;
  result: string;
  market_conditions: Record<string, string> | null;
  notes: string | null;
}

export type Section =
  | "command" | "markets" | "chart" | "scanner" | "positions"
  | "journal" | "analytics" | "news" | "settings";
