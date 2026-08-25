import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { Basket, Position, Trade } from "../lib/types";
import TakeoverPanel from "../components/TakeoverPanel";
import {
  Empty, Metric, PanelHeader, Tag, Unavailable, duration, price, signed,
} from "../components/kit";

/* Positions: a dense table of what is open, with a contextual detail panel for
   the selected row — not a wall of giant cards. */

function PositionDetail({ position, onClose, onClosed }: {
  position: Position; onClose: () => void; onClosed: () => void;
}) {
  const { setSymbol, setSection } = useAres();
  const [busy, setBusy] = useState(false);
  const pl = signed(position.floating_pl);
  const risk = position.sl != null
    ? Math.abs(position.entry - position.sl) : null;
  const reward = position.tp != null
    ? Math.abs(position.tp - position.entry) : null;

  const close = async () => {
    setBusy(true);
    await api.post("/api/position/close", { position_id: position.id }).catch(() => {});
    setBusy(false);
    onClosed();
  };

  return (
    <section className="panel rise">
      <PanelHeader
        dense
        right={<button onClick={onClose} className="btn-quiet h-6 px-1.5 text-[11px]">Close panel</button>}
      >
        {position.symbol} · {position.direction.toUpperCase()}
      </PanelHeader>
      <div className="grid grid-cols-2 gap-x-5 gap-y-4 p-4 sm:grid-cols-4">
        <Metric label="Floating P/L" value={pl.text} tone={pl.tone} large />
        <Metric label="Size" value={`${position.volume} lots`} />
        <Metric label="Entry" value={price(position.entry)} />
        <Metric label="Current" value={price(position.current_price)} />
        <Metric label="Stop" value={position.sl != null ? price(position.sl) : "none"} />
        <Metric label="Target" value={position.tp != null ? price(position.tp) : "none"} />
        <Metric
          label="Planned R:R"
          value={risk && reward ? `1 : ${(reward / risk).toFixed(2)}` : "—"}
        />
        <Metric label="Held" value={duration(position.opened_at)} />
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
        {position.strategy && <Tag>{position.strategy}</Tag>}
        {position.confidence && <Tag tone="accent">confidence {position.confidence}/5</Tag>}
        {position.basket_id && <Tag>basket {position.basket_id}</Tag>}
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => { setSymbol(position.symbol); setSection("chart"); }}
            className="btn h-8"
          >
            Open chart
          </button>
          <button onClick={() => void close()} disabled={busy} className="btn h-8 !text-bear">
            {busy ? "Closing…" : "Close position"}
          </button>
        </div>
      </div>
    </section>
  );
}

export default function Positions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [baskets, setBaskets] = useState<Basket[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [reachable, setReachable] = useState(true);

  const load = async () => {
    try {
      const [open, history] = await Promise.all([
        api.get<{ positions: Position[]; baskets: Basket[] }>("/api/positions"),
        api.get<{ trades: Trade[] }>("/api/trades?limit=25"),
      ]);
      setPositions(open.positions);
      setBaskets(open.baskets);
      setTrades(history.trades);
      setReachable(true);
    } catch {
      setReachable(false);
    }
  };

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 4000);
    return () => clearInterval(id);
  }, []);

  const active = positions.find((p) => p.id === selected) ?? null;

  if (!reachable) {
    return (
      <div className="p-4">
        <section className="panel">
          <Unavailable what="Positions" reason="The ARES backend is not reachable from this browser." />
        </section>
      </div>
    );
  }

  return (
    <div className="scroll-y h-full">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-4 p-4 pb-6">
        {active && (
          <PositionDetail
            position={active}
            onClose={() => setSelected(null)}
            onClosed={() => { setSelected(null); void load(); }}
          />
        )}

        <section className="panel">
          <PanelHeader right={<Tag>{positions.length} open</Tag>}>Open Positions</PanelHeader>
          {positions.length === 0 ? (
            <Empty>No open positions.</Empty>
          ) : (
            <>
              <div className="scroll-x hidden sm:block">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Instrument</th><th>Side</th>
                      <th className="text-right">Size</th><th className="text-right">Entry</th>
                      <th className="text-right">Current</th><th className="text-right">Stop</th>
                      <th className="text-right">Target</th><th className="text-right">P/L</th>
                      <th className="text-right">Held</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((position) => {
                      const pl = signed(position.floating_pl);
                      return (
                        <tr
                          key={position.id}
                          className={`selectable ${selected === position.id ? "is-active" : ""}`}
                          onClick={() => setSelected(position.id)}
                        >
                          <td className="num font-semibold">{position.symbol}</td>
                          <td className={position.direction === "buy" ? "text-bull" : "text-bear"}>
                            {position.direction.toUpperCase()}
                          </td>
                          <td className="num text-right">{position.volume}</td>
                          <td className="num text-right">{price(position.entry)}</td>
                          <td className="num text-right text-dim">{price(position.current_price)}</td>
                          <td className="num text-right text-faint">
                            {position.sl != null ? price(position.sl) : "—"}
                          </td>
                          <td className="num text-right text-faint">
                            {position.tp != null ? price(position.tp) : "—"}
                          </td>
                          <td className={`num text-right font-semibold ${
                            pl.tone === "bull" ? "text-bull" : pl.tone === "bear" ? "text-bear" : "text-faint"}`}>
                            {pl.text}
                          </td>
                          <td className="num text-right text-faint">{duration(position.opened_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="divide-hair sm:hidden">
                {positions.map((position) => {
                  const pl = signed(position.floating_pl);
                  return (
                    <button
                      key={position.id}
                      onClick={() => setSelected(position.id)}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="num block text-[13px] font-semibold">
                          {position.symbol}{" "}
                          <span className={position.direction === "buy" ? "text-bull" : "text-bear"}>
                            {position.direction.toUpperCase()}
                          </span>
                        </span>
                        <span className="text-[10.5px] text-faint">
                          {position.volume} lots · {duration(position.opened_at)}
                        </span>
                      </span>
                      <span className={`num text-[14px] font-semibold ${
                        pl.tone === "bull" ? "text-bull" : pl.tone === "bear" ? "text-bear" : "text-faint"}`}>
                        {pl.text}
                      </span>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </section>

        <section className="panel">
          <PanelHeader>Trade Baskets</PanelHeader>
          {baskets.length === 0 ? (
            <Empty>No baskets. Authorized takeover sessions group their trades here.</Empty>
          ) : (
            <div className="divide-hair">
              {baskets.map((basket) => {
                const pl = signed(basket.combined_pl);
                return (
                  <div key={basket.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <span className="num text-[12.5px] font-semibold">{basket.id}</span>
                    <span className="text-[11.5px] text-dim">{basket.strategy}</span>
                    <span className="num text-[11.5px]">{basket.symbol}</span>
                    <span className="text-[11px] text-faint">
                      {basket.open_trades} open · {basket.combined_exposure_lots} lots
                    </span>
                    <span className={`num text-[12.5px] font-semibold ${
                      pl.tone === "bull" ? "text-bull" : pl.tone === "bear" ? "text-bear" : "text-faint"}`}>
                      {pl.text}
                    </span>
                    <Tag tone={basket.status === "active" ? "accent" : "muted"}>{basket.status}</Tag>
                    {basket.status === "active" && basket.open_trades > 0 && (
                      <button
                        onClick={async () => { await api.post(`/api/basket/${basket.id}/close`); void load(); }}
                        className="btn ml-auto h-7 !text-bear"
                      >
                        Close basket
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <TakeoverPanel />

        <section className="panel">
          <PanelHeader>Recent Closed</PanelHeader>
          {trades.length === 0 ? (
            <Empty>No closed trades yet.</Empty>
          ) : (
            <div className="scroll-x">
              <table className="table">
                <thead>
                  <tr>
                    <th>Closed</th><th>Instrument</th><th>Side</th>
                    <th className="text-right">Entry</th><th className="text-right">Exit</th>
                    <th className="text-right">P/L</th><th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade) => {
                    const pl = signed(trade.pl);
                    return (
                      <tr key={trade.id + trade.closed_at}>
                        <td className="num text-faint">{trade.closed_at.slice(5, 16).replace("T", " ")}</td>
                        <td className="num font-semibold">{trade.symbol}</td>
                        <td className={trade.direction === "buy" ? "text-bull" : "text-bear"}>
                          {trade.direction.toUpperCase()}
                        </td>
                        <td className="num text-right">{price(trade.entry)}</td>
                        <td className="num text-right">{price(trade.exit)}</td>
                        <td className={`num text-right font-semibold ${
                          pl.tone === "bull" ? "text-bull" : pl.tone === "bear" ? "text-bear" : "text-faint"}`}>
                          {pl.text}
                        </td>
                        <td className="text-faint">{trade.close_reason}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
