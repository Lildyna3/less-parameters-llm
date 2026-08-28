import { useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { ScanRow } from "../lib/types";
import {
  Bias, Confidence, Empty, PanelHeader, Tag, Unavailable, price,
} from "../components/kit";

/* Analysis: the full structured read for the selected instrument, plus the
   scanner that ranks every watched instrument by measurable evidence. */

function FactorBar({ points }: { points: number }) {
  const width = Math.min(100, Math.abs(points) * 55);
  return (
    <span className="relative inline-block h-[3px] w-[64px] shrink-0 rounded-full bg-line-strong">
      <span
        className={`absolute top-0 h-full rounded-full ${points >= 0 ? "bg-bull left-1/2" : "bg-bear right-1/2"}`}
        style={{ width: `${width / 2}%` }}
      />
    </span>
  );
}

function FullAnalysis() {
  const { analysis, symbol, sendCommand, commandBusy } = useAres();
  const current = analysis && analysis.symbol === symbol ? analysis : analysis;

  if (!current) {
    return (
      <section className="panel">
        <PanelHeader>Instrument Analysis</PanelHeader>
        <div className="p-4">
          <Empty>No analysis yet.</Empty>
          <button
            disabled={commandBusy}
            onClick={() => void sendCommand(`Analyze ${symbol}`)}
            className="btn btn-accent w-full"
          >
            Analyze {symbol}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <PanelHeader
        right={
          <button
            disabled={commandBusy}
            onClick={() => void sendCommand(`Analyze ${current.symbol}`)}
            className="btn-quiet h-7 px-2 text-[11px] !text-accent"
          >
            Refresh
          </button>
        }
      >
        {current.symbol} Analysis
      </PanelHeader>

      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <span className="num text-[16px] font-semibold">{price(current.price)}</span>
        <Bias bias={current.bias} />
        <Confidence score={current.confidence} />
        <Tag>{current.market_state}</Tag>
        <Tag>{current.timeframe_alignment}</Tag>
        {current.data_source === "SIMULATED" && <Tag tone="warn">SIMULATED</Tag>}
      </div>

      <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
        <div className="space-y-4">
          <div>
            <div className="label">Timeframes</div>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {Object.entries(current.timeframes).map(([timeframe, data]) => (
                <div key={timeframe} className="rounded-md border border-line bg-s2 p-2.5">
                  <div className="label !text-[9px]">{timeframe}</div>
                  <div className="mt-1"><Bias bias={data.trend.direction} /></div>
                  <div className="mt-1 text-[10.5px] text-faint">
                    vol {data.volatility.state}
                    {data.dealing_range && <> · {data.dealing_range.zone}</>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="label">Structure</div>
            <p className="mt-1.5 text-[12px] leading-relaxed text-dim">{current.structure}.</p>
          </div>

          <div>
            <div className="label">Key levels</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {current.key_levels.map((level, index) => (
                <span key={index} className={`tag num ${level.kind === "resistance" ? "!text-bear" : "!text-bull"}`}>
                  {level.kind === "resistance" ? "R" : "S"} {level.price}
                </span>
              ))}
            </div>
          </div>

          <div>
            <div className="label">Liquidity</div>
            <div className="mt-1.5 space-y-1">
              {current.liquidity.sweeps.map((sweep, index) => (
                <p key={`s${index}`} className="text-[11.5px] text-dim">
                  Swept {sweep.side} at <span className="num">{sweep.level}</span> — {sweep.note}
                </p>
              ))}
              {current.liquidity.pools.map((pool, index) => (
                <p key={`p${index}`} className="text-[11.5px] text-faint">
                  Resting {pool.side} at <span className="num">{pool.level}</span> — {pool.note}
                </p>
              ))}
              {current.liquidity.sweeps.length === 0 && current.liquidity.pools.length === 0 && (
                <p className="text-[11.5px] text-faint">Nothing notable detected.</p>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <div className="label">Why this confidence</div>
            <div className="mt-2 space-y-1.5">
              {current.confidence_factors.map((factor, index) => (
                <div key={index} className="flex items-start gap-2.5">
                  <FactorBar points={factor.points} />
                  <span className={`num w-9 shrink-0 text-right text-[11px] ${
                    factor.points > 0 ? "text-bull" : factor.points < 0 ? "text-bear" : "text-faint"}`}>
                    {factor.points > 0 ? "+" : ""}{factor.points.toFixed(1)}
                  </span>
                  <span className="text-[11.5px] leading-snug text-dim">{factor.reason}</span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="label">Scenarios</div>
            <div className="mt-1.5 space-y-1.5">
              {current.scenarios.map((scenario, index) => (
                <p key={index} className="text-[11.5px] leading-relaxed text-dim">
                  <span className="text-ink">{scenario.name}:</span> {scenario.description}
                </p>
              ))}
            </div>
          </div>

          {current.invalidations.length > 0 && (
            <div className="rounded-md border border-line bg-s2 p-3">
              <div className="label !text-warn">Invalidation</div>
              {current.invalidations.map((line, index) => (
                <p key={index} className="mt-1 text-[11.5px] leading-relaxed text-dim">{line}</p>
              ))}
            </div>
          )}

          {current.risk_factors.length > 0 && (
            <div>
              <div className="label">Risk factors</div>
              <ul className="mt-1.5 space-y-1">
                {current.risk_factors.map((factor, index) => (
                  <li key={index} className="text-[11.5px] text-faint">· {factor}</li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-[10.5px] leading-relaxed text-faint">
            Evidence and confidence are computed from measurable market structure, not
            generated by a language model. Generated {current.generated_at.slice(11, 19)} UTC.
          </p>
        </div>
      </div>
    </section>
  );
}

function Scanner() {
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
      if (data.results.length === 0) {
        setError("The scan returned nothing — no market data is available to analyze.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <PanelHeader
        right={
          <button onClick={() => void scan()} disabled={busy} className="btn btn-accent h-7 text-[11px]">
            {busy ? "Scanning…" : "Run scan"}
          </button>
        }
      >
        Market Scanner
      </PanelHeader>

      {error && <Unavailable what="Scan" reason={error} />}
      {!rows && !error && (
        <Empty>Rank every watched instrument by measurable evidence.</Empty>
      )}

      {rows && rows.length > 0 && (
        <div className="scroll-x">
          <table className="table">
            <thead>
              <tr>
                <th>Instrument</th><th>Bias</th><th>Alignment</th>
                <th>Setup</th><th>Evidence</th><th>Volatility</th><th>Risk</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.symbol}
                  className="selectable"
                  onClick={() => { setSymbol(row.symbol); setSection("chart"); }}
                >
                  <td className="num font-semibold">{row.symbol}</td>
                  <td><Bias bias={row.bias} /></td>
                  <td className="text-dim">{row.alignment}</td>
                  <td className="text-dim">{row.setup}</td>
                  <td><Confidence score={row.confidence} /></td>
                  <td className="text-dim">{row.volatility}</td>
                  <td className={row.risk === "elevated" ? "text-warn" : "text-faint"}>{row.risk}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function Analysis() {
  return (
    <div className="scroll-y h-full">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-4 p-4 pb-6">
        <FullAnalysis />
        <Scanner />
      </div>
    </div>
  );
}
