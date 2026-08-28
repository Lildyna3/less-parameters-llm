import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, HistogramSeries, createChart, createSeriesMarkers,
  type IChartApi, type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi,
  type Time, type UTCTimestamp,
} from "lightweight-charts";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { Analysis, Candle, Position } from "../lib/types";

/* Every timeframe MT5 exposes natively. The row scrolls rather than hiding
   any of them behind a menu. */
const TIMEFRAMES = [
  "M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20", "M30",
  "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1",
];

/** Chart chrome is read from the design tokens so it re-themes with the app
    and never needs the chart to be rebuilt. */
function chartColors() {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) =>
    css.getPropertyValue(name).trim() || fallback;
  const line = token("--line", "rgba(255,255,255,0.07)");
  return {
    layout: {
      background: { color: "transparent" },
      textColor: token("--faint", "#6b6862"),
      attributionLogo: false,
      fontFamily: token("--font-mono", "monospace"),
    },
    grid: {
      vertLines: { color: token("--grid", "rgba(255,255,255,0.035)") },
      horzLines: { color: token("--grid", "rgba(255,255,255,0.035)") },
    },
    crosshair: {
      mode: 0,
      vertLine: { color: token("--line-strong", line), labelBackgroundColor: token("--s3", "#1e1e23") },
      horzLine: { color: token("--line-strong", line), labelBackgroundColor: token("--s3", "#1e1e23") },
    },
    timeScale: { timeVisible: true, borderColor: line },
    rightPriceScale: { borderColor: line },
  };
}

function seriesColors() {
  const css = getComputedStyle(document.documentElement);
  return {
    bull: css.getPropertyValue("--bull").trim() || "#55a37d",
    bear: css.getPropertyValue("--bear").trim() || "#c4635c",
    accent: css.getPropertyValue("--accent").trim() || "#c9a961",
  };
}

export default function PriceChart({ height }: { height?: number }) {
  const { symbol, timeframe, setTimeframe, theme, ticks, analysis } = useAres();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const lastCandleRef = useRef<Candle | null>(null);
  const firstCandleTimeRef = useRef<number>(0);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);

  // Create the chart exactly once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || chartRef.current) return;
    const palette = seriesColors();
    const chart = createChart(el, { ...chartColors(), autoSize: true });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: palette.bull, downColor: palette.bear,
      wickUpColor: palette.bull, wickDownColor: palette.bear,
      borderVisible: false,
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "vol",
      color: "rgba(140,140,140,0.22)",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    chartRef.current = chart;
    seriesRef.current = series;
    volumeRef.current = volume;
    markersRef.current = createSeriesMarkers(series, []);
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeRef.current = null;
      markersRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-theme in place — the chart instance is never rebuilt.
  useEffect(() => {
    chartRef.current?.applyOptions(chartColors());
    const palette = seriesColors();
    seriesRef.current?.applyOptions({
      upColor: palette.bull, downColor: palette.bear,
      wickUpColor: palette.bull, wickDownColor: palette.bear,
    });
  }, [theme]);

  // Load candles when symbol/timeframe changes.
  useEffect(() => {
    let cancelled = false;
    setError(null);
    api.get<{ candles: Candle[]; source: string }>(`/api/candles/${symbol}?timeframe=${timeframe}&count=400`)
      .then((data) => {
        if (cancelled || !seriesRef.current || !volumeRef.current) return;
        setSource(data.source);
        seriesRef.current.setData(
          data.candles.map((c) => ({ ...c, time: c.time as UTCTimestamp })),
        );
        volumeRef.current.setData(
          data.candles.map((c) => ({
            time: c.time as UTCTimestamp, value: c.volume,
            color: c.close >= c.open ? "rgba(45,212,160,0.3)" : "rgba(248,113,113,0.3)",
          })),
        );
        lastCandleRef.current = data.candles[data.candles.length - 1] ?? null;
        firstCandleTimeRef.current = data.candles[0]?.time ?? 0;
        chartRef.current?.timeScale().fitContent();
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
          setSource(null);
          seriesRef.current?.setData([]);
          volumeRef.current?.setData([]);
        }
      });
    return () => { cancelled = true; };
  }, [symbol, timeframe]);

  // Live last-candle updates from the tick stream.
  const tick = ticks[symbol];
  useEffect(() => {
    const last = lastCandleRef.current;
    const series = seriesRef.current;
    if (!tick || !last || !series) return;
    const mid = (tick.bid + tick.ask) / 2;
    const updated: Candle = {
      ...last,
      close: mid,
      high: Math.max(last.high, mid),
      low: Math.min(last.low, mid),
    };
    lastCandleRef.current = updated;
    series.update({ ...updated, time: updated.time as UTCTimestamp });
  }, [tick]);

  // Positions for trade visualization (poll lightly).
  useEffect(() => {
    const load = () =>
      api.get<{ positions: Position[] }>("/api/positions")
        .then((d) => setPositions(d.positions.filter((p) => p.symbol === symbol)))
        .catch(() => setPositions([]));
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [symbol]);

  // Overlay: key levels from analysis + position entry/SL/TP lines + markers.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const line of priceLinesRef.current) series.removePriceLine(line);
    priceLinesRef.current = [];

    const a: Analysis | null = analysis && analysis.symbol === symbol ? analysis : null;
    if (a) {
      for (const level of a.key_levels.slice(0, 5)) {
        priceLinesRef.current.push(series.createPriceLine({
          price: level.price,
          color: level.kind === "resistance" ? "rgba(248,113,113,0.55)" : "rgba(45,212,160,0.55)",
          lineWidth: 1, lineStyle: 3, axisLabelVisible: false,
          title: level.kind === "resistance" ? "R" : "S",
        }));
      }
    }
    for (const p of positions) {
      priceLinesRef.current.push(series.createPriceLine({
        price: p.entry, color: "#38bdf8", lineWidth: 1, lineStyle: 0,
        title: `${p.direction.toUpperCase()} ${p.volume}`,
      }));
      if (p.sl != null) priceLinesRef.current.push(series.createPriceLine({
        price: p.sl, color: "#ef4444", lineWidth: 1, lineStyle: 2, title: "SL",
      }));
      if (p.tp != null) priceLinesRef.current.push(series.createPriceLine({
        price: p.tp, color: "#2dd4a0", lineWidth: 1, lineStyle: 2, title: "TP",
      }));
    }
    const lastTime = lastCandleRef.current?.time ?? 0;
    markersRef.current?.setMarkers(
      positions.map((p) => {
        // Place the marker at the actual entry time, clamped into the
        // loaded candle range so it stays visible on every timeframe.
        const entryTime = Math.floor(Date.parse(p.opened_at) / 1000) || lastTime;
        const clamped = Math.min(Math.max(entryTime, firstCandleTimeRef.current), lastTime);
        return {
          time: clamped as UTCTimestamp,
          position: p.direction === "buy" ? "belowBar" as const : "aboveBar" as const,
          color: p.direction === "buy" ? "#2dd4a0" : "#f87171",
          shape: p.direction === "buy" ? "arrowUp" as const : "arrowDown" as const,
          text: p.id.split("-")[0],
        };
      }),
    );
  }, [analysis, positions, symbol]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-line px-2 py-1.5">
        {/* The timeframe row scrolls rather than clipping on a narrow phone. */}
        <div className="scroll-x flex min-w-0 flex-1 items-center gap-0.5">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`num shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                tf === timeframe ? "bg-[var(--accent-dim)] text-accent" : "text-faint hover:text-dim"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
        <span className="flex shrink-0 items-center gap-2 pr-1">
          {source === "SIMULATED" && <span className="tag !text-warn">SIMULATED</span>}
          {source === "MT5" && <span className="tag !text-online">MT5 LIVE</span>}
        </span>
      </div>
      <div className="relative min-h-0 flex-1" style={height ? { height } : undefined}>
        <div ref={containerRef} className="absolute inset-0" />
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-elev/70">
            <div className="rounded-lg border border-line bg-elev px-4 py-3 text-center">
              <div className="text-[12px] font-bold text-offline">DATA SOURCE OFFLINE</div>
              <div className="mt-1 max-w-xs text-[11.5px] text-faint">{error}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
