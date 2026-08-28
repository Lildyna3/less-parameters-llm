import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TakeoverPanel from "../components/TakeoverPanel";
import ExecutionTicket from "../components/ExecutionTicket";
import { Confidence, Impact, Unavailable, ago, duration, price, signed } from "../components/kit";
import { takeoverSession } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok, status, statusText: ok ? "OK" : "Error",
    json: () => Promise.resolve(body),
  });
}

describe("kit formatting", () => {
  it("signed() carries sign and tone", () => {
    expect(signed(12.5)).toEqual({ text: "+12.50", tone: "bull" });
    expect(signed(-3.2)).toEqual({ text: "-3.20", tone: "bear" });
    expect(signed(null)).toEqual({ text: "—", tone: "dim" });
    expect(signed(Number.NaN).text).toBe("—");
  });

  it("price() adapts precision to magnitude", () => {
    expect(price(1.08481)).toBe("1.08481");
    expect(price(148.512)).toBe("148.512");
    expect(price(2350.531)).toBe("2350.53");
    expect(price(null)).toBe("—");
  });

  it("ago() renders a relative age", () => {
    const now = new Date().toISOString();
    expect(ago(now)).toMatch(/s ago$/);
    const hourAgo = new Date(Date.now() - 3_600_000).toISOString();
    expect(ago(hourAgo)).toBe("1h ago");
    expect(ago("not-a-date")).toBe("");
  });

  it("duration() renders how long a position has been held", () => {
    const start = new Date(Date.now() - 90 * 60_000).toISOString();
    expect(duration(start)).toBe("1h 30m");
    expect(duration("bad")).toBe("—");
  });
});

describe("kit components", () => {
  it("Confidence shows the score out of five", () => {
    render(<Confidence score={4} />);
    expect(screen.getByText("4/5")).toBeInTheDocument();
  });

  it("Impact renders the level verbatim", () => {
    render(<Impact level="CRITICAL" />);
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
  });

  it("Unavailable states what is missing and why, instead of a placeholder value", () => {
    render(<Unavailable what="News" reason="No source could be reached." />);
    expect(screen.getByText(/News unavailable/i)).toBeInTheDocument();
    expect(screen.getByText("No source could be reached.")).toBeInTheDocument();
  });
});

describe("TakeoverPanel", () => {
  it("shows a requested session with an explicit Authorize control", async () => {
    vi.stubGlobal("fetch", jsonResponse({ session: takeoverSession }));
    render(<TakeoverPanel />);
    await waitFor(() => expect(screen.getByText("XAUUSD")).toBeInTheDocument());
    expect(screen.getByText("REQUESTED")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Authorize" })).toBeInTheDocument();
    // Limits are always visible before authorizing.
    expect(screen.getByText("Max loss")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
  });

  it("offers no Authorize control when there is no session", async () => {
    vi.stubGlobal("fetch", jsonResponse({ session: null }));
    render(<TakeoverPanel />);
    await waitFor(() => expect(screen.getByText(/No session/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Authorize" })).toBeNull();
  });

  it("an active session can be stopped but not re-authorized", async () => {
    vi.stubGlobal("fetch", jsonResponse({
      session: { ...takeoverSession, state: "ACTIVE", basket_id: "ARES-100" },
    }));
    render(<TakeoverPanel />);
    await waitFor(() => expect(screen.getByText("ACTIVE")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Authorize" })).toBeNull();
    expect(screen.getByRole("button", { name: "Stop now" })).toBeInTheDocument();
  });
});

describe("ExecutionTicket", () => {
  const blocked = {
    ready: false, verdict: "BLOCKED",
    items: [
      { name: "MT5 connection", ok: false, detail: "MT5 is not connected." },
      { name: "Direction", ok: true, detail: "buy" },
    ],
    blocked_by: ["MT5 connection"],
    plan: {},
  };
  const ready = {
    ready: true, verdict: "READY",
    items: [{ name: "MT5 connection", ok: true, detail: "connected to a DEMO account" }],
    blocked_by: [],
    plan: {
      symbol: "EURUSD", direction: "buy", volume: 0.01, entry: 1.08481,
      sl: null, tp: null, risk_reward: null, margin_required: 3.61,
      account_mode: "DEMO", broker: "Demo Broker", server: "Demo-Server",
    },
  };

  /* The ticket polls /api/mt5/positions and /api/mt5/history on mount, so the
     stub answers by path rather than returning one fixed body. */
  function routedFetch(check: unknown, order?: unknown) {
    const calls: string[] = [];
    const fn = vi.fn().mockImplementation((url: string) => {
      calls.push(url);
      const body =
        url.includes("/order/check") ? check
        : url.includes("/api/mt5/order") ? order
        : url.includes("/positions") ? { positions: [], message: "MT5 is not connected." }
        : { deals: [] };
      return Promise.resolve({ ok: true, status: 200, statusText: "OK",
                               json: () => Promise.resolve(body) });
    });
    return { fn, calls };
  }

  it("will not arm an order until the pre-trade check comes back READY", async () => {
    const { fn, calls } = routedFetch(blocked);
    vi.stubGlobal("fetch", fn);
    render(<ExecutionTicket />);

    const place = screen.getByRole("button", { name: "Place order" });
    expect(place).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Run pre-trade check" }));
    await waitFor(() => expect(screen.getByText("BLOCKED")).toBeInTheDocument());
    expect(screen.getByText("MT5 is not connected.")).toBeInTheDocument();
    // Still disabled, and nothing was ever posted to the order endpoint.
    expect(screen.getByRole("button", { name: "Place order" })).toBeDisabled();
    expect(calls.some((u) => u.endsWith("/api/mt5/order"))).toBe(false);
  });

  it("a READY check arms a confirmation, and only the confirmation sends", async () => {
    const { fn, calls } = routedFetch(ready, {
      success: true, message: "Order filled.", retcode: 10009, ticket: 5551234,
      broker_comment: null, position: null, check: null,
    });
    vi.stubGlobal("fetch", fn);
    render(<ExecutionTicket />);

    fireEvent.click(screen.getByRole("button", { name: "Run pre-trade check" }));
    await waitFor(() => expect(screen.getByText("READY")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Place order" }));
    // Arming alone must not reach the broker.
    expect(calls.some((u) => u.endsWith("/api/mt5/order"))).toBe(false);

    fireEvent.click(await screen.findByRole("button", { name: /^Confirm BUY/ }));
    await waitFor(() => expect(screen.getByText("FILLED BY MT5")).toBeInTheDocument());
    expect(calls.filter((u) => u.endsWith("/api/mt5/order"))).toHaveLength(1);
    expect(screen.getByText(/5551234/)).toBeInTheDocument();
  });

  it("reports a broker rejection as NOT EXECUTED with its retcode", async () => {
    const { fn } = routedFetch(ready, {
      success: false, message: "MT5 rejected the order.", retcode: 10018,
      ticket: null, broker_comment: "Market closed", position: null, check: null,
    });
    vi.stubGlobal("fetch", fn);
    render(<ExecutionTicket />);

    fireEvent.click(screen.getByRole("button", { name: "Run pre-trade check" }));
    await waitFor(() => expect(screen.getByText("READY")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Place order" }));
    fireEvent.click(await screen.findByRole("button", { name: /^Confirm BUY/ }));

    await waitFor(() => expect(screen.getByText("NOT EXECUTED")).toBeInTheDocument());
    expect(screen.getByText(/retcode 10018/)).toBeInTheDocument();
    expect(screen.queryByText("FILLED BY MT5")).toBeNull();
  });

  it("editing the ticket after a READY check disarms it", async () => {
    const { fn } = routedFetch(ready);
    vi.stubGlobal("fetch", fn);
    render(<ExecutionTicket />);

    fireEvent.click(screen.getByRole("button", { name: "Run pre-trade check" }));
    await waitFor(() => expect(screen.getByText("READY")).toBeInTheDocument());

    // A check describes one specific order; changing the size invalidates it.
    fireEvent.change(screen.getByLabelText("Volume (lots)"), { target: { value: "5.00" } });
    await waitFor(() => expect(screen.queryByText("READY")).toBeNull());
    expect(screen.getByRole("button", { name: "Place order" })).toBeDisabled();
  });
});
