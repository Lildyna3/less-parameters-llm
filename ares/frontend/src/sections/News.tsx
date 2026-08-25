import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { CalendarEvent, NewsArticle, NewsResponse } from "../lib/types";
import { Empty, Impact, PanelHeader, Tag, Unavailable, ago, clock } from "../components/kit";

/* The ARES news experience: a dense, scannable chronological feed with
   category filters, a reading view for the selected story, and a direct route
   from any story into that instrument's analysis.

   Headlines, summaries, sources and timestamps are reproduced verbatim from
   the feed. ARES's own read is always in its own labelled block — never mixed
   into the source text, and never invented when there is no story. */

function ImpactAccent({ level }: { level: string }) {
  const tone =
    level === "CRITICAL" ? "bg-danger" : level === "HIGH" ? "bg-warn" :
    level === "MODERATE" ? "bg-accent" : "bg-line-strong";
  return <span className={`absolute inset-y-0 left-0 w-[2px] ${tone}`} />;
}

function ArticleCard({ article, active, onSelect }: {
  article: NewsArticle; active: boolean; onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`relative block w-full px-4 py-3 text-left transition-colors ${
        active ? "bg-s2" : "hover:bg-s2/70"
      }`}
    >
      <ImpactAccent level={article.impact} />
      <div className="flex items-center gap-2">
        <span className="label !tracking-[0.08em] !text-dim">{article.source}</span>
        <span className="text-[10px] text-faint">· {ago(article.published_at)}</span>
        <span className="ml-auto"><Impact level={article.impact} /></span>
      </div>

      <h3 className="mt-1.5 text-[13px] font-medium leading-snug text-ink">{article.title}</h3>

      {(article.symbols.length > 0 || article.currencies.length > 0 || article.categories.length > 0) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
          {article.symbols.slice(0, 3).map((symbol) => (
            <span key={symbol} className="num text-[10.5px] text-accent">{symbol}</span>
          ))}
          {article.currencies.slice(0, 2).map((currency) => (
            <span key={currency} className="num text-[10.5px] text-dim">{currency}</span>
          ))}
          <span className="label !text-[9px]">{article.categories[0]}</span>
        </div>
      )}

      {article.summary && (
        <p className="mt-1.5 line-clamp-2 text-[11.5px] leading-relaxed text-faint">
          {article.summary}
        </p>
      )}

      <div className="mt-2 flex items-center gap-1.5">
        <span className="label !text-[9px] !text-accent">ARES</span>
        <span className={`text-[11px] ${
          article.direction === "bullish" ? "text-bull" :
          article.direction === "bearish" ? "text-bear" : "text-dim"}`}>
          {article.ares_impact}
        </span>
      </div>
    </button>
  );
}

function ArticleDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { analyzeSymbol, openArticle } = useAres();
  const [data, setData] = useState<{ article: NewsArticle; related: NewsArticle[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    void api.get<{ article: NewsArticle; related: NewsArticle[] }>(`/api/news/${id}`)
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, [id]);

  if (error) return <Unavailable what="Story" reason={error} />;
  if (!data) return <Empty>Loading story…</Empty>;

  const { article, related } = data;

  return (
    <article className="rise scroll-y h-full">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <button onClick={onClose} className="btn-quiet h-7 px-2 text-[11.5px]">← Feed</button>
        <span className="ml-auto"><Impact level={article.impact} /></span>
      </div>

      <div className="px-5 py-5">
        <div className="flex items-center gap-2">
          <span className="label !text-dim">{article.source}</span>
          <span className="num text-[10.5px] text-faint">
            {article.published_at.slice(0, 10)} {clock(article.published_at)} UTC
          </span>
        </div>

        <h1 className="display mt-2 text-[21px] leading-[1.25] text-ink">{article.title}</h1>

        {article.summary && (
          <p className="mt-4 text-[13px] leading-[1.7] text-dim">{article.summary}</p>
        )}

        {article.url && (
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-block text-[11.5px] text-accent hover:underline"
          >
            Read the full article at {article.source} ↗
          </a>
        )}
        <p className="mt-2 text-[10.5px] leading-relaxed text-faint">
          ARES reproduces the headline and summary the source published. It does not
          reproduce or generate full article text.
        </p>

        {/* ARES's interpretation, kept visibly separate from source content. */}
        <section className="mt-6 rounded-md border border-[var(--accent-line)] bg-[var(--accent-dim)] p-4">
          <div className="label !text-accent">ARES Interpretation</div>
          <p className="mt-2 text-[12.5px] leading-[1.65] text-ink">{article.ares_interpretation}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Tag tone={article.direction === "bullish" ? "bull" : article.direction === "bearish" ? "bear" : "muted"}>
              {article.ares_impact}
            </Tag>
            <Tag>{article.impact} IMPACT</Tag>
          </div>
        </section>

        {(article.symbols.length > 0 || article.currencies.length > 0) && (
          <section className="mt-6">
            <div className="label">Related instruments</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {article.symbols.map((symbol) => (
                <button
                  key={symbol}
                  onClick={() => void analyzeSymbol(symbol)}
                  className="btn h-8 text-[11.5px]"
                  title={`Open the ${symbol} analysis workspace`}
                >
                  Analyze {symbol} →
                </button>
              ))}
              {article.currencies.length > 0 && article.symbols.length === 0 && (
                <span className="text-[11.5px] text-faint">
                  Currencies mentioned: {article.currencies.join(", ")} — no single instrument identified.
                </span>
              )}
            </div>
          </section>
        )}

        {related.length > 0 && (
          <section className="mt-6">
            <div className="label">Related stories</div>
            <div className="divide-hair mt-2 overflow-hidden rounded-md border border-line">
              {related.map((item) => (
                <button
                  key={item.id}
                  onClick={() => openArticle(item.id)}
                  className="block w-full px-3 py-2.5 text-left transition-colors hover:bg-s2"
                >
                  <div className="flex items-center gap-2">
                    <span className="label !text-[9px]">{item.source}</span>
                    <span className="text-[10px] text-faint">{ago(item.published_at)}</span>
                  </div>
                  <p className="mt-0.5 text-[12px] leading-snug text-dim">{item.title}</p>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </article>
  );
}

function SourceHealth({ data }: { data: NewsResponse | null }) {
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const { sources, last_refresh } = data.status;
  const ok = sources.filter((s) => s.ok).length;

  return (
    <div className="border-t border-line px-4 py-2">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2 text-left">
        <span className="label">Sources</span>
        <span className={`text-[11px] ${ok ? "text-dim" : "text-offline"}`}>
          {ok}/{sources.length} reachable
        </span>
        {last_refresh && <span className="text-[10px] text-faint">· checked {ago(last_refresh)}</span>}
        <span className="ml-auto text-[10px] text-faint">{open ? "hide" : "detail"}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1">
          {sources.map((source) => (
            <div key={source.id} className="flex items-baseline gap-2 text-[10.5px]">
              <span className={`h-[5px] w-[5px] shrink-0 rounded-full ${source.ok ? "bg-online" : "bg-offline"}`} />
              <span className="text-dim">{source.name}</span>
              <span className="ml-auto text-right text-faint">
                {source.ok ? `${source.articles} stories` : (source.error ?? "not fetched")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CalendarStrip() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  useEffect(() => {
    void api.get<{ events: CalendarEvent[] }>("/api/calendar")
      .then((d) => setEvents(d.events)).catch(() => setEvents([]));
  }, []);
  if (events.length === 0) return null;
  return (
    <section className="panel">
      <PanelHeader dense>Economic Calendar</PanelHeader>
      <div className="divide-hair">
        {events.slice(0, 6).map((event) => (
          <div key={event.id} className="flex items-center gap-3 px-4 py-2">
            <span className="num text-[11px] text-faint">{clock(event.scheduled_at)}</span>
            <span className="num text-[11.5px] font-semibold">{event.currency}</span>
            <span className="truncate text-[11.5px] text-dim">{event.title}</span>
            <span className="ml-auto">
              <Tag tone={event.impact === "high" ? "warn" : "muted"}>{event.impact}</Tag>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function News() {
  const { newsCategory, setNewsCategory, selectedArticle, openArticle } = useAres();
  const [data, setData] = useState<NewsResponse | null>(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);

  const load = (category: string) => {
    const query = category === "ALL" ? "" : `?category=${encodeURIComponent(category)}`;
    void api.get<NewsResponse>(`/api/news${query}`)
      .then(setData)
      .catch(() => setData(null));
  };

  useEffect(() => {
    load(newsCategory);
    const id = setInterval(() => load(newsCategory), 60_000);
    return () => clearInterval(id);
  }, [newsCategory]);

  const refresh = async () => {
    setBusy(true);
    try {
      await api.post("/api/news/refresh");
      load(newsCategory);
    } catch { /* offline; status panel explains */ }
    setBusy(false);
  };

  const articles = useMemo(() => {
    const list = data?.articles ?? [];
    if (!search.trim()) return list;
    const needle = search.toLowerCase();
    return list.filter((a) =>
      a.title.toLowerCase().includes(needle) || a.summary.toLowerCase().includes(needle));
  }, [data, search]);

  const categories = data?.categories ?? ["ALL"];

  return (
    <div className="h-full">
      <div className="mx-auto grid h-full max-w-[1600px] grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,420px)_1fr]">
        {/* Feed column — full width on phones, a column beside the reader on desktop. */}
        <div className={`flex min-h-0 flex-col gap-4 ${selectedArticle ? "hidden lg:flex" : "flex"}`}>
          <section className="panel flex min-h-0 flex-1 flex-col">
            <PanelHeader
              right={
                <button onClick={() => void refresh()} disabled={busy} className="btn-quiet h-7 px-2 text-[11px]">
                  {busy ? "…" : "Refresh"}
                </button>
              }
            >
              Market News
            </PanelHeader>

            <div className="border-b border-line px-3 py-2">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search headlines…"
                className="field"
              />
              <div className="scroll-x mt-2 flex gap-1.5 pb-0.5">
                {categories.map((category) => (
                  <button
                    key={category}
                    onClick={() => setNewsCategory(category)}
                    className={`tag shrink-0 ${
                      newsCategory === category ? "!border-[var(--accent-line)] !bg-[var(--accent-dim)] !text-accent" : ""
                    }`}
                  >
                    {category}
                  </button>
                ))}
              </div>
            </div>

            <div className="divide-hair scroll-y min-h-0 flex-1">
              {articles.length === 0 ? (
                <Unavailable
                  what="News"
                  reason={
                    data?.message ??
                    "No stories match this filter."
                  }
                />
              ) : (
                articles.map((article) => (
                  <ArticleCard
                    key={article.id}
                    article={article}
                    active={selectedArticle === article.id}
                    onSelect={() => openArticle(article.id)}
                  />
                ))
              )}
            </div>

            <SourceHealth data={data} />
          </section>
        </div>

        {/* Reader column */}
        <div className={`min-h-0 ${selectedArticle ? "flex" : "hidden lg:flex"} flex-col gap-4`}>
          <section className="panel min-h-0 flex-1 overflow-hidden">
            {selectedArticle ? (
              <ArticleDetail id={selectedArticle} onClose={() => openArticle(null)} />
            ) : (
              <div className="flex h-full items-center justify-center">
                <p className="max-w-xs px-6 text-center text-[12px] leading-relaxed text-faint">
                  Select a story to read it, see ARES's interpretation, and jump straight
                  into the related instrument's analysis.
                </p>
              </div>
            )}
          </section>
          <CalendarStrip />
        </div>
      </div>
    </div>
  );
}
