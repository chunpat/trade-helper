import asyncio
from datetime import datetime

from app.schemas.market_insight import MarketNews
from app.services.news_service import NewsService


def test_to_market_news_uses_description_and_default_source():
    service = NewsService()

    news = service._to_market_news(
        {
            "title": "Whales are quietly accumulating TRUMP as prices dip",
            "description": "Whales are buying Trump's memecoin TRUMP as prices continue to fall.",
            "published_at": "2026-03-12T16:28:44Z",
            "kind": "news",
        },
        asset_symbol="TRUMP",
    )

    assert news.source == "CryptoPanic"
    assert news.summary == "Whales are buying Trump's memecoin TRUMP as prices continue to fall."
    assert news.symbols == ["TRUMP"]


def test_filter_relevant_news_keeps_crypto_match_and_drops_false_positive():
    service = NewsService()
    news_items = [
        MarketNews(
            title="TRUMP meme coin retraces sharply as team moves 5 million tokens",
            source="CryptoPanic",
            summary="The memecoin saw heavy selling pressure after large token transfers.",
            published_at=datetime.utcnow(),
            symbols=["TRUMP"],
        ),
        MarketNews(
            title="Trump Says Oil Firms Should Use Strait of Hormuz Despite Fresh Shipping Attack",
            source="CryptoPanic",
            summary="A geopolitical headline about shipping routes and oil producers.",
            published_at=datetime.utcnow(),
            symbols=["TRUMP"],
        ),
    ]

    filtered = service._filter_relevant_news(news_items, "TRUMP")

    assert len(filtered) == 1
    assert filtered[0].title.startswith("TRUMP meme coin")


def test_to_market_news_from_brave_uses_hostname_and_description():
    service = NewsService()

    news = service._to_market_news_from_brave(
        {
            "title": "TRUMP token jumps after derivatives volume spikes",
            "description": "Brave result summary about TRUMP token trading activity.",
            "url": "https://www.reuters.com/markets/currencies/example-story",
            "meta_url": {"hostname": "www.reuters.com"},
            "page_age": "2026-03-12T16:28:44Z",
        },
        asset_symbol="TRUMP",
    )

    assert news.source == "www.reuters.com"
    assert news.source_domain == "reuters.com"
    assert news.summary == "Brave result summary about TRUMP token trading activity."
    assert news.symbols == ["TRUMP"]


def test_to_market_news_from_binance_article_extracts_symbols_and_source():
    service = NewsService()

    news = service._to_market_news_from_binance_article(
        {
            "title": "Binance Futures Will Launch USDⓈ-Margined KATUSDT Perpetual Contract Pre-Market Trading (2026-03-02)",
            "code": "article-code",
            "releaseDate": 1773366336337,
            "shortLink": None,
            "body": None,
        },
        "New Cryptocurrency Listing",
    )

    assert news is not None
    assert news.source == "Binance Announcements"
    assert news.source_domain == "binance.com"
    assert news.symbols == ["KAT"]
    assert news.url.endswith("article-code")


def test_fetch_primary_news_pool_combines_rss_and_binance_sources(monkeypatch):
    service = NewsService()
    service.enable_okx_announcements = False
    service.enable_bybit_announcements = False
    service.enable_coinbase_blog = False

    async def fake_rss(limit):
        return [
            MarketNews(
                title="TRUMP token rises on fresh derivatives demand",
                source="CoinDesk RSS",
                source_domain="coindesk.com",
                summary="TRUMP token sees rising crypto demand.",
                published_at=datetime(2026, 3, 14, 12, 0, 0),
                url="https://www.coindesk.com/example",
                symbols=["TRUMP"],
            )
        ]

    async def fake_binance(limit):
        return [
            MarketNews(
                title="Binance Will List Katana (KAT) with Seed Tag Applied",
                source="Binance Announcements",
                source_domain="binance.com",
                summary="New Cryptocurrency Listing",
                published_at=datetime(2026, 3, 14, 13, 0, 0),
                url="https://www.binance.com/en/support/announcement/detail/article-code",
                symbols=["KAT"],
            )
        ]

    service._fetch_rss_pool = fake_rss
    service._fetch_binance_announcements = fake_binance

    items = asyncio.run(service._fetch_primary_news_pool(limit=10))

    assert len(items) == 2
    assert items[0].source_domain == "binance.com"
    assert items[1].source_domain == "coindesk.com"


def test_fetch_symbol_news_uses_brave_when_primary_provider_has_no_results(monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "auto")
    service = NewsService()

    async def fake_pool(limit):
        return []

    async def fake_cryptopanic(asset_symbol=None, limit=10):
        return []

    async def fake_brave(asset_symbol=None, limit=10):
        assert asset_symbol == "TRUMP"
        return [
            {
                "title": "TRUMP token rallies as futures open interest surges",
                "description": "TRUMP crypto traders are reacting to a sharp rise in derivatives activity.",
                "url": "https://www.coindesk.com/markets/2026/03/12/trump-token-rallies",
                "meta_url": {"hostname": "www.coindesk.com"},
                "page_age": "2026-03-12T16:28:44Z",
            }
        ]

    service._get_global_news_pool = fake_pool
    service._request_cryptopanic_news = fake_cryptopanic
    service._request_brave_news = fake_brave

    news_items = asyncio.run(service.fetch_symbol_news("TRUMPUSDT", limit=3))

    assert len(news_items) == 1
    assert news_items[0].source_domain == "coindesk.com"
    assert news_items[0].title.startswith("TRUMP token rallies")


def test_fetch_symbol_news_prefers_global_rss_pool_before_brave(monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "auto")
    service = NewsService()

    async def fake_pool(limit):
        assert limit >= 24
        return [
            MarketNews(
                title="Official Trump token surges as open interest explodes",
                source="CoinDesk RSS",
                source_domain="coindesk.com",
                summary="TRUMP token sees heavy crypto derivatives activity.",
                published_at=datetime(2026, 3, 14, 12, 0, 0),
                url="https://www.coindesk.com/example",
                symbols=[],
            )
        ]

    async def fail_brave(*args, **kwargs):
        raise AssertionError("brave fallback should not be called when rss pool already matches")

    service._get_global_news_pool = fake_pool
    service._request_brave_news = fail_brave
    service._request_cryptopanic_news = fail_brave

    news_items = asyncio.run(service.fetch_symbol_news("TRUMPUSDT", limit=3))

    assert len(news_items) == 1
    assert news_items[0].source_domain == "coindesk.com"


def test_fetch_symbol_news_caches_fallback_search_results(monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "auto")
    service = NewsService()
    brave_calls = {"count": 0}

    async def fake_pool(limit):
        return []

    async def fake_cryptopanic(asset_symbol=None, limit=10):
        return []

    async def fake_brave(asset_symbol=None, limit=10):
        brave_calls["count"] += 1
        return [
            {
                "title": "TRUMP token rallies as derivatives positions build",
                "description": "TRUMP crypto traders are reacting to a sharp rise in futures demand.",
                "url": "https://www.coindesk.com/markets/2026/03/12/trump-token-rallies",
                "meta_url": {"hostname": "www.coindesk.com"},
                "page_age": "2026-03-12T16:28:44Z",
            }
        ]

    service._get_global_news_pool = fake_pool
    service._request_cryptopanic_news = fake_cryptopanic
    service._request_brave_news = fake_brave

    first_items = asyncio.run(service.fetch_symbol_news("TRUMPUSDT", limit=3))
    second_items = asyncio.run(service.fetch_symbol_news("TRUMPUSDT", limit=3))

    assert brave_calls["count"] == 1
    assert len(first_items) == 1
    assert len(second_items) == 1


def test_parse_rss_feed_returns_market_news_items():
        service = NewsService()
        pub_date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        xml_text = f"""
        <rss version="2.0">
            <channel>
                <title>CoinDesk</title>
                <item>
                    <title>TRUMP token jumps after fresh market frenzy</title>
                    <link>https://www.coindesk.com/markets/2026/03/14/trump-token-jumps</link>
                    <description><![CDATA[TRUMP crypto traders are chasing a fresh breakout.]]></description>
                    <pubDate>{pub_date}</pubDate>
                </item>
            </channel>
        </rss>
        """

        news_items = service._parse_rss_feed(xml_text, "https://www.coindesk.com/arc/outboundfeeds/rss/")

        assert len(news_items) == 1
        assert news_items[0].source == "CoinDesk"
        assert news_items[0].source_domain == "coindesk.com"
        assert news_items[0].summary == "TRUMP crypto traders are chasing a fresh breakout."


def test_parse_okx_announcements_page_extracts_recent_items():
    service = NewsService()
    today = datetime.utcnow().strftime("%b %d, %Y")
    yesterday = datetime.utcnow().replace(day=max(datetime.utcnow().day - 1, 1)).strftime("%b %d, %Y")
    html_text = """
    <ul>
        <li class="index_articleItem__d-8iK">
            <a href="/help/okx-to-list-pre-market-perpetual-futures-for-kat-katana-crypto">
                <div class="index_title__iTmos index_articleTitle__ys7G7">OKX to list pre-market perpetual futures for KAT (Katana) crypto</div>
                <div><span>Published on {today}</span></div>
            </a>
        </li>
        <li class="index_articleItem__d-8iK">
            <a href="/help/okx-to-list-perpetual-futures-for-robo-crypto">
                <div class="index_title__iTmos index_articleTitle__ys7G7">OKX to list perpetual futures for ROBO crypto</div>
                <div><span>Published on {yesterday}</span></div>
            </a>
        </li>
    </ul>
    """.format(today=today, yesterday=yesterday)

    news_items = service._parse_okx_announcements_page(
        html_text,
        "https://www.okx.com/help/section/announcements-new-listings",
    )

    assert len(news_items) == 2
    assert news_items[0].source == "OKX Announcements"
    assert news_items[0].symbols == ["KAT"]
    assert news_items[1].url.endswith("okx-to-list-perpetual-futures-for-robo-crypto")


def test_parse_bybit_announcements_page_keeps_relevant_categories_only():
    service = NewsService()
    html_text = """
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "articleInitEntity": {
            "list": [
              {
                "title": "Bybit to Support ValueChain (SOSO) Network Upgrade",
                "description": "Maintenance notice for SOSO holders.",
                "category": {"title": "Maintenance Updates", "key": "maintenance_updates"},
                "url": "/article/bybit-to-support-valuechain-soso-network-upgrade/",
                "publish_time": 1773366336
              },
              {
                "title": "Golden Month Giveaway: Trade to share $1,000,000",
                "description": "Promotional activity.",
                "category": {"title": "Latest Activities", "key": "latest_activities"},
                "url": "/article/golden-month-giveaway/",
                "publish_time": 1773366336
              }
            ]
          }
        }
      }
    }
    </script>
    """

    news_items = service._parse_bybit_announcements_page(html_text, "https://announcements.bybit.com/en-US/")

    assert len(news_items) == 1
    assert news_items[0].source == "Bybit Announcements"
    assert news_items[0].symbols == ["SOSO"]
    assert news_items[0].summary == "Maintenance Updates"


def test_parse_coinbase_blog_landing_page_keeps_market_posts_only():
    service = NewsService()
    today = datetime.utcnow().strftime("%b %d, %Y")
    html_text = """
    <div>
        <a data-testid="blog-search-results-article-card-link-overlay" aria-label="Futures Contracts Now Available on Coinbase in Europe" href="/blog/futures-contracts-europe"></a>
        <span>{today}</span>
        <div data-testid="blog-search-results-article-card-paragraph"><p>TLDR: European traders can now access futures contracts for the first time on Coinbase.</p></div>
    </div>
    <div>
        <a data-testid="blog-search-results-article-card-link-overlay" aria-label="Reducing Fraud Loss With an Automated Dynamic Policy" href="/blog/reducing-fraud-loss-with-an-automated-dynamic-policy"></a>
        <span>{today}</span>
        <div data-testid="blog-search-results-article-card-paragraph"><p>Dynamic controls for fraud and risk systems.</p></div>
    </div>
    """.format(today=today)

    news_items = service._parse_coinbase_blog_landing_page(html_text, "https://www.coinbase.com/blog/landing")

    assert len(news_items) == 1
    assert news_items[0].source == "Coinbase Blog"
    assert news_items[0].url == "https://www.coinbase.com/blog/futures-contracts-europe"


def test_filter_relevant_news_accepts_official_network_upgrade_announcements():
    service = NewsService()
    news_items = [
        MarketNews(
            title="Bybit to Support ValueChain (SOSO) Network Upgrade",
            source="Bybit Announcements",
            source_domain="bybit.com",
            summary="Maintenance Updates",
            published_at=datetime.utcnow(),
            symbols=["SOSO"],
        )
    ]

    filtered = service._filter_relevant_news(news_items, "SOSO")

    assert len(filtered) == 1
    assert filtered[0].title.startswith("Bybit to Support ValueChain")


def test_fetch_symbol_official_feed_news_returns_recent_items_even_without_ticker_match(monkeypatch):
    monkeypatch.setenv("NEWS_SYMBOL_OFFICIAL_FEEDS", '{"KAT": ["https://medium.com/feed/@katana"]}')
    service = NewsService()

    async def fake_fetch_rss_responses(client, feed_urls=None):
        return [("https://medium.com/feed/@katana", "<rss />")]

    def fake_parse_rss_feed(xml_text, feed_url):
        return [
            MarketNews(
                title="Katana mainnet launch is live",
                source="Katana Blog",
                source_domain="medium.com",
                summary="Official launch update from the Katana team.",
                published_at=datetime.utcnow(),
                url="https://medium.com/@katana/mainnet-launch",
                symbols=[],
            )
        ]

    service._fetch_rss_responses = fake_fetch_rss_responses
    service._parse_rss_feed = fake_parse_rss_feed

    news_items = asyncio.run(service._fetch_symbol_official_feed_news("KAT", limit=3))

    assert len(news_items) == 1
    assert news_items[0].source == "Katana Blog"