import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAres } from "../store";
import { tick } from "./fixtures";

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok, status, statusText: ok ? "OK" : "Error",
    json: () => Promise.resolve(body),
  });
}

describe("ARES store", () => {
  beforeEach(() => {
    useAres.setState({
      chat: [], ticks: {}, alerts: [], analysis: null,
      symbol: "EURUSD", timeframe: "M15", section: "command",
      favorites: ["EURUSD"], commandBusy: false,
    });
  });

  it("applies incoming ticks by symbol", () => {
    useAres.getState().applyTicks([tick("EURUSD"), tick("XAUUSD", 2350, 2350.2)]);
    const state = useAres.getState();
    expect(state.ticks.EURUSD.bid).toBe(1.1);
    expect(state.ticks.XAUUSD.ask).toBe(2350.2);
  });

  it("persists theme, symbol, and timeframe choices", () => {
    useAres.getState().setTheme("light");
    expect(localStorage.getItem("ares.theme")).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    useAres.getState().setTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    useAres.getState().setSymbol("GBPJPY");
    expect(localStorage.getItem("ares.symbol")).toBe("GBPJPY");
    useAres.getState().setTimeframe("H1");
    expect(localStorage.getItem("ares.timeframe")).toBe("H1");
  });

  it("toggles favorites and persists them", () => {
    useAres.getState().toggleFavorite("XAUUSD");
    expect(useAres.getState().favorites).toContain("XAUUSD");
    useAres.getState().toggleFavorite("XAUUSD");
    expect(useAres.getState().favorites).not.toContain("XAUUSD");
    expect(JSON.parse(localStorage.getItem("ares.favorites")!)).toEqual(useAres.getState().favorites);
  });

  it("applies command actions: symbol, timeframe, section", () => {
    useAres.getState().applyActions([
      { type: "set_symbol", symbol: "XAUUSD" },
      { type: "set_timeframe", timeframe: "H4" },
      { type: "open_section", section: "scanner" },
    ]);
    const state = useAres.getState();
    expect(state.symbol).toBe("XAUUSD");
    expect(state.timeframe).toBe("H4");
    expect(state.section).toBe("scanner");
  });

  it("sendCommand records user + ARES messages and applies actions", async () => {
    vi.stubGlobal("fetch", mockFetch({
      reply: "Opening XAUUSD.",
      actions: [{ type: "set_symbol", symbol: "XAUUSD" }],
    }));
    await useAres.getState().sendCommand("Open XAUUSD");
    const state = useAres.getState();
    expect(state.chat).toHaveLength(2);
    expect(state.chat[0]).toMatchObject({ role: "user", text: "Open XAUUSD" });
    expect(state.chat[1]).toMatchObject({ role: "ares", text: "Opening XAUUSD." });
    expect(state.symbol).toBe("XAUUSD");
    vi.unstubAllGlobals();
  });

  it("sendCommand reports backend failure honestly instead of pretending", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    await useAres.getState().sendCommand("Analyze EURUSD");
    const last = useAres.getState().chat.at(-1)!;
    expect(last.role).toBe("ares");
    expect(last.text).toContain("Backend unreachable");
    vi.unstubAllGlobals();
  });

  it("caps stored alerts at 100", () => {
    for (let i = 0; i < 120; i++) {
      useAres.getState().pushAlert({ id: i, kind: "price", severity: "info", message: `a${i}`, at: "" });
    }
    const alerts = useAres.getState().alerts;
    expect(alerts).toHaveLength(100);
    expect(alerts[0].id).toBe(119); // newest first
  });
});
