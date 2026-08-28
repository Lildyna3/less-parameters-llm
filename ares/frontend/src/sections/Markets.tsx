import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { SymbolInfo } from "../lib/types";
import { PanelHeader, Unavailable, price } from "../components/kit";

/* Markets: one clean instrument table with search, favourites, asset-class
   filters and sorting. On a phone the same data becomes a compact list of
   rows rather than a squeezed table. */

type SortKey = "symbol" | "change" | "spread";

const CLASSES: { id: string; label: string; test: (symbol: string) => boolean }[] = [
  { id: "ALL", label: "All", test: () => true },
  { id: "FX", label: "Forex", test: (s) => /^[A-Z]{6}$/.test(s) && !s.startsWith("XA") },
  { id: "METALS", label: "Metals", test: (s) => s.startsWith("XAU") || s.startsWith("XAG") },
  { id: "INDICES", label: "Indices", test: (s) => /^(US|DE|UK|JP|EU)\d|^(SPX|NAS|DJI)/.test(s) },
  { id: "CRYPTO", label: "Crypto", test: (s) => /(BTC|ETH|XRP|SOL|LTC|DOGE)/.test(s) },
];

export default function Markets() {
  const { ticks, favorites, toggleFavorite, setSymbol, setSection, symbol } = useAres();
  const [query, setQuery] = useState("");
  const [assetClass, setAssetClass] = useState("ALL");
  const [favOnly, setFavOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("symbol");
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
    const filter = CLASSES.find((c) => c.id === assetClass) ?? CLASSES[0];
    let list = Object.values(ticks).filter((t) => filter.test(t.symbol));
    if (query) list = list.filter((t) => t.symbol.includes(query.toUpperCase()));
    if (favOnly) list = list.filter((t) => favorites.includes(t.symbol));
    return [...list].sort((a, b) => {
      if (sort === "change") return Math.abs(b.change_percent ?? 0) - Math.abs(a.change_percent ?? 0);
      if (sort === "spread") return (a.spread_points ?? 1e9) - (b.spread_points ?? 1e9);
      const favA = favorites.includes(a.symbol) ? 0 : 1;
      const favB = favorites.includes(b.symbol) ? 0 : 1;
      return favA - favB || a.symbol.localeCompare(b.symbol);
    });
  }, [ticks, query, favOnly, favorites, sort, assetClass]);

  const addable = useMemo(() => {
    if (query.length < 2) return [];
    const needle = query.toUpperCase();
    const known = new Set([...watched, ...Object.keys(ticks)]);
    return allSymbols
      .filter((s) => s.name.toUpperCase().includes(needle) && !known.has(s.name.toUpperCase()))
      .slice(0, 8);
  }, [query, allSymbols, watched, ticks]);

  const add = async (name: string) => {
    setBusySymbol(name);
    try {
      setWatched((await api.post<{ symbols: string[] }>(`/api/watchlist/${name}`)).symbols);
    } catch { /* the data source rejected it; row stays addable */ }
    setBusySymbol(null);
  };

  const remove = async (name: string) => {
    try {
      setWatched((await api.del<{ symbols: string[] }>(`/api/watchlist/${name}`)).symbols);
      useAres.setState((state) => {
        const next = { ...state.ticks };
        delete next[name];
        return { ticks: next };
      });
    } catch { /* already gone */ }
  };

  const open = (name: string) => { setSymbol(name); setSection("chart"); };

  return (
    <div className="scroll-y h-full">
      <div className="mx-auto max-w-[1100px] p-4">
        <section className="panel">
          <PanelHeader
            right={
              <>
                <button
                  onClick={() => setFavOnly((v) => !v)}
                  className={`tag ${favOnly ? "!border-[var(--accent-line)] !text-accent" : ""}`}
                >
                  Favourites
                </button>
                <select
                  value={sort}
                  onChange={(event) => setSort(event.target.value as SortKey)}
                  className="field !h-7 !w-auto !text-[11px]"
                  aria-label="Sort instruments"
                >
                  <option value="symbol">Sort: name</option>
                  <option value="change">Sort: move</option>
                  <option value="spread">Sort: spread</option>
                </select>
              </>
            }
          >
            Markets
          </PanelHeader>

          <div className="flex flex-col gap-2 border-b border-line px-3 py-2.5 sm:flex-row sm:items-center">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search instruments…"
              className="field sm:max-w-[220px]"
            />
            <div className="scroll-x flex gap-1.5">
              {CLASSES.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setAssetClass(item.id)}
                  className={`tag shrink-0 ${
                    assetClass === item.id ? "!border-[var(--accent-line)] !bg-[var(--accent-dim)] !text-accent" : ""
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {addable.length > 0 && (
            <div className="border-b border-line px-4 py-2.5">
              <div className="label">Available from the data source</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {addable.map((item) => (
                  <button
                    key={item.name}
                    disabled={busySymbol === item.name}
                    onClick={() => void add(item.name)}
                    title={item.description}
                    className="tag hover:!text-accent disabled:opacity-40"
                  >
                    + {item.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {rows.length === 0 ? (
            <Unavailable
              what={Object.keys(ticks).length === 0 ? "Market data" : "Instruments"}
              reason={
                Object.keys(ticks).length === 0
                  ? "No quotes are streaming. Connect the MT5 bridge, or enable the simulated feed for testing."
                  : "No instrument matches this filter."
              }
            />
          ) : (
            <>
              {/* Desktop table */}
              <div className="scroll-x hidden sm:block">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Instrument</th>
                      <th className="text-right">Bid</th>
                      <th className="text-right">Ask</th>
                      <th className="text-right">Spread</th>
                      <th className="text-right">Change</th>
                      <th>Source</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={row.symbol}
                        className={`selectable ${row.symbol === symbol ? "is-active" : ""}`}
                        onClick={() => open(row.symbol)}
                      >
                        <td>
                          <span className="flex items-center gap-2">
                            <button
                              onClick={(event) => { event.stopPropagation(); toggleFavorite(row.symbol); }}
                              className={favorites.includes(row.symbol) ? "text-accent" : "text-faint hover:text-dim"}
                              aria-label="Toggle favourite"
                            >
                              ★
                            </button>
                            <span className="num font-semibold">{row.symbol}</span>
                          </span>
                        </td>
                        <td className="num text-right">{row.bid}</td>
                        <td className="num text-right text-dim">{row.ask}</td>
                        <td className="num text-right text-faint">{row.spread_points ?? "—"}</td>
                        <td className={`num text-right ${
                          (row.change_percent ?? 0) > 0 ? "text-bull" :
                          (row.change_percent ?? 0) < 0 ? "text-bear" : "text-faint"}`}>
                          {row.change_percent != null
                            ? `${row.change_percent > 0 ? "+" : ""}${row.change_percent}%` : "—"}
                        </td>
                        <td>
                          <span className={`tag ${row.source === "SIMULATED" ? "!text-warn" : "!text-online"}`}>
                            {row.source}
                          </span>
                        </td>
                        <td className="text-right">
                          <button
                            onClick={(event) => { event.stopPropagation(); void remove(row.symbol); }}
                            className="text-[11px] text-faint hover:text-bear"
                            aria-label="Remove from watchlist"
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Phone list: same data, laid out for a thumb. */}
              <div className="divide-hair sm:hidden">
                {rows.map((row) => (
                  <button
                    key={row.symbol}
                    onClick={() => open(row.symbol)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left"
                  >
                    <button
                      onClick={(event) => { event.stopPropagation(); toggleFavorite(row.symbol); }}
                      className={favorites.includes(row.symbol) ? "text-accent" : "text-faint"}
                      aria-label="Toggle favourite"
                    >
                      ★
                    </button>
                    <span className="min-w-0 flex-1">
                      <span className="num block text-[13px] font-semibold">{row.symbol}</span>
                      <span className="text-[10.5px] text-faint">
                        spread {row.spread_points ?? "—"} · {row.source}
                      </span>
                    </span>
                    <span className="text-right">
                      <span className="num block text-[13.5px]">{price(row.bid)}</span>
                      <span className={`num text-[11px] ${
                        (row.change_percent ?? 0) > 0 ? "text-bull" :
                        (row.change_percent ?? 0) < 0 ? "text-bear" : "text-faint"}`}>
                        {row.change_percent != null
                          ? `${row.change_percent > 0 ? "+" : ""}${row.change_percent}%` : "—"}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
