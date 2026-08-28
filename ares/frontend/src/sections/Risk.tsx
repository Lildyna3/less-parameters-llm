import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AccountSnapshot, RiskSnapshot } from "../lib/types";
import { Metric, PanelHeader, Tag, Unavailable, signed } from "../components/kit";

/* Risk Command: how much room is left, in one screen. Utilisation bars are
   hairline-thin and only take colour as they approach a limit. */

function Utilisation({ label, used, limit, unit, invert }: {
  label: string; used: number; limit: number; unit?: string; invert?: boolean;
}) {
  const ratio = limit > 0 ? Math.min(1, Math.max(0, used / limit)) : 0;
  const pct = Math.round(ratio * 100);
  const tone = ratio >= 0.9 ? "bg-danger" : ratio >= 0.66 ? "bg-warn" : "bg-accent";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="label">{label}</span>
        <span className="num text-[11.5px] text-dim">
          {invert ? `${(limit - used).toFixed(2)} left` : `${used}${unit ?? ""} / ${limit}${unit ?? ""}`}
        </span>
      </div>
      <div className="mt-1.5 h-[3px] w-full overflow-hidden rounded-full bg-line-strong">
        <div className={`h-full rounded-full ${tone} transition-[width] duration-500`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function Risk() {
  const [risk, setRisk] = useState<RiskSnapshot | null>(null);
  const [account, setAccount] = useState<AccountSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [reachable, setReachable] = useState(true);

  const load = async () => {
    try {
      const [riskData, accountData] = await Promise.all([
        api.get<RiskSnapshot>("/api/risk"),
        api.get<{ paper: AccountSnapshot }>("/api/account"),
      ]);
      setRisk(riskData);
      setAccount(accountData.paper);
      setReachable(true);
    } catch {
      setReachable(false);
    }
  };

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, []);

  const engage = async () => {
    if (!window.confirm(
      "Engage the emergency stop?\n\nAll open paper positions close immediately and every "
      + "execution path is blocked until you release it."
    )) return;
    setBusy(true);
    await api.post("/api/risk/emergency-stop").catch(() => {});
    setBusy(false);
    void load();
  };

  const release = async () => {
    setBusy(true);
    await api.post("/api/risk/emergency-stop/release").catch(() => {});
    setBusy(false);
    void load();
  };

  if (!reachable || !risk || !account) {
    return (
      <div className="p-4">
        <section className="panel">
          <Unavailable what="Risk data" reason="The ARES backend is not reachable from this browser." />
        </section>
      </div>
    );
  }

  const limits = risk.limits as Record<string, number>;
  const daily = signed(risk.daily_pl);
  const dailyLossUsed = Math.max(0, -risk.daily_pl);

  return (
    <div className="scroll-y h-full">
      <div className="mx-auto flex max-w-[1100px] flex-col gap-4 p-4 pb-6">
        <section className={`panel ${risk.emergency_stop ? "!border-[color-mix(in_srgb,var(--danger)_45%,transparent)]" : ""}`}>
          <PanelHeader
            right={
              risk.emergency_stop
                ? <Tag tone="danger">EMERGENCY STOP ENGAGED</Tag>
                : <Tag tone={risk.cooldown_active ? "warn" : "muted"}>
                    {risk.cooldown_active ? "COOLDOWN ACTIVE" : "ARMED"}
                  </Tag>
            }
          >
            Risk Command
          </PanelHeader>

          <div className="grid grid-cols-2 gap-x-6 gap-y-5 p-4 sm:grid-cols-3 lg:grid-cols-5">
            <Metric label="Daily P/L" value={daily.text} tone={daily.tone} large />
            <Metric
              label="Loss remaining"
              value={(limits.max_daily_loss - dailyLossUsed).toFixed(2)}
              sub={`limit ${limits.max_daily_loss}`}
            />
            <Metric label="Drawdown" value={`${account.drawdown_percent}%`}
                    sub={`limit ${limits.max_drawdown_percent}%`}
                    tone={account.drawdown_percent >= limits.max_drawdown_percent * 0.7 ? "bear" : undefined} />
            <Metric label="Exposure" value={`${account.exposure_lots} lots`}
                    sub={`limit ${limits.max_exposure_lots}`} />
            <Metric label="Blocks issued" value={risk.blocks_issued}
                    sub="orders stopped by risk" />
          </div>

          <div className="grid grid-cols-1 gap-5 border-t border-line p-4 sm:grid-cols-2">
            <Utilisation label="Daily loss used" used={Number(dailyLossUsed.toFixed(2))}
                         limit={limits.max_daily_loss} />
            <Utilisation label="Open positions" used={account.open_positions}
                         limit={limits.max_open_positions} />
            <Utilisation label="Exposure" used={account.exposure_lots}
                         limit={limits.max_exposure_lots} unit=" lots" />
            <Utilisation label="Trades this session" used={risk.session_trades}
                         limit={limits.max_trades_per_session} />
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
            <span className="text-[11.5px] text-faint">
              Connection never implies permission: every order is checked against these
              limits, and Takeover Mode additionally needs your explicit authorization.
            </span>
            {risk.emergency_stop ? (
              <button onClick={() => void release()} disabled={busy} className="btn ml-auto h-8">
                Release emergency stop
              </button>
            ) : (
              <button onClick={() => void engage()} disabled={busy} className="btn ml-auto h-8 !text-danger">
                Emergency stop
              </button>
            )}
          </div>
        </section>

        <section className="panel">
          <PanelHeader>Account</PanelHeader>
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 p-4 sm:grid-cols-4">
            <Metric label="Balance" value={account.balance.toFixed(2)} sub={account.currency} />
            <Metric label="Equity" value={account.equity.toFixed(2)} />
            <Metric label="Floating" value={signed(account.floating_pl).text}
                    tone={signed(account.floating_pl).tone} />
            <Metric label="Mode" value={account.mode} tone="accent" />
            <Metric label="Win rate" value={account.win_rate != null ? `${account.win_rate}%` : "—"} />
            <Metric label="Average R" value={account.average_r ?? "—"} />
            <Metric label="Profit factor" value={account.profit_factor ?? "—"} />
            <Metric label="Trades closed" value={account.trades_closed} />
          </div>
        </section>

        <section className="panel">
          <PanelHeader>Active Limits</PanelHeader>
          <div className="scroll-x">
            <table className="table">
              <thead>
                <tr><th>Control</th><th className="text-right">Limit</th></tr>
              </thead>
              <tbody>
                {[
                  ["Maximum daily loss", limits.max_daily_loss],
                  ["Maximum drawdown", `${limits.max_drawdown_percent}%`],
                  ["Maximum open positions", limits.max_open_positions],
                  ["Maximum exposure", `${limits.max_exposure_lots} lots`],
                  ["Maximum trades per session", limits.max_trades_per_session],
                  ["Maximum position size", `${limits.max_position_size_lots} lots`],
                  ["Maximum spread", `${limits.max_spread_points} points`],
                  ["Cooldown after a loss", `${limits.cooldown_seconds_after_loss}s`],
                ].map(([label, value]) => (
                  <tr key={String(label)}>
                    <td className="text-dim">{label}</td>
                    <td className="num text-right">{String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-line px-4 py-2.5 text-[11px] text-faint">
            Limits are edited in Settings → Risk.
          </p>
        </section>
      </div>
    </div>
  );
}
