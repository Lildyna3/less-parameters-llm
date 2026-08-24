import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, HistogramSeries, createChart, createSeriesMarkers,
  type IChartApi, type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi,
  type Time, type UTCTimestamp,
} from "lightweight-charts";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { Analysis, Candle, Position } from "../lib/types";

const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

function chartColors(dark: boolean) {
  const css = getComputedStyle(document.documentElement);
  return {
    layout: {
      background: { color: "transparent" },
      textColor: css.getPropertyValue("--text-dim").trim() || (dark ? "#97a1b0" : "#5a6675"),
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: css.getPropertyValue("--chart-grid").trim() },
      horzLines: { color: css.getPropertyValue("--chart-grid").trim() },
    },
    crosshair: { mode: 0 },
    timeScale: { timeVisible: true, borderColor: css.getPropertyValue("--border").trim() },
    rightPriceScale: { borderColor: css.getPropertyValue("--border").trim() },
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
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);

  // Create the chart exactly once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || chartRef.current) return;
    const chart = createChart(el, { ...chartColors(theme === "dark"), autoSize: true });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#2dd4a0", downColor: "#f87171",
      wickUpColor: "#2dd4a0", wickDownColor: "#f87171",
      borderVisible: false,
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "vol",
      color: "rgba(120,130,150,0.35)",
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

  // Re-theme without recreating.
  useEffect(() => {
    chartRef.current?.applyOptions(chartColors(theme === "dark"));
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
    markersRef.current?.setMarkers(
      positions.map((p) => ({
        time: (lastCandleRef.current?.time ?? 0) as UTCTimestamp,
        position: p.direction === "buy" ? "belowBar" : "aboveBar",
        color: p.direction === "buy" ? "#2dd4a0" : "#f87171",
        shape: p.direction === "buy" ? "arrowUp" : "arrowDown",
        text: p.id.split("-")[0],
      })),
    );
  }, [analysis, positions, symbol]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf)}
            className={`rounded-md px-2 py-0.5 text-[11px] font-semibold num ${
              tf === timeframe ? "bg-accent/15 text-accent" : "text-faint hover:text-dim"
            }`}
          >
            {tf}
          </button>
        ))}
        <span className="ml-auto flex items-center gap-2 pr-1">
          {source === "SIMULATED" && <span className="chip !text-warn">SIMULATED</span>}
          {source === "MT5" && <span className="chip !text-online">MT5 LIVE</span>}
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
