import { create } from "zustand";
import { api } from "./lib/api";
import type {
  AccountSnapshot, AlertEvent, Analysis, ChatMessage, CommandAction,
  CommandResponse, Section, StatusMap, TakeoverSession, Tick,
} from "./lib/types";

interface AresState {
  theme: "dark" | "light";
  section: Section;
  symbol: string;
  timeframe: string;
  ticks: Record<string, Tick>;
  status: StatusMap | null;
  overall: string;
  account: AccountSnapshot | null;
  alerts: AlertEvent[];
  chat: ChatMessage[];
  analysis: Analysis | null;
  takeover: TakeoverSession | null;
  favorites: string[];
  wsConnected: boolean;
  commandBusy: boolean;
  selectedArticle: string | null;
  newsCategory: string;

  setTheme: (t: "dark" | "light") => void;
  setSection: (s: Section) => void;
  setSymbol: (s: string) => void;
  setTimeframe: (tf: string) => void;
  applyTicks: (ticks: Tick[]) => void;
  pushAlert: (a: AlertEvent) => void;
  setAccount: (a: AccountSnapshot) => void;
  setWsConnected: (b: boolean) => void;
  toggleFavorite: (s: string) => void;
  openArticle: (id: string | null) => void;
  setNewsCategory: (category: string) => void;
  analyzeSymbol: (symbol: string) => Promise<void>;
  refreshStatus: () => Promise<void>;
  refreshTakeover: () => Promise<void>;
  sendCommand: (message: string) => Promise<void>;
  applyActions: (actions?: CommandAction[]) => void;
}

function readStoredFavorites(): string[] {
  // Corrupt localStorage must never white-screen the app at module load.
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem("ares.favorites") ?? "null");
    if (Array.isArray(parsed) && parsed.every((v) => typeof v === "string")) return parsed;
  } catch { /* fall through to defaults */ }
  return ["EURUSD", "XAUUSD", "GBPUSD"];
}

const storedTheme = (localStorage.getItem("ares.theme") as "dark" | "light") || "dark";
const storedFavs: string[] = readStoredFavorites();

export const useAres = create<AresState>((set, get) => ({
  theme: storedTheme,
  section: "command",
  symbol: localStorage.getItem("ares.symbol") || "EURUSD",
  timeframe: localStorage.getItem("ares.timeframe") || "M15",
  ticks: {},
  status: null,
  overall: "OFFLINE",
  account: null,
  alerts: [],
  chat: [],
  analysis: null,
  takeover: null,
  favorites: storedFavs,
  wsConnected: false,
  commandBusy: false,
  selectedArticle: null,
  newsCategory: "ALL",

  setTheme: (theme) => {
    localStorage.setItem("ares.theme", theme);
    // Dark is the base palette on :root; light is an explicit override class.
    document.documentElement.classList.toggle("light", theme === "light");
    set({ theme });
  },
  setSection: (section) => set({ section }),
  setSymbol: (symbol) => {
    localStorage.setItem("ares.symbol", symbol);
    set({ symbol });
  },
  setTimeframe: (timeframe) => {
    localStorage.setItem("ares.timeframe", timeframe);
    set({ timeframe });
  },
  applyTicks: (incoming) =>
    set((state) => {
      const ticks = { ...state.ticks };
      for (const t of incoming) ticks[t.symbol] = t;
      return { ticks };
    }),
  pushAlert: (a) =>
    set((state) => ({ alerts: [a, ...state.alerts].slice(0, 100) })),
  setAccount: (account) => set({ account }),
  setWsConnected: (wsConnected) => set({ wsConnected }),
  toggleFavorite: (symbol) =>
    set((state) => {
      const favorites = state.favorites.includes(symbol)
        ? state.favorites.filter((f) => f !== symbol)
        : [...state.favorites, symbol];
      localStorage.setItem("ares.favorites", JSON.stringify(favorites));
      return { favorites };
    }),

  openArticle: (id) => set({ selectedArticle: id, section: "news" }),
  setNewsCategory: (newsCategory) => set({ newsCategory, selectedArticle: null }),

  /** News → market connection: jump from a story straight into the
      instrument's analysis workspace. */
  analyzeSymbol: async (symbol) => {
    get().setSymbol(symbol);
    set({ section: "analysis", selectedArticle: null });
    await get().sendCommand(`Analyze ${symbol}`);
  },

  refreshStatus: async () => {
    try {
      const data = await api.get<{ components: StatusMap; overall: string }>("/api/status");
      set({ status: data.components, overall: data.overall });
    } catch {
      set({ status: null, overall: "OFFLINE" });
    }
  },

  refreshTakeover: async () => {
    try {
      const data = await api.get<{ session: TakeoverSession | null }>("/api/takeover");
      set({ takeover: data.session });
    } catch { /* backend unreachable */ }
  },

  applyActions: (actions) => {
    if (!actions) return;
    for (const a of actions) {
      if (a.type === "set_symbol" && a.symbol) get().setSymbol(a.symbol);
      if (a.type === "set_timeframe" && a.timeframe) get().setTimeframe(a.timeframe);
      if (a.type === "open_section" && a.section) {
        // Backend action names map onto the current section layout; the
        // scanner now lives inside the Analysis workspace.
        const map: Record<string, Section> = {
          scanner: "analysis", analysis: "analysis", positions: "positions",
          chart: "chart", news: "news", markets: "markets",
          journal: "journal", risk: "risk", settings: "settings",
        };
        if (map[a.section]) set({ section: map[a.section] });
      }
      if (a.type === "takeover_requested") void get().refreshTakeover();
    }
  },

  sendCommand: async (message) => {
    const trimmed = message.trim();
    if (!trimmed || get().commandBusy) return;
    set((s) => ({
      chat: [...s.chat, { role: "user", text: trimmed, at: Date.now() }],
      commandBusy: true,
    }));
    try {
      const resp = await api.post<CommandResponse>("/api/command", { message: trimmed });
      set((s) => ({
        chat: [...s.chat, { role: "ares", text: resp.reply, at: Date.now(), analysis: resp.analysis }],
        analysis: resp.analysis ?? s.analysis,
      }));
      get().applyActions(resp.actions);
    } catch (err) {
      set((s) => ({
        chat: [...s.chat, {
          role: "ares",
          text: `Backend unreachable (${err instanceof Error ? err.message : "error"}). Is the ARES backend running on port 8000?`,
          at: Date.now(),
        }],
      }));
    } finally {
      set({ commandBusy: false });
    }
  },
}));

// Apply the persisted theme before first paint.
document.documentElement.classList.toggle("light", storedTheme === "light");
