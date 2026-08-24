import { useEffect } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import { Empty, PanelTitle } from "./ui";

export default function TakeoverPanel() {
  const { takeover, refreshTakeover } = useAres();

  useEffect(() => {
    void refreshTakeover();
    const id = setInterval(() => void refreshTakeover(), 4000);
    return () => clearInterval(id);
  }, [refreshTakeover]);

  const authorize = async () => {
    if (!takeover) return;
    const confirmed = window.confirm(
      `AUTHORIZE TAKEOVER ${takeover.id}?\n\n` +
      `${takeover.symbol} ${takeover.direction.toUpperCase()} — ${takeover.proposed_trades.length} trade(s)\n` +
      `Max loss: ${takeover.max_loss} · Max trades: ${takeover.max_trades} · ` +
      `Time limit: ${Math.round(takeover.duration_seconds / 60)} min\n\n` +
      `ARES will execute DEMO trades within these limits. You can stop it at any time.`,
    );
    if (!confirmed) return;
    await api.post("/api/takeover/authorize", { session_id: takeover.id, confirm: true });
    await refreshTakeover();
  };

  const stop = async () => {
    await api.post("/api/takeover/stop");
    await refreshTakeover();
  };

  return (
    <div className={`panel ${takeover ? "border-warn/40" : ""}`}>
      <PanelTitle right={takeover && (
        <span className={`chip ${takeover.state === "ACTIVE" ? "!text-warn" : "!text-dim"}`}>{takeover.state}</span>
      )}>
        Takeover Mode
      </PanelTitle>
      {!takeover ? (
        <Empty>No takeover session. Ask ARES: “Request takeover on XAUUSD”.</Empty>
      ) : (
        <div className="space-y-2.5 p-3.5">
          <div className="text-[12.5px]">
            <span className="font-bold num">{takeover.symbol}</span>{" "}
            <span className={takeover.direction === "buy" ? "text-bull" : "text-bear"}>
              {takeover.direction.toUpperCase()}
            </span>{" "}
            · confidence {takeover.confidence}/5
          </div>
          <div className="text-[11.5px] text-dim">{takeover.reason}</div>
          {takeover.proposed_trades.map((t, i) => (
            <div key={i} className="rounded-lg border border-line bg-inset/60 px-2.5 py-1.5 text-[11px] num text-dim">
              {t.direction.toUpperCase()} {t.volume} lots · SL {t.sl} · TP {t.tp ?? "—"}
              {t.executed && <span className="ml-2 text-bull">✓ executed</span>}
            </div>
          ))}
          <div className="text-[11px] text-faint num">
            Max loss {takeover.max_loss} · max {takeover.max_trades} trade(s) ·{" "}
            {Math.round(takeover.duration_seconds / 60)} min limit
            {takeover.basket_id && <> · basket {takeover.basket_id}</>}
          </div>
          {takeover.log.length > 0 && (
            <div className="max-h-20 overflow-y-auto rounded-lg bg-inset/60 px-2.5 py-1.5 text-[10.5px] text-faint">
              {takeover.log.map((l, i) => <div key={i}>{l}</div>)}
            </div>
          )}
          <div className="flex gap-2">
            {takeover.state === "REQUESTED" && (
              <button onClick={() => void authorize()}
                className="rounded-lg bg-warn/15 px-3 py-1.5 text-[11.5px] font-bold text-warn hover:bg-warn/25">
                AUTHORIZE
              </button>
            )}
            <button onClick={() => void stop()}
              className="rounded-lg bg-danger/12 px-3 py-1.5 text-[11.5px] font-bold text-danger hover:bg-danger/20">
              STOP / CANCEL
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
