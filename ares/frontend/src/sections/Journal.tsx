import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AccountSnapshot, JournalEntry } from "../lib/types";
import { Empty, Metric, PanelHeader, Tag, signed } from "../components/kit";

/* Journal: the record, the performance figures derived from it, and coaching
   that only ever cites recorded behaviour. */

interface Coach {
  trades_analyzed: number;
  message: string;
  observations: { pattern: string; evidence: string; advice: string }[];
}

interface Analytics {
  account: AccountSnapshot;
  ares: {
    analyses_performed: number;
    risk_blocks: number;
    confidence_distribution: Record<string, number>;
    successful_setups: number;
    failed_setups: number;
  };
}

export default function Journal() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [coach, setCoach] = useState<Coach | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  const load = () => {
    void api.get<{ entries: JournalEntry[] }>("/api/journal")
      .then((data) => setEntries(data.entries)).catch(() => {});
    void api.get<Coach>("/api/coach").then(setCoach).catch(() => {});
    void api.get<Analytics>("/api/analytics").then(setAnalytics).catch(() => {});
  };

  useEffect(load, []);

  const editNotes = async (entry: JournalEntry) => {
    const notes = window.prompt(
      `Notes — ${entry.symbol} ${entry.direction} (${entry.trade_id})`, entry.notes ?? "");
    if (notes === null) return;
    try {
      await api.patch(`/api/journal/${entry.id}/notes`, { notes });
      load();
    } catch { /* backend offline; the entry is unchanged */ }
  };

  const distribution = analytics?.ares.confidence_distribution ?? {};
  const peak = Math.max(1, ...Object.values(distribution));

  return (
    <div className="scroll-y h-full">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-4 p-4 pb-6">
        {analytics && (
          <section className="panel">
            <PanelHeader right={<Tag>{analytics.account.mode}</Tag>}>Performance</PanelHeader>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 p-4 sm:grid-cols-3 lg:grid-cols-6">
              <Metric label="Win rate"
                      value={analytics.account.win_rate != null ? `${analytics.account.win_rate}%` : "—"} large />
              <Metric label="Average R" value={analytics.account.average_r ?? "—"} />
              <Metric label="Profit factor" value={analytics.account.profit_factor ?? "—"} />
              <Metric label="Trades" value={analytics.account.trades_closed} />
              <Metric label="Analyses" value={analytics.ares.analyses_performed} />
              <div>
                <div className="label">Confidence taken</div>
                <div className="mt-2 flex items-end gap-1">
                  {[1, 2, 3, 4, 5].map((score) => {
                    const count = distribution[String(score)] ?? 0;
                    return (
                      <div key={score} className="flex flex-col items-center gap-1"
                           title={`${count} trade(s) at ${score}/5`}>
                        <div className="w-4 rounded-sm bg-accent/45"
                             style={{ height: `${5 + (count / peak) * 26}px` }} />
                        <span className="num text-[9px] text-faint">{score}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 border-t border-line px-4 py-2.5 text-[11.5px] text-faint">
              <span>High-conviction wins: <span className="text-bull">{analytics.ares.successful_setups}</span></span>
              <span>High-conviction losses: <span className="text-bear">{analytics.ares.failed_setups}</span></span>
              <span>Orders blocked by risk: <span className="text-ink">{analytics.ares.risk_blocks}</span></span>
            </div>
          </section>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
          <section className="panel">
            <PanelHeader right={<Tag>{entries.length} recorded</Tag>}>Trade Journal</PanelHeader>
            {entries.length === 0 ? (
              <Empty>No recorded trades yet. Closed paper trades are journaled automatically.</Empty>
            ) : (
              <div className="scroll-x">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Closed</th><th>Instrument</th><th>Side</th>
                      <th className="text-right">Entry</th><th className="text-right">Exit</th>
                      <th className="text-right">P/L</th><th>Result</th>
                      <th>Reason</th><th>Conf</th><th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry) => {
                      const pl = signed(entry.pl);
                      return (
                        <tr key={entry.id}>
                          <td className="num text-faint">
                            {entry.closed_at.slice(5, 16).replace("T", " ")}
                          </td>
                          <td className="num font-semibold">{entry.symbol}</td>
                          <td className={entry.direction === "buy" ? "text-bull" : "text-bear"}>
                            {entry.direction.toUpperCase()}
                          </td>
                          <td className="num text-right">{entry.entry}</td>
                          <td className="num text-right">{entry.exit}</td>
                          <td className={`num text-right font-semibold ${
                            pl.tone === "bull" ? "text-bull" : pl.tone === "bear" ? "text-bear" : "text-faint"}`}>
                            {pl.text}
                          </td>
                          <td>
                            <Tag tone={entry.result === "win" ? "bull" : entry.result === "loss" ? "bear" : "muted"}>
                              {entry.result}
                            </Tag>
                          </td>
                          <td className="text-faint">{entry.close_reason}</td>
                          <td className="num text-faint">{entry.confidence ? `${entry.confidence}/5` : "—"}</td>
                          <td className="max-w-[150px]">
                            <button
                              onClick={() => void editNotes(entry)}
                              title={entry.notes ?? "Add notes"}
                              className="block max-w-full truncate text-left text-[11px] text-faint hover:text-accent"
                            >
                              {entry.notes ? entry.notes : "add"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel h-fit">
            <PanelHeader>ARES Coaching</PanelHeader>
            <div className="space-y-2.5 p-4">
              {coach ? (
                <>
                  <p className="text-[12px] leading-relaxed text-dim">{coach.message}</p>
                  {coach.observations.map((observation, index) => (
                    <div key={index} className="rounded-md border border-line bg-s2 p-3">
                      <div className="label !text-warn">{observation.pattern}</div>
                      <p className="mt-1 text-[10.5px] text-faint">{observation.evidence}</p>
                      <p className="mt-1.5 text-[11.5px] leading-relaxed text-dim">{observation.advice}</p>
                    </div>
                  ))}
                  <p className="text-[10.5px] leading-relaxed text-faint">
                    Coaching cites only your recorded trades — never assumed psychology.
                  </p>
                </>
              ) : (
                <Empty>Coaching unavailable.</Empty>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
