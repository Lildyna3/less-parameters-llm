import { useState } from "react";
import PriceChart from "../components/PriceChart";
import { api } from "../lib/api";
import { useAres } from "../store";
import { PanelTitle } from "../components/ui";

interface OrderResult { success: boolean; message: string; risk?: { reasons: string[] } | null }

function OrderTicket() {
  const { symbol, ticks } = useAres();
  const tick = ticks[symbol];
  const [volume, setVolume] = useState("0.10");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (direction: "buy" | "sell") => {
    setBusy(true);
    setResult(null);
    try {
      const resp = await api.post<OrderResult>("/api/order/demo", {
        symbol, direction, volume: parseFloat(volume) || 0,
        sl: sl ? parseFloat(sl) : null, tp: tp ? parseFloat(tp) : null,
        strategy: "manual",
      });
      setResult(resp.success ? `✓ ${resp.message}` :
        `✗ ${resp.message}${resp.risk?.reasons?.length ? ` — ${resp.risk.reasons.join("; ")}` : ""}`);
    } catch (err) {
      setResult(`✗ ${err instanceof Error ? err.message : "failed"}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <PanelTitle right={<span className="chip">PAPER ONLY</span>}>Demo Order · {symbol}</PanelTitle>
      <div className="space-y-2.5 p-3.5">
        <div className="grid grid-cols-3 gap-2">
          <label className="block">
            <span className="text-[10.5px] font-semibold uppercase text-faint">Lots</span>
            <input value={volume} onChange={(e) => setVolume(e.target.value)}
              className="mt-0.5 w-full rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] num outline-none focus:border-accent/60" />
          </label>
          <label className="block">
            <span className="text-[10.5px] font-semibold uppercase text-faint">SL</span>
            <input value={sl} onChange={(e) => setSl(e.target.value)} placeholder="optional"
              className="mt-0.5 w-full rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] num outline-none focus:border-accent/60" />
          </label>
          <label className="block">
            <span className="text-[10.5px] font-semibold uppercase text-faint">TP</span>
            <input value={tp} onChange={(e) => setTp(e.target.value)} placeholder="optional"
              className="mt-0.5 w-full rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] num outline-none focus:border-accent/60" />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button disabled={busy || !tick} onClick={() => void submit("sell")}
            className="rounded-lg bg-bear/12 py-2 text-[12px] font-bold text-bear hover:bg-bear/20 disabled:opacity-40">
            SELL {tick ? tick.bid : "—"}
          </button>
          <button disabled={busy || !tick} onClick={() => void submit("buy")}
            className="rounded-lg bg-bull/12 py-2 text-[12px] font-bold text-bull hover:bg-bull/20 disabled:opacity-40">
            BUY {tick ? tick.ask : "—"}
          </button>
        </div>
        {!tick && <div className="text-[11px] text-offline">DATA SOURCE OFFLINE — orders disabled.</div>}
        {result && <div className={`text-[11.5px] ${result.startsWith("✓") ? "text-bull" : "text-bear"}`}>{result}</div>}
      </div>
    </div>
  );
}

export default function ChartSection() {
  const { analysis, symbol, sendCommand } = useAres();
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 p-3 lg:grid-cols-[1fr_300px]">
      <div className="panel min-h-[320px] overflow-hidden">
        <PriceChart />
      </div>
      <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
        <OrderTicket />
        <div className="panel">
          <PanelTitle>Quick analysis</PanelTitle>
          <div className="p-3.5">
            <button onClick={() => void sendCommand(`Analyze ${symbol}`)}
              className="w-full rounded-lg bg-accent/12 py-2 text-[12px] font-bold text-accent hover:bg-accent/20">
              Analyze {symbol}
            </button>
            {analysis && analysis.symbol === symbol && (
              <div className="mt-2 text-[11.5px] text-dim">
                {analysis.bias} · confidence {analysis.confidence}/5 — full briefing in the Command Center.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
