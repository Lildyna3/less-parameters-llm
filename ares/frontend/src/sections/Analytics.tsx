import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AccountSnapshot } from "../lib/types";
import { Empty, PanelTitle, Stat, pl } from "../components/ui";

interface AnalyticsData {
  account: AccountSnapshot;
  ares: {
    analyses_performed: number;
    risk_blocks: number;
    confidence_distribution: Record<string, number>;
    successful_setups: number;
    failed_setups: number;
  };
}

export default function Analytics() {
  const [data, setData] = useState<AnalyticsData | null>(null);

  useEffect(() => {
    const load = () => void api.get<AnalyticsData>("/api/analytics").then(setData).catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (!data) {
    return <div className="p-3"><div className="panel"><Empty>Analytics unavailable — backend offline.</Empty></div></div>;
  }

  const { account, ares } = data;
  const daily = pl(account.daily_pl);
  const floating = pl(account.floating_pl);
  const maxDist = Math.max(1, ...Object.values(ares.confidence_distribution));

  return (
    <div className="h-full space-y-3 overflow-y-auto p-3">
      <div className="panel mx-auto max-w-4xl">
        <PanelTitle right={<span className="chip">PAPER</span>}>Account</PanelTitle>
        <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
          <Stat label="Balance" value={account.balance.toFixed(2)} sub={account.currency} />
          <Stat label="Equity" value={account.equity.toFixed(2)} />
          <Stat label="Floating P/L" value={floating.text} tone={floating.tone} />
          <Stat label="Daily P/L" value={daily.text} tone={daily.tone} />
          <Stat label="Drawdown" value={`${account.drawdown_percent}%`} />
          <Stat label="Open positions" value={account.open_positions} />
          <Stat label="Exposure" value={`${account.exposure_lots} lots`} />
          <Stat label="Trades closed" value={account.trades_closed} />
        </div>
      </div>

      <div className="panel mx-auto max-w-4xl">
        <PanelTitle>Trading Performance</PanelTitle>
        <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
          <Stat label="Win rate" value={account.win_rate != null ? `${account.win_rate}%` : "—"} />
          <Stat label="Average R" value={account.average_r ?? "—"} />
          <Stat label="Profit factor" value={account.profit_factor ?? "—"} />
          <Stat label="Risk blocks" value={ares.risk_blocks} />
        </div>
      </div>

      <div className="panel mx-auto max-w-4xl">
        <PanelTitle>ARES Intelligence</PanelTitle>
        <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
          <Stat label="Analyses" value={ares.analyses_performed} />
          <Stat label="4/5+ wins" value={ares.successful_setups} tone="bull" />
          <Stat label="4/5+ losses" value={ares.failed_setups} tone="bear" />
          <div>
            <div className="text-[10.5px] font-semibold uppercase tracking-wider text-faint">Confidence dist.</div>
            <div className="mt-1.5 flex items-end gap-1">
              {[1, 2, 3, 4, 5].map((c) => {
                const count = ares.confidence_distribution[String(c)] ?? 0;
                return (
                  <div key={c} className="flex flex-col items-center gap-0.5">
                    <div className="w-5 rounded-sm bg-accent/40"
                      style={{ height: `${6 + (count / maxDist) * 34}px` }}
                      title={`${count} trade(s) at ${c}/5`} />
                    <span className="text-[9px] num text-faint">{c}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
