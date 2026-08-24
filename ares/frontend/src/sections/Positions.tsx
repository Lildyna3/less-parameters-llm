import { useEffect, useState } from "react";
import { api } from "../lib/api";
import TakeoverPanel from "../components/TakeoverPanel";
import type { Basket, Position } from "../lib/types";
import { Empty, PanelTitle, pl } from "../components/ui";

interface RiskSnapshot {
  emergency_stop: boolean;
  daily_pl: number;
  session_trades: number;
  cooldown_active: boolean;
  blocks_issued: number;
}

export default function Positions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [baskets, setBaskets] = useState<Basket[]>([]);
  const [risk, setRisk] = useState<RiskSnapshot | null>(null);

  const load = async () => {
    try {
      const [pos, riskData] = await Promise.all([
        api.get<{ positions: Position[]; baskets: Basket[] }>("/api/positions"),
        api.get<RiskSnapshot>("/api/risk"),
      ]);
      setPositions(pos.positions);
      setBaskets(pos.baskets);
      setRisk(riskData);
    } catch { /* backend offline; panels show empty */ }
  };

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 3000);
    return () => clearInterval(id);
  }, []);

  const closePosition = async (id: string) => {
    await api.post("/api/position/close", { position_id: id });
    await load();
  };
  const closeBasket = async (id: string) => {
    await api.post(`/api/basket/${id}/close`);
    await load();
  };
  const emergencyStop = async () => {
    if (!window.confirm("ENGAGE EMERGENCY STOP?\nAll open paper positions will be closed and execution blocked.")) return;
    await api.post("/api/risk/emergency-stop");
    await load();
  };
  const releaseStop = async () => {
    await api.post("/api/risk/emergency-stop/release");
    await load();
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 overflow-y-auto p-3 lg:grid-cols-[1fr_340px]">
      <div className="flex min-h-0 flex-col gap-3">
        <div className="panel">
          <PanelTitle right={<span className="chip">PAPER</span>}>Open Positions</PanelTitle>
          {positions.length === 0 ? <Empty>No open positions.</Empty> : (
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-line text-left text-[10.5px] uppercase tracking-wider text-faint">
                    <th className="px-3.5 py-2">ID</th><th className="px-2 py-2">Symbol</th>
                    <th className="px-2 py-2">Dir</th><th className="px-2 py-2 text-right">Lots</th>
                    <th className="px-2 py-2 text-right">Entry</th><th className="px-2 py-2 text-right">SL</th>
                    <th className="px-2 py-2 text-right">TP</th><th className="px-2 py-2 text-right">P/L</th>
                    <th className="px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => {
                    const t = pl(p.floating_pl);
                    return (
                      <tr key={p.id} className="border-b border-line/50 last:border-0">
                        <td className="px-3.5 py-2 num text-faint">{p.id.split("-")[0]}</td>
                        <td className="px-2 py-2 font-semibold num">{p.symbol}</td>
                        <td className={`px-2 py-2 font-bold ${p.direction === "buy" ? "text-bull" : "text-bear"}`}>
                          {p.direction.toUpperCase()}
                        </td>
                        <td className="px-2 py-2 text-right num">{p.volume}</td>
                        <td className="px-2 py-2 text-right num">{p.entry}</td>
                        <td className="px-2 py-2 text-right num text-faint">{p.sl ?? "—"}</td>
                        <td className="px-2 py-2 text-right num text-faint">{p.tp ?? "—"}</td>
                        <td className={`px-2 py-2 text-right num font-bold text-${t.tone === "dim" ? "faint" : t.tone}`}>{t.text}</td>
                        <td className="px-2 py-2 text-right">
                          <button onClick={() => void closePosition(p.id)}
                            className="rounded-md border border-line px-2 py-0.5 text-[10.5px] font-semibold text-dim hover:border-bear/50 hover:text-bear">
                            Close
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

        <div className="panel">
          <PanelTitle>Trade Baskets</PanelTitle>
          {baskets.length === 0 ? <Empty>No baskets. Takeover sessions group their trades here.</Empty> : (
            <div className="divide-y divide-line/60">
              {baskets.map((b) => {
                const t = pl(b.combined_pl);
                return (
                  <div key={b.id} className="flex flex-wrap items-center gap-3 px-3.5 py-2.5 text-[12px]">
                    <span className="font-bold num">{b.id}</span>
                    <span className="text-dim">{b.strategy}</span>
                    <span className="num">{b.symbol}</span>
                    <span className={b.direction === "buy" ? "text-bull" : "text-bear"}>{b.direction.toUpperCase()}</span>
                    <span className="text-faint num">{b.open_trades} open · {b.combined_exposure_lots} lots</span>
                    <span className={`num font-bold text-${t.tone === "dim" ? "faint" : t.tone}`}>{t.text}</span>
                    <span className={`chip ${b.status === "active" ? "!text-online" : ""}`}>{b.status}</span>
                    {b.status === "active" && b.open_trades > 0 && (
                      <button onClick={() => void closeBasket(b.id)}
                        className="ml-auto rounded-md border border-line px-2 py-0.5 text-[10.5px] font-semibold text-dim hover:border-bear/50 hover:text-bear">
                        Close basket
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-col gap-3">
        <div className={`panel ${risk?.emergency_stop ? "border-danger/50" : ""}`}>
          <PanelTitle>Risk Control</PanelTitle>
          <div className="space-y-2.5 p-3.5 text-[12px]">
            {risk && (
              <div className="space-y-1 text-dim">
                <div>Daily P/L: <span className={`num font-bold ${risk.daily_pl >= 0 ? "text-bull" : "text-bear"}`}>{risk.daily_pl.toFixed(2)}</span></div>
                <div>Session trades: <span className="num text-ink">{risk.session_trades}</span></div>
                <div>Risk blocks issued: <span className="num text-ink">{risk.blocks_issued}</span></div>
                {risk.cooldown_active && <div className="text-warn">Post-loss cooldown active</div>}
              </div>
            )}
            {risk?.emergency_stop ? (
              <>
                <div className="rounded-lg bg-danger/10 px-2.5 py-1.5 text-[11.5px] font-bold text-danger">
                  EMERGENCY STOP ENGAGED — execution blocked
                </div>
                <button onClick={() => void releaseStop()}
                  className="w-full rounded-lg border border-line py-2 text-[11.5px] font-bold text-dim hover:text-ink">
                  Release emergency stop
                </button>
              </>
            ) : (
              <button onClick={() => void emergencyStop()}
                className="w-full rounded-lg bg-danger/12 py-2 text-[11.5px] font-bold text-danger hover:bg-danger/20">
                ■ EMERGENCY STOP
              </button>
            )}
          </div>
        </div>
        <TakeoverPanel />
      </div>
    </div>
  );
}
