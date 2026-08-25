"""News engine: feed parsing, classification, interpretation, honest offline."""

import pytest

from app.config import NewsSettings
from app.news.feeds import NewsSource, clean_text, parse_datetime, parse_feed
from app.news.service import NewsService, build_interpretation, classify

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Test Feed</title>
  <item>
    <title>Dollar strengthens ahead of key US inflation data</title>
    <link>https://example.com/a1</link>
    <description>&lt;p&gt;The US dollar <b>rises</b> as traders await CPI.&lt;/p&gt;</description>
    <pubDate>Mon, 25 Aug 2026 09:30:00 GMT</pubDate>
    <category>Forex</category>
  </item>
  <item>
    <title>Gold falls as yields climb</title>
    <link>https://example.com/a2</link>
    <description>Bullion slides in London trade.</description>
    <pubDate>Mon, 25 Aug 2026 08:00:00 GMT</pubDate>
  </item>
</channel></rss>"""

ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>ECB holds rates steady</title>
    <link rel="alternate" href="https://example.com/atom1"/>
    <summary>The European Central Bank kept its policy rate unchanged.</summary>
    <published>2026-08-25T07:15:00Z</published>
  </entry>
</feed>"""


def test_parse_rss():
    articles = parse_feed(RSS_SAMPLE)
    assert len(articles) == 2
    first = articles[0]
    assert first.title == "Dollar strengthens ahead of key US inflation data"
    assert first.link == "https://example.com/a1"
    assert "<p>" not in first.summary and "rises" in first.summary  # markup stripped
    assert first.published is not None and first.published.year == 2026
    assert first.categories == ["FOREX"]


def test_parse_atom():
    articles = parse_feed(ATOM_SAMPLE)
    assert len(articles) == 1
    assert articles[0].title == "ECB holds rates steady"
    assert articles[0].link == "https://example.com/atom1"
    assert articles[0].published is not None


def test_parse_malformed_raises():
    from xml.etree.ElementTree import ParseError

    with pytest.raises(ParseError):
        parse_feed("<rss><channel><item></channel>")


def test_clean_text_and_dates():
    assert clean_text("<b>Hello</b> &amp; welcome") == "Hello & welcome"
    assert clean_text("x" * 500, limit=50).endswith("…")
    assert parse_datetime("Mon, 25 Aug 2026 09:30:00 GMT") is not None
    assert parse_datetime("2026-08-25T07:15:00Z") is not None
    assert parse_datetime("nonsense") is None
    assert parse_datetime(None) is None


def test_classification_extracts_symbols_and_impact():
    categories, symbols, currencies, impact, direction = classify(
        "Dollar strengthens ahead of key US CPI inflation data",
        "The greenback rises as traders await the inflation report.",
        ("FOREX",), [],
    )
    assert "USD" in currencies
    assert impact in ("HIGH", "CRITICAL")
    assert direction == "bullish"
    assert "ECONOMY" in categories or "FOREX" in categories


def test_classification_gold_bearish():
    _, symbols, _, _, direction = classify(
        "Gold falls as yields climb", "Bullion slides.", ("COMMODITIES",), [])
    assert "XAUUSD" in symbols
    assert direction == "bearish"


def test_interpretation_is_labeled_as_ares_opinion():
    short, long_text = build_interpretation(
        "Dollar rises", "HIGH", "bullish", ["EURUSD"], ["USD"])
    assert "USD" in short
    assert "ARES's interpretation" in long_text
    assert "not a trade recommendation" in long_text


@pytest.mark.asyncio
async def test_service_reports_unreachable_sources_truthfully():
    """With an unroutable source the feed stays empty and the error is real."""
    service = NewsService(
        NewsSettings(fetch_timeout_seconds=2.0),
        sources=(NewsSource("dead", "Dead Feed", "https://127.0.0.1:9/none.rss", ("MARKETS",)),),
    )
    await service.refresh(force=True)
    assert service.articles == []
    status = service.status_payload()
    assert status["article_count"] == 0
    assert status["sources"][0]["ok"] is False
    assert status["sources"][0]["error"]

    from app.status import status_registry
    assert status_registry.get("news").state.value == "OFFLINE"
    assert "inventing" in status_registry.get("news").reason


@pytest.mark.asyncio
async def test_service_query_filters(monkeypatch):
    source = NewsSource("t", "Test", "https://example.com/f.rss", ("FOREX",))
    service = NewsService(NewsSettings(), sources=(source,))

    class FakeResponse:
        status_code = 200
        text = RSS_SAMPLE

    class FakeClient:
        async def get(self, url):
            return FakeResponse()

    articles = await service._fetch_source(FakeClient(), source)
    service._merge(articles)
    assert len(service.articles) == 2

    gold = service.query(symbol="XAUUSD")
    assert len(gold) == 1 and "Gold" in gold[0]["title"]
    assert service.query(search="inflation")
    assert service.query(category="FOREX")
    assert service.query(category="CRYPTO") == []

    article_id = service.articles[0].id
    assert service.get(article_id) is not None
    assert service.get("missing") is None
    # Related stories share categories/symbols.
    assert isinstance(service.related(article_id), list)


def test_news_endpoint_reports_no_fabrication(client_factory):
    """With no reachable feed the endpoint returns nothing and states why."""
    client = client_factory()
    body = client.get("/api/news").json()
    assert body["articles"] == []
    assert body["message"] and "No news available" in body["message"]
    # The reason must be a real explanation, not a placeholder.
    assert "disabled" in body["message"] or "unreachable" in body["message"]
    assert "ALL" in body["categories"]
    assert body["status"]["article_count"] == 0
