import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { JournalEntry } from "../lib/types";
import { Empty, PanelTitle, pl } from "../components/ui";

interface Coach {
  trades_analyzed: number;
  message: string;
  observations: { pattern: string; evidence: string; advice: string }[];
}

export default function Journal() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [coach, setCoach] = useState<Coach | null>(null);

  const load = () => {
    void api.get<{ entries: JournalEntry[] }>("/api/journal").then((d) => setEntries(d.entries)).catch(() => {});
    void api.get<Coach>("/api/coach").then(setCoach).catch(() => {});
  };

  useEffect(load, []);

  const editNotes = async (entry: JournalEntry) => {
    const notes = window.prompt(`Notes for ${entry.symbol} ${entry.direction} (${entry.trade_id}):`, entry.notes ?? "");
    if (notes === null) return;
    try {
      await api.patch(`/api/journal/${entry.id}/notes`, { notes });
      load();
    } catch { /* backend offline; entry unchanged */ }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 overflow-y-auto p-3 lg:grid-cols-[1fr_320px]">
      <div className="panel">
        <PanelTitle>Trade Journal</PanelTitle>
        {entries.length === 0 ? <Empty>No recorded trades yet. Closed paper trades land here automatically.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-line text-left text-[10.5px] uppercase tracking-wider text-faint">
                  <th className="px-3.5 py-2">Closed</th><th className="px-2 py-2">Symbol</th>
                  <th className="px-2 py-2">Dir</th><th className="px-2 py-2 text-right">Entry</th>
                  <th className="px-2 py-2 text-right">Exit</th><th className="px-2 py-2 text-right">P/L</th>
                  <th className="px-2 py-2">Result</th><th className="px-2 py-2">Reason</th>
                  <th className="px-2 py-2">Strategy</th><th className="px-2 py-2">Conf</th>
                  <th className="px-2 py-2">Notes</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => {
                  const t = pl(e.pl);
                  return (
                    <tr key={e.trade_id + e.closed_at} className="border-b border-line/50 last:border-0">
                      <td className="px-3.5 py-2 num text-faint">{e.closed_at.replace("T", " ").slice(5, 16)}</td>
                      <td className="px-2 py-2 font-semibold num">{e.symbol}</td>
                      <td className={`px-2 py-2 font-bold ${e.direction === "buy" ? "text-bull" : "text-bear"}`}>{e.direction.toUpperCase()}</td>
                      <td className="px-2 py-2 text-right num">{e.entry}</td>
                      <td className="px-2 py-2 text-right num">{e.exit}</td>
                      <td className={`px-2 py-2 text-right num font-bold text-${t.tone === "dim" ? "faint" : t.tone}`}>{t.text}</td>
                      <td className="px-2 py-2">
                        <span className={`chip ${e.result === "win" ? "!text-bull" : e.result === "loss" ? "!text-bear" : ""}`}>{e.result}</span>
                      </td>
                      <td className="px-2 py-2 text-faint">{e.close_reason}</td>
                      <td className="px-2 py-2 text-faint">{e.strategy ?? "—"}</td>
                      <td className="px-2 py-2 num text-faint">{e.confidence ? `${e.confidence}/5` : "—"}</td>
                      <td className="max-w-[160px] px-2 py-2">
                        <button onClick={() => void editNotes(e)}
                          title={e.notes ?? "Add notes"}
                          className="block max-w-full truncate text-left text-[11px] text-faint hover:text-accent">
                          {e.notes ? e.notes : "✎ add"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel h-fit">
        <PanelTitle>ARES Coach</PanelTitle>
        <div className="space-y-2.5 p-3.5 text-[12px]">
          {coach ? (
            <>
              <div className="text-dim">{coach.message}</div>
              {coach.observations.map((o, i) => (
                <div key={i} className="rounded-lg border border-line bg-inset/60 px-2.5 py-2">
                  <div className="text-[11px] font-bold uppercase tracking-wide text-warn">{o.pattern}</div>
                  <div className="mt-0.5 text-[11px] text-faint">{o.evidence}</div>
                  <div className="mt-1 text-[11.5px] text-dim">{o.advice}</div>
                </div>
              ))}
            </>
          ) : <Empty>Coach unavailable.</Empty>}
        </div>
      </div>
    </div>
  );
}
