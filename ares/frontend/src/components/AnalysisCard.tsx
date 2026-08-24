import { useState } from "react";
import type { Analysis } from "../lib/types";
import { BiasTag, Confidence, fmtPrice } from "./ui";

export default function AnalysisCard({ analysis }: { analysis: Analysis }) {
  const [showFactors, setShowFactors] = useState(false);
  const tfs = Object.entries(analysis.timeframes);

  return (
    <div className="fade-up space-y-3 p-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="text-[15px] font-bold num">{analysis.symbol}</span>
        <BiasTag bias={analysis.bias} />
        <Confidence score={analysis.confidence} />
        {analysis.data_source === "SIMULATED" && <span className="chip !text-warn">SIMULATED</span>}
      </div>

      <div className="text-[12px] leading-relaxed text-dim">{analysis.structure}</div>

      <div className="grid grid-cols-3 gap-2">
        {tfs.map(([tf, data]) => (
          <div key={tf} className="rounded-lg border border-line bg-inset/60 px-2.5 py-2">
            <div className="flex items-center justify-between">
              <span className="text-[10.5px] font-bold text-faint">{tf}</span>
              <span className={`text-[10.5px] font-bold ${
                data.trend.direction === "bullish" ? "text-bull" :
                data.trend.direction === "bearish" ? "text-bear" : "text-dim"}`}>
                {data.trend.direction === "bullish" ? "▲" : data.trend.direction === "bearish" ? "▼" : "◆"} {data.trend.direction}
              </span>
            </div>
            {data.dealing_range && (
              <div className="mt-1 text-[10px] text-faint">{data.dealing_range.zone}</div>
            )}
            <div className="text-[10px] text-faint">vol {data.volatility.state}</div>
          </div>
        ))}
      </div>

      <div>
        <div className="mb-1 text-[10.5px] font-bold uppercase tracking-wider text-faint">Key levels</div>
        <div className="flex flex-wrap gap-1.5">
          {analysis.key_levels.slice(0, 6).map((level, i) => (
            <span key={i} className={`chip num ${level.kind === "resistance" ? "!text-bear" : "!text-bull"}`}>
              {level.kind === "resistance" ? "R" : "S"} {fmtPrice(level.price)}
            </span>
          ))}
        </div>
      </div>

      {analysis.scenarios.length > 0 && (
        <div>
          <div className="mb-1 text-[10.5px] font-bold uppercase tracking-wider text-faint">Scenarios</div>
          {analysis.scenarios.map((s, i) => (
            <div key={i} className="text-[11.5px] leading-relaxed text-dim">
              <span className="font-semibold text-ink">{s.name}:</span> {s.description}
            </div>
          ))}
        </div>
      )}

      {analysis.invalidations.length > 0 && (
        <div className="rounded-lg border border-warn/25 bg-warn/8 px-2.5 py-1.5 text-[11.5px] text-warn">
          Invalidation: {analysis.invalidations[0]}
        </div>
      )}

      {analysis.risk_factors.length > 0 && (
        <div className="text-[11px] text-faint">Risk: {analysis.risk_factors.join("; ")}</div>
      )}

      <button
        onClick={() => setShowFactors(!showFactors)}
        className="text-[11px] font-semibold text-accent hover:underline"
      >
        {showFactors ? "Hide" : "Why this confidence?"}
      </button>
      {showFactors && (
        <div className="space-y-1">
          {analysis.confidence_factors.map((f, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px]">
              <span className={`w-10 shrink-0 text-right font-bold num ${f.points > 0 ? "text-bull" : f.points < 0 ? "text-bear" : "text-faint"}`}>
                {f.points > 0 ? "+" : ""}{f.points.toFixed(1)}
              </span>
              <span className="text-dim">{f.reason}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
