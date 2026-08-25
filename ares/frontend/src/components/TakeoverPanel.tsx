import { useEffect } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import { Empty, PanelHeader, Tag } from "./kit";

/* Takeover Mode. ARES can request; only the operator can authorize, and only
   through this explicit control — never from a chat message. */

export default function TakeoverPanel() {
  const { takeover, refreshTakeover } = useAres();

  useEffect(() => {
    void refreshTakeover();
    const id = setInterval(() => void refreshTakeover(), 5000);
    return () => clearInterval(id);
  }, [refreshTakeover]);

  const authorize = async () => {
    if (!takeover) return;
    const trade = takeover.proposed_trades[0];
    const confirmed = window.confirm(
      `Authorize takeover ${takeover.id}?\n\n`
      + `${takeover.symbol} ${takeover.direction.toUpperCase()} · `
      + `${takeover.proposed_trades.length} trade(s)\n`
      + (trade ? `First: ${trade.volume} lots, stop ${trade.sl}, target ${trade.tp ?? "none"}\n` : "")
      + `Maximum loss: ${takeover.max_loss}\n`
      + `Maximum trades: ${takeover.max_trades}\n`
      + `Time limit: ${Math.round(takeover.duration_seconds / 60)} minutes\n\n`
      + `ARES will execute demo trades within these limits. You can stop it at any time.`
    );
    if (!confirmed) return;
    await api.post("/api/takeover/authorize", { session_id: takeover.id, confirm: true });
    await refreshTakeover();
  };

  const stop = async () => {
    await api.post("/api/takeover/stop");
    await refreshTakeover();
  };

  const active = takeover?.state === "ACTIVE";

  return (
    <section className={`panel ${takeover ? "!border-[var(--accent-line)]" : ""}`}>
      <PanelHeader
        dense
        right={takeover ? <Tag tone={active ? "warn" : "accent"}>{takeover.state}</Tag> : <Tag>IDLE</Tag>}
      >
        Takeover Mode
      </PanelHeader>

      {!takeover ? (
        <Empty>
          No session. Ask ARES to request takeover on an instrument; authorization
          always stays with you.
        </Empty>
      ) : (
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="num text-[13px] font-semibold">{takeover.symbol}</span>
            <span className={`text-[12px] font-semibold ${
              takeover.direction === "buy" ? "text-bull" : "text-bear"}`}>
              {takeover.direction.toUpperCase()}
            </span>
            <Tag tone="accent">confidence {takeover.confidence}/5</Tag>
          </div>

          <p className="text-[11.5px] leading-relaxed text-dim">{takeover.reason}</p>

          <div className="space-y-1">
            {takeover.proposed_trades.map((trade, index) => (
              <div key={index} className="flex items-center gap-2 rounded-md border border-line bg-s2 px-2.5 py-1.5">
                <span className="num text-[11px] text-dim">
                  {trade.direction.toUpperCase()} {trade.volume} · stop {trade.sl} · target {trade.tp ?? "—"}
                </span>
                {trade.executed && <span className="ml-auto text-[10.5px] text-bull">executed</span>}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-2 border-t border-line pt-2.5">
            {[
              ["Max loss", takeover.max_loss],
              ["Max trades", takeover.max_trades],
              ["Time limit", `${Math.round(takeover.duration_seconds / 60)}m`],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <div className="label !text-[9px]">{label}</div>
                <div className="num mt-0.5 text-[12px]">{String(value)}</div>
              </div>
            ))}
          </div>

          {takeover.log.length > 0 && (
            <div className="scroll-y max-h-20 rounded-md bg-s2 px-2.5 py-1.5">
              {takeover.log.map((line, index) => (
                <p key={index} className="text-[10.5px] leading-relaxed text-faint">{line}</p>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            {takeover.state === "REQUESTED" && (
              <button onClick={() => void authorize()} className="btn btn-accent flex-1">
                Authorize
              </button>
            )}
            <button onClick={() => void stop()} className="btn flex-1 !text-danger">
              {active ? "Stop now" : "Cancel"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
