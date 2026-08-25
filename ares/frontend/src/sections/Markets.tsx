import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { SymbolInfo } from "../lib/types";
import { Empty, PanelTitle } from "../components/ui";

export default function Markets() {
  const { ticks, favorites, toggleFavorite, setSymbol, setSection, symbol } = useAres();
  const [query, setQuery] = useState("");
  const [favOnly, setFavOnly] = useState(false);
  const [allSymbols, setAllSymbols] = useState<SymbolInfo[]>([]);
  const [watched, setWatched] = useState<string[]>([]);
  const [busySymbol, setBusySymbol] = useState<string | null>(null);

  useEffect(() => {
    void api.get<{ symbols: SymbolInfo[] }>("/api/symbols")
      .then((d) => setAllSymbols(d.symbols)).catch(() => {});
    void api.get<{ symbols: string[] }>("/api/watchlist")
      .then((d) => setWatched(d.symbols)).catch(() => {});
  }, []);

  const rows = useMemo(() => {
    let list = Object.values(ticks);
    if (query) list = list.filter((t) => t.symbol.includes(query.toUpperCase()));
    if (favOnly) list = list.filter((t) => favorites.includes(t.symbol));
    return list.sort((a, b) => {
      const fa = favorites.includes(a.symbol) ? 0 : 1;
      const fb = favorites.includes(b.symbol) ? 0 : 1;
      return fa - fb || a.symbol.localeCompare(b.symbol);
    });
  }, [ticks, query, favOnly, favorites]);

  // Provider symbols matching the search that are not yet on the watchlist.
  const addable = useMemo(() => {
    if (!query || query.length < 2) return [];
    const q = query.toUpperCase();
    const watchedSet = new Set([...watched, ...Object.keys(ticks)]);
    return allSymbols
      .filter((s) => s.name.toUpperCase().includes(q) && !watchedSet.has(s.name.toUpperCase()))
      .slice(0, 8);
  }, [query, allSymbols, watched, ticks]);

  const addToWatchlist = async (name: string) => {
    setBusySymbol(name);
    try {
      const resp = await api.post<{ symbols: string[] }>(`/api/watchlist/${name}`);
      setWatched(resp.symbols);
    } catch { /* symbol rejected by data source; row stays addable */ }
    setBusySymbol(null);
  };

  const removeFromWatchlist = async (name: string) => {
    try {
      const resp = await api.del<{ symbols: string[] }>(`/api/watchlist/${name}`);
      setWatched(resp.symbols);
      useAres.setState((s) => {
        const next = { ...s.ticks };
        delete next[name];
        return { ticks: next };
      });
    } catch { /* already gone */ }
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="panel mx-auto max-w-4xl">
        <PanelTitle right={
          <div className="flex items-center gap-2">
            <button onClick={() => setFavOnly(!favOnly)}
              className={`chip ${favOnly ? "!text-warn" : ""}`}>★ favorites</button>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search symbols…"
              className="w-40 rounded-md border border-line bg-inset px-2 py-1 text-[11.5px] outline-none focus:border-accent/60"
            />
          </div>
        }>
          Market Watch
        </PanelTitle>

        {addable.length > 0 && (
          <div className="border-b border-line px-3.5 py-2">
            <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-faint">
              Available from the data source — add to watchlist
            </div>
            <div className="flex flex-wrap gap-1.5">
              {addable.map((s) => (
                <button key={s.name} disabled={busySymbol === s.name}
                  onClick={() => void addToWatchlist(s.name)}
                  title={s.description}
                  className="chip hover:!text-accent disabled:opacity-40">
                  + {s.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {rows.length === 0 ? (
          <Empty>
            {Object.keys(ticks).length === 0
              ? "DATA SOURCE OFFLINE — no live quotes are streaming."
              : "No symbols match."}
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-line text-left text-[10.5px] uppercase tracking-wider text-faint">
                  <th className="px-3.5 py-2">Symbol</th>
                  <th className="px-2 py-2 text-right">Bid</th>
                  <th className="px-2 py-2 text-right">Ask</th>
                  <th className="px-2 py-2 text-right">Spread</th>
                  <th className="px-2 py-2 text-right">Δ%</th>
                  <th className="px-2 py-2">Source</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.symbol}
                    className={`cursor-pointer border-b border-line/50 last:border-0 hover:bg-inset/70 ${t.symbol === symbol ? "bg-accent/6" : ""}`}
                    onClick={() => { setSymbol(t.symbol); setSection("chart"); }}>
                    <td className="px-3.5 py-2 font-semibold num">
                      <button onClick={(e) => { e.stopPropagation(); toggleFavorite(t.symbol); }}
                        className={`mr-2 ${favorites.includes(t.symbol) ? "text-warn" : "text-faint"}`}>★</button>
                      {t.symbol}
                    </td>
                    <td className="px-2 py-2 text-right num">{t.bid}</td>
                    <td className="px-2 py-2 text-right num text-dim">{t.ask}</td>
                    <td className="px-2 py-2 text-right num text-faint">{t.spread_points ?? "—"}</td>
                    <td className={`px-2 py-2 text-right num font-semibold ${
                      (t.change_percent ?? 0) > 0 ? "text-bull" : (t.change_percent ?? 0) < 0 ? "text-bear" : "text-faint"}`}>
                      {t.change_percent != null ? `${t.change_percent > 0 ? "+" : ""}${t.change_percent}%` : "—"}
                    </td>
                    <td className="px-2 py-2">
                      <span className={`chip ${t.source === "SIMULATED" ? "!text-warn" : "!text-online"}`}>{t.source}</span>
                    </td>
                    <td className="px-2 py-2 text-right">
                      <span className="text-[10.5px] text-faint">open →</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); void removeFromWatchlist(t.symbol); }}
                        title="Remove from watchlist"
                        className="ml-2 text-[10.5px] text-faint hover:text-bear">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
