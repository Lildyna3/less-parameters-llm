import { useEffect, useState } from "react";
import PriceChart from "../components/PriceChart";
import { api } from "../lib/api";
import { useAres } from "../store";
import { Empty, PanelHeader, Tag } from "../components/kit";

/* The market workspace: the chart is the visual focus and everything else is
   a quiet column beside it (below it, on a phone). */

interface OrderResult {
  success: boolean;
  message: string;
  risk?: { reasons: string[] } | null;
}

interface PriceAlert {
  id: number; symbol: string; level: number; condition: string;
  note: string | null; triggered: boolean;
}

function OrderTicket() {
  const { symbol, ticks } = useAres();
  const tick = ticks[symbol];
  const [volume, setVolume] = useState("0.10");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (direction: "buy" | "sell") => {
    setBusy(true);
    setResult(null);
    try {
      const response = await api.post<OrderResult>("/api/order/demo", {
        symbol, direction, volume: parseFloat(volume) || 0,
        sl: sl ? parseFloat(sl) : null, tp: tp ? parseFloat(tp) : null,
        strategy: "manual",
      });
      setResult({
        ok: response.success,
        text: response.success
          ? response.message
          : `${response.message}${response.risk?.reasons?.length ? ` — ${response.risk.reasons.join("; ")}` : ""}`,
      });
    } catch (error) {
      setResult({ ok: false, text: error instanceof Error ? error.message : "Order failed" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <PanelHeader dense right={<Tag>PAPER</Tag>}>Order · {symbol}</PanelHeader>
      <div className="space-y-2.5 p-4">
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "Lots", value: volume, set: setVolume, placeholder: "0.10" },
            { label: "Stop", value: sl, set: setSl, placeholder: "optional" },
            { label: "Target", value: tp, set: setTp, placeholder: "optional" },
          ].map((field) => (
            <label key={field.label} className="block">
              <span className="label">{field.label}</span>
              <input
                value={field.value}
                onChange={(event) => field.set(event.target.value)}
                placeholder={field.placeholder}
                className="field num mt-1"
              />
            </label>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            disabled={busy || !tick}
            onClick={() => void submit("sell")}
            className="btn h-9 !border-[color-mix(in_srgb,var(--bear)_35%,transparent)] !text-bear"
          >
            Sell {tick ? tick.bid : "—"}
          </button>
          <button
            disabled={busy || !tick}
            onClick={() => void submit("buy")}
            className="btn h-9 !border-[color-mix(in_srgb,var(--bull)_35%,transparent)] !text-bull"
          >
            Buy {tick ? tick.ask : "—"}
          </button>
        </div>
        {!tick && (
          <p className="text-[11px] text-offline">
            No live quote for {symbol} — orders are refused rather than filled at a stale price.
          </p>
        )}
        {result && (
          <p className={`text-[11.5px] leading-relaxed ${result.ok ? "text-bull" : "text-bear"}`}>
            {result.text}
          </p>
        )}
      </div>
    </section>
  );
}

function AlertsPanel() {
  const { symbol, ticks } = useAres();
  const tick = ticks[symbol];
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [level, setLevel] = useState("");
  const [condition, setCondition] = useState<"above" | "below">("above");

  const load = () => {
    void api.get<{ price_alerts: PriceAlert[] }>("/api/alerts")
      .then((data) => setAlerts(data.price_alerts)).catch(() => {});
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  const create = async () => {
    const value = parseFloat(level);
    if (!Number.isFinite(value)) return;
    await api.post("/api/alerts/price", { symbol, level: value, condition });
    setLevel("");
    load();
  };

  return (
    <section className="panel">
      <PanelHeader dense>Alerts</PanelHeader>
      <div className="space-y-2 p-4">
        <div className="flex gap-2">
          <select
            value={condition}
            onChange={(event) => setCondition(event.target.value as "above" | "below")}
            className="field !w-[86px]"
            aria-label="Alert condition"
          >
            <option value="above">above</option>
            <option value="below">below</option>
          </select>
          <input
            value={level}
            onChange={(event) => setLevel(event.target.value)}
            placeholder={tick ? ((tick.bid + tick.ask) / 2).toFixed(5) : "level"}
            className="field num"
            aria-label="Alert level"
          />
          <button onClick={() => void create()} className="btn shrink-0">Set</button>
        </div>
        {alerts.length === 0 ? (
          <p className="text-[11px] text-faint">No alerts set.</p>
        ) : (
          <div className="space-y-1">
            {alerts.map((alert) => (
              <div key={alert.id} className="flex items-center gap-2 text-[11.5px]">
                <span className="num font-semibold">{alert.symbol}</span>
                <span className="text-dim">{alert.condition}</span>
                <span className="num">{alert.level}</span>
                {alert.triggered && <Tag tone="bull">fired</Tag>}
                <button
                  onClick={async () => { await api.del(`/api/alerts/price/${alert.id}`); load(); }}
                  className="ml-auto text-faint hover:text-bear"
                  aria-label="Delete alert"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default function Chart() {
  const { symbol, analysis, sendCommand, commandBusy } = useAres();
  const current = analysis && analysis.symbol === symbol ? analysis : null;

  return (
    <div className="h-full">
      <div className="mx-auto grid h-full max-w-[1700px] grid-cols-1 gap-4 p-4 lg:grid-cols-[1fr_300px]">
        <section className="panel min-h-[380px] overflow-hidden lg:min-h-0">
          <PriceChart />
        </section>

        <div className="scroll-y flex min-h-0 flex-col gap-4 pb-4">
          <section className="panel">
            <PanelHeader dense>ARES Read</PanelHeader>
            {current ? (
              <div className="space-y-2 p-4">
                <p className="text-[12px] leading-relaxed text-dim">{current.structure}.</p>
                <div className="flex flex-wrap gap-1.5">
                  {current.key_levels.slice(0, 4).map((level, index) => (
                    <span key={index} className={`tag num ${level.kind === "resistance" ? "!text-bear" : "!text-bull"}`}>
                      {level.kind === "resistance" ? "R" : "S"} {level.price}
                    </span>
                  ))}
                </div>
                <button
                  disabled={commandBusy}
                  onClick={() => void sendCommand(`Analyze ${symbol}`)}
                  className="btn btn-accent w-full"
                >
                  Re-analyze {symbol}
                </button>
              </div>
            ) : (
              <div className="p-4">
                <Empty>No analysis for {symbol} yet.</Empty>
                <button
                  disabled={commandBusy}
                  onClick={() => void sendCommand(`Analyze ${symbol}`)}
                  className="btn btn-accent w-full"
                >
                  Analyze {symbol}
                </button>
              </div>
            )}
          </section>

          <OrderTicket />
          <AlertsPanel />
        </div>
      </div>
    </div>
  );
}
