import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnalysisCard from "../components/AnalysisCard";
import TakeoverPanel from "../components/TakeoverPanel";
import { Confidence, fmtPrice, pl } from "../components/ui";
import { analysis, takeoverSession } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ui helpers", () => {
  it("pl() formats sign and tone", () => {
    expect(pl(12.5)).toEqual({ text: "+12.50", tone: "bull" });
    expect(pl(-3.2)).toEqual({ text: "-3.20", tone: "bear" });
    expect(pl(null)).toEqual({ text: "—", tone: "dim" });
  });

  it("fmtPrice() adapts digits to magnitude", () => {
    expect(fmtPrice(1.08481)).toBe("1.08481");
    expect(fmtPrice(2350.531)).toBe("2350.53");
    expect(fmtPrice(null)).toBe("—");
  });

  it("Confidence renders the score", () => {
    render(<Confidence score={4} />);
    expect(screen.getByText("4/5")).toBeInTheDocument();
  });
});

describe("AnalysisCard", () => {
  it("renders bias, confidence, levels, invalidation and SIMULATED label", () => {
    render(<AnalysisCard analysis={analysis} />);
    expect(screen.getByText("EURUSD")).toBeInTheDocument();
    expect(screen.getByText("BULLISH")).toBeInTheDocument();
    expect(screen.getByText("4/5")).toBeInTheDocument();
    expect(screen.getByText("SIMULATED")).toBeInTheDocument();
    expect(screen.getByText(/R 1.12/)).toBeInTheDocument();
    expect(screen.getByText(/Invalidation:/)).toBeInTheDocument();
  });

  it("reveals confidence factors on demand", async () => {
    const { getByText } = render(<AnalysisCard analysis={analysis} />);
    expect(screen.queryByText(/timeframes aligned bullish/)).toBeNull();
    getByText("Why this confidence?").click();
    await waitFor(() =>
      expect(screen.getByText(/timeframes aligned bullish/)).toBeInTheDocument());
  });
});

describe("TakeoverPanel", () => {
  it("shows the requested session with an explicit AUTHORIZE control", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: "OK",
      json: () => Promise.resolve({ session: takeoverSession }),
    }));
    render(<TakeoverPanel />);
    await waitFor(() => expect(screen.getByText("XAUUSD")).toBeInTheDocument());
    expect(screen.getByText("REQUESTED")).toBeInTheDocument();
    expect(screen.getByText("AUTHORIZE")).toBeInTheDocument();
    expect(screen.getByText("STOP / CANCEL")).toBeInTheDocument();
    expect(screen.getByText(/Max loss 150/)).toBeInTheDocument();
  });

  it("shows the empty state when no session exists", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: "OK",
      json: () => Promise.resolve({ session: null }),
    }));
    render(<TakeoverPanel />);
    await waitFor(() => expect(screen.getByText(/No takeover session/)).toBeInTheDocument());
    expect(screen.queryByText("AUTHORIZE")).toBeNull();
  });
});
