"""RSS/Atom feed parsing and the ARES source registry.

Parsing uses the standard library only (no new dependency): both RSS 2.0 and
Atom are handled. Nothing here invents content — a feed that cannot be fetched
or parsed yields no articles and an explicit error on its source status.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

# Categories used across the API and the UI.
CATEGORIES = (
    "FOREX", "GOLD", "INDICES", "CRYPTO", "COMMODITIES",
    "ECONOMY", "CENTRAL BANKS", "MARKETS",
)


@dataclass(frozen=True)
class NewsSource:
    """A configured feed. `categories` is the default classification for its
    articles; per-article keyword tagging refines it."""

    id: str
    name: str
    url: str
    categories: tuple[str, ...]
    enabled: bool = True


# Public, widely syndicated financial feeds. These are fetched only when the
# host has outbound network access; ARES reports the truthful per-source state
# either way. Operators can add/replace sources via ARES_NEWS__EXTRA_FEEDS.
DEFAULT_SOURCES: tuple[NewsSource, ...] = (
    NewsSource("forexlive", "ForexLive", "https://www.forexlive.com/feed/news/", ("FOREX", "MARKETS")),
    NewsSource("fxstreet", "FXStreet", "https://www.fxstreet.com/rss/news", ("FOREX", "MARKETS")),
    NewsSource("investing-fx", "Investing.com FX", "https://www.investing.com/rss/news_1.rss", ("FOREX",)),
    NewsSource("investing-commodities", "Investing.com Commodities",
               "https://www.investing.com/rss/news_11.rss", ("COMMODITIES", "GOLD")),
    NewsSource("investing-economy", "Investing.com Economy",
               "https://www.investing.com/rss/news_14.rss", ("ECONOMY",)),
    NewsSource("marketwatch", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories",
               ("MARKETS", "INDICES")),
    NewsSource("cointelegraph", "Cointelegraph", "https://cointelegraph.com/rss", ("CRYPTO",)),
    NewsSource("cnbc-markets", "CNBC Markets",
               "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
               ("MARKETS", "ECONOMY")),
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw: str | None, limit: int = 400) -> str:
    """Strip markup/entities from feed-provided text. Content is only ever
    shortened here — never generated.

    Entities are unescaped before tags are stripped: feeds carry HTML either
    escaped (&lt;p&gt;) or as real markup, and unescaping first collapses both
    cases to one pass.
    """
    if not raw:
        return ""
    text = html.unescape(raw)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)  # entities that were double-escaped
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        return cut + "…"
    return text


# Feed-supplied URLs are untrusted input that ends up in an anchor href, so only
# real web schemes are ever accepted. A "javascript:" or "data:" link from a
# hostile or compromised feed would otherwise run in the ARES origin.
_SAFE_URL_SCHEMES = ("http://", "https://")


def safe_link(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = html.unescape(raw.strip())
    # Strip control characters and whitespace that browsers ignore but which can
    # disguise a scheme (e.g. "java\tscript:").
    candidate = "".join(ch for ch in candidate if ch.isprintable() and not ch.isspace())
    if not candidate.lower().startswith(_SAFE_URL_SCHEMES):
        return None
    return candidate


def parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    # RFC 822 (RSS)
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    # ISO 8601 (Atom)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _tag_name(element: ElementTree.Element) -> str:
    """Local tag name without the XML namespace."""
    return element.tag.rsplit("}", 1)[-1].lower()


def _find_text(item: ElementTree.Element, names: tuple[str, ...]) -> str | None:
    """Full text of the first matching child, including any inline markup's
    text. Real feeds routinely put <b>/<a> inside <description>, which the XML
    parser turns into child elements — reading only `.text` would silently
    truncate the summary at the first tag."""
    for child in item:
        if _tag_name(child) not in names:
            continue
        full = "".join(child.itertext())
        if full.strip():
            return full
    return None


def _find_link(item: ElementTree.Element) -> str | None:
    for child in item:
        if _tag_name(child) != "link":
            continue
        # Atom puts the URL in href; RSS in the element text.
        href = child.attrib.get("href")
        rel = child.attrib.get("rel", "alternate")
        if href and rel == "alternate" and (safe := safe_link(href)):
            return safe
        if safe := safe_link(child.text):
            return safe
    return safe_link(_find_text(item, ("guid", "id")))


@dataclass
class RawArticle:
    title: str
    link: str | None
    summary: str
    published: datetime | None
    categories: list[str] = field(default_factory=list)


def parse_feed(xml_text: str) -> list[RawArticle]:
    """Parse RSS 2.0 or Atom into RawArticles. Raises ElementTree.ParseError
    on malformed XML so the caller can record a truthful source error."""
    root = ElementTree.fromstring(xml_text)
    items: list[ElementTree.Element] = []
    for element in root.iter():
        if _tag_name(element) in ("item", "entry"):
            items.append(element)

    articles: list[RawArticle] = []
    for item in items:
        title = clean_text(_find_text(item, ("title",)), 240)
        if not title:
            continue
        summary = clean_text(
            _find_text(item, ("description", "summary", "content", "encoded")), 400
        )
        published = parse_datetime(
            _find_text(item, ("pubdate", "published", "updated", "date"))
        )
        cats = [
            clean_text(child.text, 40).upper()
            for child in item
            if _tag_name(child) == "category" and (child.text or "").strip()
        ]
        articles.append(RawArticle(
            title=title, link=_find_link(item), summary=summary,
            published=published, categories=cats,
        ))
    return articles
