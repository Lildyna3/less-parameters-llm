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

export interface JournalEntry {
  id: number; // database id (used for notes updates)
  trade_id: string;
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
  result: string;
  market_conditions: Record<string, string> | null;
  notes: string | null;
}

export interface SymbolInfo {
  name: string;
  description: string;
  digits: number;
}

export type Section =
  | "command" | "markets" | "chart" | "news" | "positions"
  | "risk" | "analysis" | "journal" | "settings";

export interface NewsArticle {
  id: string;
  title: string;
  summary: string;
  source: string;
  source_id: string;
  url: string | null;
  published_at: string;
  categories: string[];
  symbols: string[];
  currencies: string[];
  impact: "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
  ares_impact: string;
  ares_interpretation: string;
  direction: string;
}

export interface NewsSourceStatus {
  id: string;
  name: string;
  ok: boolean;
  articles: number;
  error: string | null;
  last_attempt: string | null;
  last_success: string | null;
}

export interface NewsResponse {
  articles: NewsArticle[];
  categories: string[];
  status: {
    sources: NewsSourceStatus[];
    article_count: number;
    last_refresh: string | null;
    enabled: boolean;
  };
  message: string | null;
}

export interface MarketPulse {
  regime: string | null;
  volatility: string | null;
  sessions: {
    utc_time: string;
    fx_market_open: boolean;
    active_sessions: string[];
    overlap: string | null;
  };
  movers: Tick[];
  strongest_setups: ScanRow[];
  scanned_at: boolean;
  upcoming_events: CalendarEvent[];
  data_source: string | null;
  quotes_live: number;
  account: AccountSnapshot;
  risk: RiskSnapshot;
  news_headlines: NewsArticle[];
}

export interface RiskSnapshot {
  emergency_stop: boolean;
  daily_pl: number;
  session_trades: number;
  cooldown_active: boolean;
  blocks_issued: number;
  limits: Record<string, number | boolean>;
}

export interface BridgeStatus {
  mode: string;
  attached: boolean;
  connected: boolean;
  state: string;
  bridge: {
    bridge_version: string;
    host: string;
    platform: string;
    mt5_package: boolean;
    terminal_connected: boolean;
    terminal_path: string | null;
    broker: string | null;
    server: string | null;
    mt5_state: string;
    detail: string;
  };
  account: {
    login_masked: string; broker: string; server: string; currency: string;
    balance: number; equity: number; is_demo: boolean; trade_allowed: boolean;
  } | null;
  last_error: string | null;
  connected_since: string | null;
  token_configured: boolean;
  verified_real_terminal: boolean;
  chain: ChainLink[];
  access_mode: string;
  instructions: string;
}

/** One link in the path from this backend to the broker. Reported separately
    so "connected" can never mean four different things at once. */
export interface ChainLink {
  id: "backend" | "bridge" | "terminal" | "broker";
  label: string;
  state: "ONLINE" | "OFFLINE" | "DEGRADED" | "UNKNOWN" | "UNVERIFIED";
  detail: string;
}
