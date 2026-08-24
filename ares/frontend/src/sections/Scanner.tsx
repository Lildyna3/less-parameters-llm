import { useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { ScanRow } from "../lib/types";
import { BiasTag, Confidence, Empty, PanelTitle } from "../components/ui";

export default function Scanner() {
  const { setSymbol, setSection } = useAres();
  const [rows, setRows] = useState<ScanRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scan = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await api.get<{ results: ScanRow[] }>("/api/scanner");
      setRows(data.results);
      if (data.results.length === 0) setError("Scan returned nothing — DATA SOURCE OFFLINE.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="panel mx-auto max-w-4xl">
        <PanelTitle right={
          <button onClick={() => void scan()} disabled={busy}
            className="rounded-lg bg-accent/12 px-3 py-1 text-[11.5px] font-bold text-accent hover:bg-accent/20 disabled:opacity-40">
            {busy ? "Scanning…" : "Run scan"}
          </button>
        }>
          Market Scanner
        </PanelTitle>

        {error && <div className="px-3.5 py-2 text-[11.5px] text-warn">{error}</div>}
        {!rows && !error && <Empty>Rank the watched instruments by measurable evidence.</Empty>}

        {rows && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-line text-left text-[10.5px] uppercase tracking-wider text-faint">
                  <th className="px-3.5 py-2">Symbol</th>
                  <th className="px-2 py-2">Bias</th>
                  <th className="px-2 py-2">Setup</th>
                  <th className="px-2 py-2">Confidence</th>
                  <th className="px-2 py-2">Volatility</th>
                  <th className="px-2 py-2">Risk</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol}
                    className="cursor-pointer border-b border-line/50 last:border-0 hover:bg-inset/70"
                    onClick={() => { setSymbol(r.symbol); setSection("chart"); }}>
                    <td className="px-3.5 py-2.5 font-bold num">{r.symbol}</td>
                    <td className="px-2 py-2.5"><BiasTag bias={r.bias} /></td>
                    <td className="px-2 py-2.5 text-dim">{r.setup}</td>
                    <td className="px-2 py-2.5"><Confidence score={r.confidence} size="sm" /></td>
                    <td className="px-2 py-2.5 text-dim">{r.volatility}</td>
                    <td className={`px-2 py-2.5 ${r.risk === "elevated" ? "text-warn" : "text-dim"}`}>{r.risk}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
