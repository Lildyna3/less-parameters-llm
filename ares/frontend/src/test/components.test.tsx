import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TakeoverPanel from "../components/TakeoverPanel";
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
