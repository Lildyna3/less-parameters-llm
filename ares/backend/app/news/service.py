"""ARES news service: fetch, classify, and interpret real market news.

Guarantees:
  * Headlines, summaries, sources and timestamps come verbatim from the feed.
    Nothing is generated. If no source can be reached, the feed is empty and
    the UI is told exactly why (per-source error strings).
  * ARES's own interpretation is clearly separated from source content: it
    lives under `ares_impact` / `ares_interpretation` and is derived from
    measurable keyword evidence plus (when available) the deterministic
    analysis engine — never from an invented article body.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from ..config import NewsSettings
from ..logging_setup import get_logger
from ..status import ComponentState, status_registry
from .feeds import CATEGORIES, DEFAULT_SOURCES, NewsSource, parse_feed

log = get_logger("news")

USER_AGENT = "ARES/1.0 (+trading-intelligence; RSS reader)"

# Hard ceiling on a single feed response.
MAX_FEED_BYTES = 4 * 1024 * 1024

# Instrument keyword map. Matching is word-boundary aware and case-insensitive.
SYMBOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "EURUSD": ("eurusd", "eur/usd", "euro", "ecb", "eurozone", "euro zone"),
    "GBPUSD": ("gbpusd", "gbp/usd", "sterling", "pound", "boe", "bank of england", "cable"),
    "USDJPY": ("usdjpy", "usd/jpy", "yen", "boj", "bank of japan"),
    "USDCHF": ("usdchf", "usd/chf", "franc", "snb"),
    "AUDUSD": ("audusd", "aud/usd", "aussie", "australian dollar", "rba"),
    "NZDUSD": ("nzdusd", "nzd/usd", "kiwi", "new zealand dollar", "rbnz"),
    "USDCAD": ("usdcad", "usd/cad", "loonie", "canadian dollar", "boc"),
    "XAUUSD": ("xauusd", "gold", "bullion", "precious metal"),
    "XAGUSD": ("xagusd", "silver"),
    "BTCUSD": ("bitcoin", "btc", "crypto", "cryptocurrency"),
    "ETHUSD": ("ethereum", "ether", "eth"),
    "US500": ("s&p 500", "s&p500", "sp500", "wall street", "us stocks", "nasdaq", "dow"),
}

CURRENCY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "USD": ("dollar", "usd", "fed", "federal reserve", "fomc", "powell", "treasury"),
    "EUR": ("euro", "eur", "ecb", "lagarde", "eurozone"),
    "GBP": ("pound", "sterling", "gbp", "boe"),
    "JPY": ("yen", "jpy", "boj"),
    "CHF": ("franc", "chf", "snb"),
    "AUD": ("aussie", "aud", "rba"),
    "CAD": ("loonie", "cad", "boc"),
    "NZD": ("kiwi", "nzd", "rbnz"),
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CENTRAL BANKS": ("fed", "fomc", "ecb", "boe", "boj", "rba", "rbnz", "snb", "boc",
                      "central bank", "rate decision", "interest rate", "powell", "lagarde"),
    "ECONOMY": ("cpi", "inflation", "gdp", "nfp", "payrolls", "unemployment", "pmi",
                "retail sales", "jobless", "economic", "recession"),
    "GOLD": ("gold", "bullion", "xau"),
    "CRYPTO": ("bitcoin", "crypto", "ethereum", "btc", "eth", "blockchain"),
    "FOREX": ("forex", "currency", "dollar", "euro", "yen", "sterling", "fx"),
    "INDICES": ("s&p", "nasdaq", "dow", "index", "stocks", "equities", "shares"),
    "COMMODITIES": ("oil", "crude", "brent", "wti", "natural gas", "copper", "commodity"),
}

# Impact scoring: high-signal event words carry more weight.
CRITICAL_TERMS = ("emergency", "war", "invasion", "default", "collapse", "crisis",
                  "shock", "intervention", "halt trading", "circuit breaker")
HIGH_TERMS = ("fomc", "rate decision", "cpi", "inflation report", "nfp", "non-farm",
              "payrolls", "central bank", "gdp", "powell", "lagarde", "rate hike",
              "rate cut", "unemployment rate")
MODERATE_TERMS = ("pmi", "retail sales", "consumer confidence", "trade balance",
                  "jobless claims", "housing", "earnings", "forecast", "outlook")

BULLISH_TERMS = ("rises", "rally", "surges", "gains", "strengthens", "jumps", "climbs",
                 "boosts", "hawkish", "beats", "stronger", "higher", "soars", "advance")
BEARISH_TERMS = ("falls", "drops", "slides", "weakens", "plunges", "slumps", "declines",
                 "dovish", "misses", "weaker", "lower", "tumbles", "retreats", "sinks")


def _contains(text: str, terms: tuple[str, ...]) -> list[str]:
    return [t for t in terms if t in text]



def build_sources(settings: NewsSettings) -> tuple[NewsSource, ...]:
    """Built-in feeds plus any the operator configured. A malformed entry is
    skipped with a log line rather than taking the whole service down."""
    configured: list[NewsSource] = []
    for entry in settings.extra_feeds:
        try:
            configured.append(NewsSource(
                id=str(entry["id"]),
                name=str(entry.get("name", entry["id"])),
                url=str(entry["url"]),
                categories=tuple(str(c).upper() for c in entry.get("categories", ("MARKETS",))),
                enabled=bool(entry.get("enabled", True)),
            ))
        except (KeyError, TypeError) as exc:
            log.warning("ignoring malformed news feed entry %r: %s", entry, exc)

    if settings.replace_default_feeds:
        return tuple(configured)
    # Configured feeds win on id collisions with a built-in.
    by_id = {source.id: source for source in DEFAULT_SOURCES}
    for source in configured:
        by_id[source.id] = source
    return tuple(by_id.values())


@dataclass
class NewsArticle:
    id: str
    title: str                     # verbatim from source
    summary: str                   # verbatim from source (trimmed)
    source: str
    source_id: str
    url: str | None
    published_at: str              # ISO UTC
    categories: list[str]
    symbols: list[str]
    currencies: list[str]
    impact: str                    # LOW | MODERATE | HIGH | CRITICAL
    ares_impact: str               # short ARES read, e.g. "Moderate bullish USD"
    ares_interpretation: str       # longer ARES read; clearly ARES's own words
    direction: str                 # bullish | bearish | neutral (ARES's read)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class SourceStatus:
    id: str
    name: str
    ok: bool = False
    articles: int = 0
    error: str | None = None
    last_attempt: str | None = None
    last_success: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def classify(title: str, summary: str, source_categories: tuple[str, ...],
             feed_categories: list[str]) -> tuple[list[str], list[str], list[str], str, str]:
    """Derive categories, symbols, currencies, impact and direction from the
    article's own text. Deterministic and inspectable."""
    text = f"{title} {summary}".lower()

    symbols = [
        symbol for symbol, words in SYMBOL_KEYWORDS.items()
        if any(w in text for w in words)
    ]
    currencies = [
        code for code, words in CURRENCY_KEYWORDS.items()
        if any(w in text for w in words)
    ]

    categories = {c for c in source_categories}
    for category, words in CATEGORY_KEYWORDS.items():
        if any(w in text for w in words):
            categories.add(category)
    for raw in feed_categories:
        upper = raw.upper()
        if upper in CATEGORIES:
            categories.add(upper)
    if not categories:
        categories = {"MARKETS"}

    if _contains(text, CRITICAL_TERMS):
        impact = "CRITICAL"
    elif _contains(text, HIGH_TERMS):
        impact = "HIGH"
    elif _contains(text, MODERATE_TERMS):
        impact = "MODERATE"
    else:
        impact = "LOW"

    bulls = len(_contains(text, BULLISH_TERMS))
    bears = len(_contains(text, BEARISH_TERMS))
    direction = "bullish" if bulls > bears else "bearish" if bears > bulls else "neutral"

    ordered = [c for c in CATEGORIES if c in categories]
    return ordered, symbols, currencies, impact, direction


def build_interpretation(title: str, impact: str, direction: str,
                         symbols: list[str], currencies: list[str]) -> tuple[str, str]:
    """ARES's own reading of the headline — explicitly separated from source
    content and phrased as an assessment, not as fact."""
    # The direction was derived from the headline's own verbs, so the subject
    # must be what the headline is about. A named instrument wins over a
    # currency that merely appears in passing: "Gold falls as yields climb"
    # is bearish XAUUSD, not bearish USD.
    subject = symbols[0] if symbols else (currencies[0] if currencies else "the market")
    label_direction = direction if direction != "neutral" else "mixed"
    short = f"{impact.capitalize()} {label_direction} {subject}".replace("Low", "Low-impact")

    if direction == "neutral":
        lead = f"No clear directional bias for {subject} from this headline alone."
    else:
        lead = (f"Potentially {direction} for {subject} in the short term "
                f"if the market takes the headline at face value.")

    detail = []
    if impact in ("HIGH", "CRITICAL"):
        detail.append("This is a high-attention event type; expect wider spreads and "
                      "faster moves around related instruments.")
    elif impact == "MODERATE":
        detail.append("Moderate event type — usually a secondary driver rather than a "
                      "primary one.")
    else:
        detail.append("Low measured impact; treat as context rather than a trigger.")

    if symbols:
        detail.append(f"Most directly relevant instruments: {', '.join(symbols[:4])}.")
    detail.append("This is ARES's interpretation of the headline, not a claim from the "
                  "source and not a trade recommendation. Confirm against live structure "
                  "before acting.")
    return short, f"{lead} " + " ".join(detail)


class NewsService:
    """Fetches configured feeds on an interval, classifies articles, and keeps
    a truthful per-source status. Never fabricates."""

    def __init__(self, settings: NewsSettings, sources: tuple[NewsSource, ...] | None = None) -> None:
        self.settings = settings
        self.sources = sources if sources is not None else build_sources(settings)
        self.articles: list[NewsArticle] = []
        self.source_status: dict[str, SourceStatus] = {
            s.id: SourceStatus(id=s.id, name=s.name) for s in self.sources
        }
        self.last_refresh: str | None = None
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None
        self._refreshing = asyncio.Lock()
        self._last_attempt_monotonic = 0.0
        status_registry.set(
            "news", ComponentState.OFFLINE,
            "News feed starting — no sources fetched yet."
            if settings.news_feed_enabled else
            "News feed disabled in configuration.",
        )

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        if not self.settings.news_feed_enabled:
            status_registry.set(
                "news", ComponentState.OFFLINE,
                "News feed disabled in configuration (ARES_NEWS__NEWS_FEED_ENABLED=false).",
            )
            return
        self._task = asyncio.create_task(self._loop(), name="news-refresh")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - loop must survive
                log.error("news refresh failed: %s", exc)
            await asyncio.sleep(max(60, self.settings.refresh_interval_seconds))

    # -- fetching ----------------------------------------------------------

    async def refresh(self, force: bool = False) -> dict:
        """Fetch every enabled source concurrently. Returns a status summary."""
        if self._refreshing.locked() and not force:
            return self.status_payload()
        async with self._refreshing:
            # Request de-duplication: ignore rapid repeat refreshes.
            now = time.monotonic()
            if not force and now - self._last_attempt_monotonic < 30:
                return self.status_payload()
            self._last_attempt_monotonic = now

            enabled = [s for s in self.sources if s.enabled]
            timeout = httpx.Timeout(self.settings.fetch_timeout_seconds)
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                results = await asyncio.gather(
                    *(self._fetch_source(client, source) for source in enabled),
                    return_exceptions=True,
                )

            collected: list[NewsArticle] = []
            for source, result in zip(enabled, results):
                if isinstance(result, BaseException):
                    self._record_failure(source, f"{type(result).__name__}: {result}")
                else:
                    collected.extend(result)

            if collected:
                self._merge(collected)
                self.last_refresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self.last_error = None
            self._publish_status()
            return self.status_payload()

    async def _fetch_source(self, client: httpx.AsyncClient, source: NewsSource) -> list[NewsArticle]:
        status = self.source_status[source.id]
        status.last_attempt = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            # Streamed with a hard byte cap: a feed is untrusted input, and an
            # unbounded body could exhaust memory.
            async with client.stream("GET", source.url) as resp:
                if resp.status_code != 200:
                    self._record_failure(source, f"HTTP {resp.status_code}")
                    return []
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_FEED_BYTES:
                        self._record_failure(
                            source, f"feed exceeded {MAX_FEED_BYTES // 1024} KiB limit")
                        return []
                    chunks.append(chunk)
            body = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - network reality, reported truthfully
            self._record_failure(source, f"unreachable: {type(exc).__name__}")
            return []

        try:
            raw_articles = parse_feed(body)
        except Exception as exc:  # noqa: BLE001
            self._record_failure(source, f"unparseable feed: {type(exc).__name__}")
            return []

        articles: list[NewsArticle] = []
        for raw in raw_articles:
            categories, symbols, currencies, impact, direction = classify(
                raw.title, raw.summary, source.categories, raw.categories
            )
            short, interpretation = build_interpretation(
                raw.title, impact, direction, symbols, currencies
            )
            published = raw.published or datetime.now(timezone.utc)
            articles.append(NewsArticle(
                id=hashlib.sha256(
                    (raw.link or raw.title).encode("utf-8", "ignore")
                ).hexdigest()[:16],
                title=raw.title,
                summary=raw.summary,
                source=source.name,
                source_id=source.id,
                url=raw.link,
                published_at=published.astimezone(timezone.utc).isoformat(timespec="seconds"),
                categories=categories,
                symbols=symbols,
                currencies=currencies,
                impact=impact,
                ares_impact=short,
                ares_interpretation=interpretation,
                direction=direction,
            ))

        status.ok = True
        status.error = None
        status.articles = len(articles)
        status.last_success = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return articles

    def _record_failure(self, source: NewsSource, error: str) -> None:
        status = self.source_status[source.id]
        status.ok = False
        status.error = error
        status.articles = 0
        log.info("news source %s unavailable: %s", source.id, error)

    def _merge(self, incoming: list[NewsArticle]) -> None:
        by_id = {a.id: a for a in self.articles}
        for article in incoming:
            by_id[article.id] = article
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        merged = []
        for article in by_id.values():
            try:
                when = datetime.fromisoformat(article.published_at)
            except ValueError:
                continue
            if when >= cutoff:
                merged.append(article)
        merged.sort(key=lambda a: a.published_at, reverse=True)
        self.articles = merged[: self.settings.max_articles]

    # -- status / queries ---------------------------------------------------

    def _publish_status(self) -> None:
        ok_sources = [s for s in self.source_status.values() if s.ok]
        total = len([s for s in self.sources if s.enabled])
        if ok_sources and len(ok_sources) == total:
            status_registry.set("news", ComponentState.ONLINE,
                                f"{len(self.articles)} articles from {len(ok_sources)} source(s)",
                                {"sources_ok": len(ok_sources), "sources_total": total})
        elif ok_sources:
            status_registry.set("news", ComponentState.DEGRADED,
                                f"{len(ok_sources)}/{total} sources reachable",
                                {"sources_ok": len(ok_sources), "sources_total": total})
        else:
            errors = {s.error for s in self.source_status.values() if s.error}
            reason = ("No news source could be reached from this host. "
                      "This is a network/egress limitation, not an ARES failure — "
                      "no headlines are shown rather than inventing any.")
            status_registry.set("news", ComponentState.OFFLINE, reason,
                                {"sources_ok": 0, "sources_total": total,
                                 "errors": sorted(errors)[:4]})

    def status_payload(self) -> dict:
        return {
            "sources": [s.as_dict() for s in self.source_status.values()],
            "article_count": len(self.articles),
            "last_refresh": self.last_refresh,
            "enabled": self.settings.news_feed_enabled,
        }

    def query(self, category: str | None = None, symbol: str | None = None,
              impact: str | None = None, search: str | None = None,
              limit: int = 60) -> list[dict]:
        items = self.articles
        if category and category.upper() != "ALL":
            wanted = category.upper()
            items = [a for a in items if wanted in a.categories]
        if symbol:
            wanted_symbol = symbol.upper()
            items = [a for a in items if wanted_symbol in a.symbols]
        if impact:
            wanted_impact = impact.upper()
            items = [a for a in items if a.impact == wanted_impact]
        if search:
            needle = search.lower()
            items = [a for a in items
                     if needle in a.title.lower() or needle in a.summary.lower()]
        return [a.as_dict() for a in items[:limit]]

    def get(self, article_id: str) -> dict | None:
        for article in self.articles:
            if article.id == article_id:
                return article.as_dict()
        return None

    def related(self, article_id: str, limit: int = 5) -> list[dict]:
        target = next((a for a in self.articles if a.id == article_id), None)
        if target is None:
            return []
        scored = []
        for other in self.articles:
            if other.id == target.id:
                continue
            score = len(set(other.symbols) & set(target.symbols)) * 2
            score += len(set(other.categories) & set(target.categories))
            if score:
                scored.append((score, other))
        scored.sort(key=lambda pair: (-pair[0], pair[1].published_at))
        return [a.as_dict() for _, a in scored[:limit]]
