import asyncio
import logging
import os
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from app.schemas.market_insight import MarketNews

logger = logging.getLogger(__name__)


class NewsService:
    PROVIDER_AUTO = "auto"
    PROVIDER_BRAVE = "brave"
    PROVIDER_CRYPTOPANIC = "cryptopanic"
    BINANCE_ANNOUNCEMENT_SOURCE = "Binance Announcements"
    BINANCE_ANNOUNCEMENT_DOMAIN = "binance.com"
    OKX_ANNOUNCEMENT_SOURCE = "OKX Announcements"
    OKX_ANNOUNCEMENT_DOMAIN = "okx.com"
    BYBIT_ANNOUNCEMENT_SOURCE = "Bybit Announcements"
    BYBIT_ANNOUNCEMENT_DOMAIN = "bybit.com"
    COINBASE_BLOG_SOURCE = "Coinbase Blog"
    COINBASE_BLOG_DOMAIN = "coinbase.com"
    BINANCE_ANNOUNCEMENT_DETAIL_URL = "https://www.binance.com/en/support/announcement/detail/{code}"
    BINANCE_MARKET_HINT_WORDS = (
        "list",
        "listing",
        "launch",
        "launchpool",
        "futures",
        "margin",
        "spot",
        "trading pairs",
        "contract",
        "airdrop",
        "earn",
        "convert",
        "delist",
    )

    OFFICIAL_MARKET_HINT_WORDS = BINANCE_MARKET_HINT_WORDS + (
        "support",
        "upgrade",
        "network",
        "trade",
        "trading",
        "contracts",
        "derivatives",
        "institutional",
        "market",
        "prime",
    )

    PAGE_FETCH_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }

    BYBIT_ALWAYS_RELEVANT_CATEGORY_KEYS = {
        "new_crypto",
        "delistings",
        "maintenance_updates",
    }

    BYBIT_CONDITIONAL_CATEGORY_KEYS = {
        "latest_bybit_news",
        "Partnership_Announcement",
        "Listing Billboard",
    }

    PANEWS_NEWSFLASH_RSS_URL = "https://www.panewslab.com/zh/rss/newsflash.xml"

    SYMBOL_STOP_WORDS = {
        "APR",
        "BUSD",
        "BYBIT",
        "COINBASE",
        "OKX",
        "USDC",
        "USDT",
        "USD",
        "UTC",
    }

    DEFAULT_RSS_FEED_URLS = (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        PANEWS_NEWSFLASH_RSS_URL,
        "https://decrypt.co/feed",
        "https://blockworks.co/feed",
        "https://www.theblock.co/rss.xml",
        "https://cryptoslate.com/feed/",
        "https://bitcoinmagazine.com/feed",
        "https://thedefiant.io/feed",
        "https://ambcrypto.com/feed/",
        "https://coingape.com/feed/",
        "https://news.bitcoin.com/feed/",
    )

    DEFAULT_SYMBOL_ALIAS_MAP = {
        "TRUMP": ["official trump", "trump token", "trump memecoin", "world liberty financial"],
        "PIXEL": ["pixels", "pixels token"],
        "BNX": ["binaryx", "four token", "four meme"],
    }

    CRYPTO_HINT_WORDS = (
        "crypto",
        "token",
        "coin",
        "memecoin",
        "blockchain",
        "onchain",
        "wallet",
        "listing",
        "exchange",
        "binance",
        "futures",
        "spot",
        "trading",
        "market",
        "price",
        "usdt",
    )

    def __init__(self):
        self.provider = os.getenv("NEWS_PROVIDER", self.PROVIDER_AUTO).strip().lower() or self.PROVIDER_AUTO
        if self.provider not in {self.PROVIDER_AUTO, self.PROVIDER_BRAVE, self.PROVIDER_CRYPTOPANIC}:
            logger.warning("news-service: unsupported NEWS_PROVIDER=%s, fallback to auto", self.provider)
            self.provider = self.PROVIDER_AUTO

        self.api_key = os.getenv("NEWS_API_KEY", "").strip()
        self.base_url = os.getenv(
            "NEWS_API_BASE_URL",
            "https://cryptopanic.com/api/developer/v2/posts/"
        ).rstrip("/") + "/"
        self.timeout = float(os.getenv("NEWS_API_TIMEOUT_SECONDS", "12"))
        self.enable_binance_announcements = self._read_bool_env("NEWS_ENABLE_BINANCE_ANNOUNCEMENTS", True)
        self.binance_article_list_url = os.getenv(
            "NEWS_BINANCE_ARTICLE_LIST_URL",
            "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query",
        ).strip()
        self.binance_article_page_size = int(os.getenv("NEWS_BINANCE_ARTICLE_PAGE_SIZE", "3"))
        self.binance_catalog_limit = int(os.getenv("NEWS_BINANCE_CATALOG_LIMIT", "8"))
        self.enable_okx_announcements = self._read_bool_env("NEWS_ENABLE_OKX_ANNOUNCEMENTS", True)
        self.okx_announcements_url = os.getenv(
            "NEWS_OKX_ANNOUNCEMENTS_URL",
            "https://www.okx.com/help/section/announcements-new-listings",
        ).strip()
        self.enable_bybit_announcements = self._read_bool_env("NEWS_ENABLE_BYBIT_ANNOUNCEMENTS", True)
        self.bybit_announcements_url = os.getenv(
            "NEWS_BYBIT_ANNOUNCEMENTS_URL",
            "https://announcements.bybit.com/en-US/",
        ).strip()
        self.enable_coinbase_blog = self._read_bool_env("NEWS_ENABLE_COINBASE_BLOG", True)
        self.coinbase_blog_url = os.getenv(
            "NEWS_COINBASE_BLOG_URL",
            "https://www.coinbase.com/blog/landing",
        ).strip()
        self.official_page_item_limit = int(os.getenv("NEWS_OFFICIAL_PAGE_ITEM_LIMIT", "12"))
        self.brave_api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        self.brave_base_url = os.getenv(
            "BRAVE_SEARCH_BASE_URL",
            "https://api.search.brave.com/res/v1"
        ).rstrip("/")
        self.brave_freshness = os.getenv("BRAVE_NEWS_FRESHNESS", "pd").strip() or "pd"
        self.rss_feed_urls = self._load_rss_feed_urls()
        self.rss_cache_seconds = int(os.getenv("NEWS_RSS_CACHE_SECONDS", "180"))
        self.rss_per_feed_limit = int(os.getenv("NEWS_RSS_PER_FEED_LIMIT", "12"))
        self.global_pool_size = int(os.getenv("NEWS_GLOBAL_POOL_SIZE", "80"))
        self.search_cache_seconds = int(os.getenv("NEWS_SEARCH_CACHE_SECONDS", "600"))
        self.empty_search_cache_seconds = int(os.getenv("NEWS_SEARCH_EMPTY_CACHE_SECONDS", "180"))
        self.rss_max_age_hours = int(os.getenv("NEWS_RSS_MAX_AGE_HOURS", "72"))
        self.symbol_alias_map = self._load_symbol_alias_map()
        self.symbol_official_feed_map = self._load_symbol_source_map("NEWS_SYMBOL_OFFICIAL_FEEDS")
        self.symbol_official_feed_cache_seconds = int(os.getenv("NEWS_SYMBOL_OFFICIAL_FEED_CACHE_SECONDS", "900"))
        self._rss_cache: Dict[str, Any] = {"expires_at": datetime.min, "items": []}
        self._search_cache: Dict[str, Dict[str, Any]] = {}
        self._symbol_official_feed_cache: Dict[str, Dict[str, Any]] = {}

    async def fetch_general_news(self, limit: int = 10) -> List[MarketNews]:
        pool_items = await self._get_global_news_pool(limit=max(limit, self.global_pool_size))
        if pool_items:
            return pool_items[:limit]
        return await self._fetch_news(limit=limit)

    async def fetch_symbol_news(self, symbol: str, limit: int = 6) -> List[MarketNews]:
        asset = self._normalize_asset_symbol(symbol)
        pool_items = await self._get_global_news_pool(limit=max(self.global_pool_size, limit * 8))
        filtered_pool_items = self._filter_relevant_news(pool_items, asset)
        if filtered_pool_items:
            return filtered_pool_items[:limit]

        official_feed_items = await self._fetch_symbol_official_feed_news(
            asset,
            limit=max(limit * 4, self.rss_per_feed_limit),
        )
        if official_feed_items:
            return official_feed_items[:limit]

        return await self._fetch_fallback_symbol_news(asset, limit)

    async def _fetch_news(self, asset_symbol: Optional[str] = None, limit: int = 10) -> List[MarketNews]:
        for provider in self._get_provider_order():
            provider_news = await self._request_provider_news(provider, asset_symbol=asset_symbol, limit=limit)
            if provider_news:
                return provider_news[:limit]
        return []

    async def _get_global_news_pool(self, limit: int) -> List[MarketNews]:
        now = datetime.utcnow()
        if self._rss_cache["expires_at"] > now:
            return self._rss_cache["items"][:limit]

        items = await self._fetch_primary_news_pool(limit=max(limit, self.global_pool_size))
        self._rss_cache = {
            "expires_at": now + timedelta(seconds=self.rss_cache_seconds),
            "items": items,
        }
        return items[:limit]

    async def _fetch_primary_news_pool(self, limit: int) -> List[MarketNews]:
        rss_limit = max(limit, self.global_pool_size)
        tasks = [self._fetch_rss_pool(limit=rss_limit)]
        if self.enable_binance_announcements:
            tasks.append(self._fetch_binance_announcements(limit=rss_limit))
        if self.enable_okx_announcements:
            tasks.append(self._fetch_okx_announcements(limit=rss_limit))
        if self.enable_bybit_announcements:
            tasks.append(self._fetch_bybit_announcements(limit=rss_limit))
        if self.enable_coinbase_blog:
            tasks.append(self._fetch_coinbase_blog_posts(limit=rss_limit))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        combined: List[MarketNews] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("news-service: primary pool source failed: %s", result)
                continue
            combined.extend(result)
        return self._dedupe_and_sort_news(combined)[:limit]

    async def _fetch_fallback_symbol_news(self, asset_symbol: str, limit: int) -> List[MarketNews]:
        cache_key = f"symbol:{asset_symbol}"
        cached = self._search_cache.get(cache_key)
        now = datetime.utcnow()
        if cached and cached["expires_at"] > now:
            return cached["items"][:limit]

        provider_limit = max(limit * 3, 20)
        matched_items: List[MarketNews] = []
        for provider in self._get_provider_order():
            provider_news = await self._request_provider_news(provider, asset_symbol=asset_symbol, limit=provider_limit)
            matched_items = self._filter_relevant_news(provider_news, asset_symbol)
            if matched_items:
                break

        ttl_seconds = self.search_cache_seconds if matched_items else self.empty_search_cache_seconds
        self._search_cache[cache_key] = {
            "expires_at": now + timedelta(seconds=ttl_seconds),
            "items": matched_items,
        }
        return matched_items[:limit]

    async def _fetch_symbol_official_feed_news(self, asset_symbol: str, limit: int) -> List[MarketNews]:
        feed_urls = self.symbol_official_feed_map.get(asset_symbol.upper()) or []
        if not feed_urls:
            return []

        cache_key = asset_symbol.upper()
        cached = self._symbol_official_feed_cache.get(cache_key)
        now = datetime.utcnow()
        if cached and cached["expires_at"] > now:
            return cached["items"][:limit]

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=self.PAGE_FETCH_HEADERS) as client:
                responses = await self._fetch_rss_responses(client, feed_urls=feed_urls)
        except Exception as exc:
            logger.warning("news-service: official feed fetch failed for %s: %s", asset_symbol, exc)
            return []

        items: List[MarketNews] = []
        for feed_url, xml_text in responses:
            items.extend(self._parse_rss_feed(xml_text, feed_url))

        filtered_items = self._filter_relevant_news(items, asset_symbol)
        if not filtered_items:
            filtered_items = self._dedupe_and_sort_news(items)
        self._symbol_official_feed_cache[cache_key] = {
            "expires_at": now + timedelta(seconds=self.symbol_official_feed_cache_seconds),
            "items": filtered_items,
        }
        return filtered_items[:limit]

    def _get_provider_order(self) -> List[str]:
        if self.provider == self.PROVIDER_BRAVE:
            return [self.PROVIDER_BRAVE]
        if self.provider == self.PROVIDER_CRYPTOPANIC:
            return [self.PROVIDER_CRYPTOPANIC]
        return [self.PROVIDER_CRYPTOPANIC, self.PROVIDER_BRAVE]

    async def _request_provider_news(
        self,
        provider: str,
        asset_symbol: Optional[str] = None,
        limit: int = 10,
    ) -> List[MarketNews]:
        if provider == self.PROVIDER_CRYPTOPANIC:
            raw_items = await self._request_cryptopanic_news(asset_symbol=asset_symbol, limit=limit)
            return [self._to_market_news(item, asset_symbol=asset_symbol) for item in raw_items]
        if provider == self.PROVIDER_BRAVE:
            raw_items = await self._request_brave_news(asset_symbol=asset_symbol, limit=limit)
            return [self._to_market_news_from_brave(item, asset_symbol=asset_symbol) for item in raw_items]
        return []

    async def _fetch_rss_pool(self, limit: int) -> List[MarketNews]:
        if not self.rss_feed_urls:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=self.PAGE_FETCH_HEADERS) as client:
                responses = await self._fetch_rss_responses(client)
        except Exception as exc:
            logger.warning("news-service: rss pool fetch failed: %s", exc)
            return []

        items: List[MarketNews] = []
        for feed_url, xml_text in responses:
            items.extend(self._parse_rss_feed(xml_text, feed_url))

        return self._dedupe_and_sort_news(items)[:limit]

    async def _fetch_okx_announcements(self, limit: int) -> List[MarketNews]:
        html_text = await self._fetch_html_page(self.okx_announcements_url, source_name="okx announcements")
        if not html_text:
            return []
        return self._parse_okx_announcements_page(html_text, self.okx_announcements_url)[:limit]

    async def _fetch_bybit_announcements(self, limit: int) -> List[MarketNews]:
        html_text = await self._fetch_html_page(self.bybit_announcements_url, source_name="bybit announcements")
        if not html_text:
            return []
        return self._parse_bybit_announcements_page(html_text, self.bybit_announcements_url)[:limit]

    async def _fetch_coinbase_blog_posts(self, limit: int) -> List[MarketNews]:
        html_text = await self._fetch_html_page(self.coinbase_blog_url, source_name="coinbase blog")
        if not html_text:
            return []
        return self._parse_coinbase_blog_landing_page(html_text, self.coinbase_blog_url)[:limit]

    async def _fetch_html_page(self, url: str, source_name: str) -> Optional[str]:
        if not url:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=self.PAGE_FETCH_HEADERS) as client:
                response = await client.get(url)

            if response.status_code != 200:
                logger.warning(
                    "news-service: %s request failed status=%s url=%s body=%s",
                    source_name,
                    response.status_code,
                    url,
                    response.text[:300],
                )
                return None

            return response.text
        except Exception as exc:
            logger.warning("news-service: %s fetch failed: %s", source_name, exc)
            return None

    async def _fetch_binance_announcements(self, limit: int) -> List[MarketNews]:
        if not self.binance_article_list_url:
            return []

        params = {
            "type": 1,
            "pageNo": 1,
            "pageSize": min(max(self.binance_article_page_size, 1), 10),
        }
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                response = await client.get(self.binance_article_list_url, params=params)

            if response.status_code != 200:
                logger.warning(
                    "news-service: binance announcements request failed status=%s body=%s",
                    response.status_code,
                    response.text[:300],
                )
                return []

            payload = response.json()
        except Exception as exc:
            logger.warning("news-service: binance announcements fetch failed: %s", exc)
            return []

        catalogs = payload.get("data", {}).get("catalogs") or []
        items: List[MarketNews] = []
        for catalog in catalogs[: self.binance_catalog_limit]:
            catalog_name = catalog.get("catalogName")
            for article in catalog.get("articles") or []:
                news_item = self._to_market_news_from_binance_article(article, catalog_name)
                if not news_item or self._is_too_old(news_item.published_at):
                    continue
                items.append(news_item)

        return self._dedupe_and_sort_news(items)[:limit]

    async def _fetch_rss_responses(
        self,
        client: httpx.AsyncClient,
        feed_urls: Optional[List[str]] = None,
    ) -> List[tuple[str, str]]:
        urls = feed_urls or self.rss_feed_urls
        responses: List[tuple[str, str]] = []
        tasks = [client.get(feed_url) for feed_url in urls]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        for feed_url, result in zip(urls, raw_results):
            if isinstance(result, Exception):
                logger.debug("news-service: rss fetch failed for %s: %s", feed_url, result)
                continue
            if result.status_code != 200:
                logger.debug("news-service: rss fetch status=%s url=%s", result.status_code, feed_url)
                continue
            responses.append((feed_url, result.text))
        return responses

    def _parse_okx_announcements_page(self, html_text: str, page_url: str) -> List[MarketNews]:
        pattern = re.compile(
            r'<li class="[^"]*index_articleItem[^"]*">.*?'
            r'<a href="(?P<href>/help/[^"]+)"[^>]*>.*?'
            r'<div class="[^"]*index_articleTitle[^"]*">(?P<title>.*?)</div>.*?'
            r'<span[^>]*>\s*Published on (?P<published_at>[^<]+)</span>',
            re.S,
        )

        news_items: List[MarketNews] = []
        for match in pattern.finditer(html_text):
            title = self._clean_text(match.group("title"))
            url = self._absolutize_url(match.group("href"), page_url)
            published_at = self._parse_datetime(self._clean_text(match.group("published_at")))
            if not title or not url or self._is_too_old(published_at):
                continue

            news_items.append(
                MarketNews(
                    title=title,
                    source=self.OKX_ANNOUNCEMENT_SOURCE,
                    source_domain=self.OKX_ANNOUNCEMENT_DOMAIN,
                    sentiment=None,
                    url=url,
                    summary=self.OKX_ANNOUNCEMENT_SOURCE,
                    published_at=published_at,
                    symbols=self._extract_symbols_from_text(title),
                )
            )
            if len(news_items) >= self.official_page_item_limit:
                break
        return self._dedupe_and_sort_news(news_items)

    def _parse_bybit_announcements_page(self, html_text: str, page_url: str) -> List[MarketNews]:
        payload = self._extract_json_script_payload(html_text, script_id="__NEXT_DATA__")
        if not isinstance(payload, dict):
            return []

        articles = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("articleInitEntity", {})
            .get("list")
            or []
        )

        news_items: List[MarketNews] = []
        for article in articles:
            title = self._clean_text(article.get("title"))
            summary = self._clean_text(article.get("description"))
            category = article.get("category") or {}
            category_key = str(category.get("key") or "").strip()
            category_title = self._clean_text(category.get("title"))
            url = self._absolutize_url(article.get("url"), page_url)
            published_at = self._parse_datetime(article.get("publish_time") or article.get("date_timestamp"))
            if not title or not url or self._is_too_old(published_at):
                continue
            if not self._is_bybit_market_relevant(title, summary, category_key, category_title):
                continue

            news_items.append(
                MarketNews(
                    title=title,
                    source=self.BYBIT_ANNOUNCEMENT_SOURCE,
                    source_domain=self.BYBIT_ANNOUNCEMENT_DOMAIN,
                    sentiment=None,
                    url=url,
                    summary=category_title or summary or self.BYBIT_ANNOUNCEMENT_SOURCE,
                    published_at=published_at,
                    symbols=self._extract_symbols_from_text(f"{title} {summary or ''}"),
                )
            )
            if len(news_items) >= self.official_page_item_limit:
                break
        return self._dedupe_and_sort_news(news_items)

    def _parse_coinbase_blog_landing_page(self, html_text: str, page_url: str) -> List[MarketNews]:
        anchor_pattern = re.compile(
            r'<a[^>]+data-testid="blog-search-results-article-card-link-overlay"[^>]+aria-label="(?P<title>[^"]+)"[^>]+href="(?P<href>/blog/[^"]+)"',
            re.S,
        )

        news_items: List[MarketNews] = []
        for match in anchor_pattern.finditer(html_text):
            title = self._clean_text(match.group("title"))
            if not title:
                continue

            block = html_text[match.end(): match.end() + 5000]
            date_match = re.search(r'<span[^>]*>([A-Z][a-z]{2} \d{1,2}, \d{4})</span>', block)
            summary_match = re.search(
                r'data-testid="blog-search-results-article-card-paragraph"[^>]*>(.*?)</div>',
                block,
                re.S,
            )
            published_at = self._parse_datetime(date_match.group(1) if date_match else None)
            summary = self._clean_text(summary_match.group(1)) if summary_match else None
            url = self._absolutize_url(match.group("href"), page_url)
            if not url or self._is_too_old(published_at):
                continue
            if not self._is_official_market_relevant(title, summary):
                continue

            news_items.append(
                MarketNews(
                    title=title,
                    source=self.COINBASE_BLOG_SOURCE,
                    source_domain=self.COINBASE_BLOG_DOMAIN,
                    sentiment=None,
                    url=url,
                    summary=summary or self.COINBASE_BLOG_SOURCE,
                    published_at=published_at,
                    symbols=self._extract_symbols_from_text(f"{title} {summary or ''}"),
                )
            )
            if len(news_items) >= self.official_page_item_limit:
                break
        return self._dedupe_and_sort_news(news_items)

    def _parse_rss_feed(self, xml_text: str, feed_url: str) -> List[MarketNews]:
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            logger.debug("news-service: rss parse failed for %s: %s", feed_url, exc)
            return []

        channel = root.find("channel")
        if channel is not None:
            feed_title = self._clean_text(self._get_child_text(channel, "title")) or self._extract_domain(feed_url)
            items = channel.findall("item")
            return self._parse_rss_items(items, feed_title, feed_url)

        feed_title = self._clean_text(self._get_child_text(root, "title")) or self._extract_domain(feed_url)
        entries = [node for node in root if self._strip_namespace(node.tag) == "entry"]
        return self._parse_atom_entries(entries, feed_title, feed_url)

    def _parse_rss_items(self, items: List[ElementTree.Element], feed_title: Optional[str], feed_url: str) -> List[MarketNews]:
        news_items: List[MarketNews] = []
        for item in items[: self.rss_per_feed_limit]:
            title = self._clean_text(self._get_child_text(item, "title"))
            summary = self._clean_text(
                self._get_child_text(item, "description")
                or self._get_child_text(item, "content")
            )
            url = self._clean_text(self._get_child_text(item, "link"))
            published_at = self._parse_datetime(
                self._get_child_text(item, "pubDate")
                or self._get_child_text(item, "date")
                or self._get_child_text(item, "updated")
            )
            if not title or not url or self._is_too_old(published_at):
                continue

            source_domain = self._extract_domain(url) or self._extract_domain(feed_url)
            news_items.append(
                MarketNews(
                    title=title,
                    source=feed_title or source_domain or "RSS Feed",
                    source_domain=source_domain,
                    sentiment=None,
                    url=url,
                    summary=summary,
                    published_at=published_at,
                    symbols=[],
                )
            )
        return news_items

    def _parse_atom_entries(self, entries: List[ElementTree.Element], feed_title: Optional[str], feed_url: str) -> List[MarketNews]:
        news_items: List[MarketNews] = []
        for entry in entries[: self.rss_per_feed_limit]:
            title = self._clean_text(self._get_child_text(entry, "title"))
            summary = self._clean_text(
                self._get_child_text(entry, "summary")
                or self._get_child_text(entry, "content")
            )
            url = self._extract_atom_link(entry)
            published_at = self._parse_datetime(
                self._get_child_text(entry, "published")
                or self._get_child_text(entry, "updated")
            )
            if not title or not url or self._is_too_old(published_at):
                continue

            source_domain = self._extract_domain(url) or self._extract_domain(feed_url)
            news_items.append(
                MarketNews(
                    title=title,
                    source=feed_title or source_domain or "RSS Feed",
                    source_domain=source_domain,
                    sentiment=None,
                    url=url,
                    summary=summary,
                    published_at=published_at,
                    symbols=[],
                )
            )
        return news_items

    async def _request_cryptopanic_news(self, asset_symbol: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.api_key:
            logger.debug("news-service: NEWS_API_KEY missing, skipping CryptoPanic fetch")
            return []

        params: Dict[str, Any] = {
            "auth_token": self.api_key,
            "kind": "news",
            "public": "true",
            "limit": min(max(limit, 1), 50),
        }
        if asset_symbol:
            params["currencies"] = asset_symbol

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)

            if response.status_code != 200:
                logger.warning(
                    "news-service: request failed status=%s body=%s",
                    response.status_code,
                    response.text[:300],
                )
                return []

            payload = response.json()
        except Exception as exc:
            logger.warning("news-service: cryptopanic fetch failed for %s: %s", asset_symbol or "market", exc)
            return []

        return payload.get("results", [])

    async def _request_brave_news(self, asset_symbol: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.brave_api_key:
            logger.debug("news-service: BRAVE_SEARCH_API_KEY missing, skipping Brave fetch")
            return []

        params = {
            "q": self._build_brave_query(asset_symbol),
            "count": min(max(limit, 1), 20),
            "freshness": self.brave_freshness,
            "search_lang": "en",
            "safesearch": "moderate",
        }
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.brave_api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.brave_base_url}/news/search", params=params, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    "news-service: brave request failed status=%s body=%s",
                    response.status_code,
                    response.text[:300],
                )
                return []

            payload = response.json()
        except Exception as exc:
            logger.warning("news-service: brave fetch failed for %s: %s", asset_symbol or "market", exc)
            return []

        news_block = payload.get("news") or {}
        return payload.get("results") or news_block.get("results") or []

    def _build_brave_query(self, asset_symbol: Optional[str] = None) -> str:
        if asset_symbol:
            return f'"{asset_symbol}" crypto token binance'
        return "crypto market bitcoin altcoin binance"

    def _to_market_news(self, item: Dict[str, Any], asset_symbol: Optional[str] = None) -> MarketNews:
        source = item.get("source") or {}
        url = item.get("url")
        domain = self._extract_domain(url)
        symbols = [entry.get("code") for entry in item.get("currencies", []) if entry.get("code")]
        if asset_symbol and not symbols:
            symbols = [asset_symbol]

        summary = (
            item.get("description")
            or item.get("body")
            or item.get("slug")
            or ""
        )[:500] or None

        return MarketNews(
            title=item.get("title") or "Untitled",
            source=source.get("title") or source.get("domain") or "CryptoPanic",
            source_domain=domain or source.get("domain"),
            sentiment=None,
            url=url,
            summary=summary,
            published_at=self._parse_datetime(item.get("published_at") or item.get("created_at")),
            symbols=symbols,
        )

    def _to_market_news_from_brave(self, item: Dict[str, Any], asset_symbol: Optional[str] = None) -> MarketNews:
        meta_url = item.get("meta_url") or {}
        url = item.get("url")
        source_domain = self._extract_domain(meta_url.get("hostname") or meta_url.get("netloc") or url)
        summary = (
            item.get("description")
            or " ".join((item.get("extra_snippets") or [])[:2])
            or None
        )

        symbols = [asset_symbol] if asset_symbol else []
        return MarketNews(
            title=item.get("title") or "Untitled",
            source=meta_url.get("hostname") or item.get("source") or "Brave Search",
            source_domain=source_domain,
            sentiment=None,
            url=url,
            summary=summary,
            published_at=self._parse_datetime(
                item.get("page_age") or item.get("published_at") or item.get("age")
            ),
            symbols=symbols,
        )

    def _to_market_news_from_binance_article(
        self,
        article: Dict[str, Any],
        catalog_name: Optional[str] = None,
    ) -> Optional[MarketNews]:
        title = self._clean_text(article.get("title"))
        if not title:
            return None
        if not self._is_binance_market_relevant(title, catalog_name):
            return None

        article_code = article.get("code")
        release_date = article.get("releaseDate")
        published_at = self._parse_binance_release_date(release_date)
        summary = self._clean_text(article.get("body")) or catalog_name or self.BINANCE_ANNOUNCEMENT_SOURCE
        url = article.get("shortLink") or (
            self.BINANCE_ANNOUNCEMENT_DETAIL_URL.format(code=article_code) if article_code else None
        )
        symbols = self._extract_binance_symbols_from_title(title)

        return MarketNews(
            title=title,
            source=self.BINANCE_ANNOUNCEMENT_SOURCE,
            source_domain=self.BINANCE_ANNOUNCEMENT_DOMAIN,
            sentiment=None,
            url=url,
            summary=summary,
            published_at=published_at,
            symbols=symbols,
        )

    def _filter_relevant_news(self, news_items: List[MarketNews], asset_symbol: str) -> List[MarketNews]:
        if not asset_symbol:
            return news_items

        filtered: List[MarketNews] = []
        search_terms = self._build_symbol_search_terms(asset_symbol)
        for item in news_items:
            haystack = f"{item.title} {item.summary or ''}".lower()
            item_symbols = {symbol.lower() for symbol in item.symbols or []}
            has_asset_match = any(term in haystack for term in search_terms) or any(term in item_symbols for term in search_terms)
            has_crypto_hint = any(word in haystack for word in self.CRYPTO_HINT_WORDS)
            if item.source_domain in {
                self.BINANCE_ANNOUNCEMENT_DOMAIN,
                self.OKX_ANNOUNCEMENT_DOMAIN,
                self.BYBIT_ANNOUNCEMENT_DOMAIN,
                self.COINBASE_BLOG_DOMAIN,
            }:
                has_crypto_hint = has_crypto_hint or self._has_official_market_hint(haystack)
            if has_asset_match and has_crypto_hint:
                filtered.append(item)
        return self._dedupe_and_sort_news(filtered)

    def _normalize_asset_symbol(self, symbol: str) -> str:
        upper_symbol = (symbol or "").upper()
        for suffix in ("USDT", "BUSD", "USDC", "FDUSD"):
            if upper_symbol.endswith(suffix):
                return upper_symbol[: -len(suffix)]
        return upper_symbol

    def _build_symbol_search_terms(self, asset_symbol: str) -> List[str]:
        normalized_symbol = asset_symbol.lower()
        aliases = [alias.lower() for alias in self.symbol_alias_map.get(asset_symbol.upper(), [])]
        return [normalized_symbol, *aliases]

    def _load_rss_feed_urls(self) -> List[str]:
        raw_value = os.getenv("NEWS_RSS_FEED_URLS", "").strip()
        if raw_value:
            feed_urls = [item.strip() for item in raw_value.split(",") if item.strip()]
            if self.PANEWS_NEWSFLASH_RSS_URL not in feed_urls:
                feed_urls.append(self.PANEWS_NEWSFLASH_RSS_URL)
            return feed_urls
        return list(self.DEFAULT_RSS_FEED_URLS)

    def _load_symbol_alias_map(self) -> Dict[str, List[str]]:
        raw_value = os.getenv("NEWS_SYMBOL_ALIAS_MAP", "").strip()
        if not raw_value:
            return dict(self.DEFAULT_SYMBOL_ALIAS_MAP)
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            logger.warning("news-service: NEWS_SYMBOL_ALIAS_MAP is invalid json, fallback to defaults")
            return dict(self.DEFAULT_SYMBOL_ALIAS_MAP)

        merged = dict(self.DEFAULT_SYMBOL_ALIAS_MAP)
        for symbol, aliases in payload.items():
            if isinstance(aliases, list):
                merged[str(symbol).upper()] = [str(item).strip() for item in aliases if str(item).strip()]
        return merged

    def _load_symbol_source_map(self, env_key: str) -> Dict[str, List[str]]:
        raw_value = os.getenv(env_key, "").strip()
        if not raw_value:
            return {}
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            logger.warning("news-service: %s is invalid json, ignore it", env_key)
            return {}

        source_map: Dict[str, List[str]] = {}
        for symbol, urls in payload.items():
            normalized_symbol = str(symbol).upper().strip()
            if not normalized_symbol:
                continue
            if isinstance(urls, str):
                normalized_urls = [urls.strip()] if urls.strip() else []
            elif isinstance(urls, list):
                normalized_urls = [str(item).strip() for item in urls if str(item).strip()]
            else:
                normalized_urls = []
            if normalized_urls:
                source_map[normalized_symbol] = normalized_urls
        return source_map

    def _read_bool_env(self, key: str, default: bool) -> bool:
        raw_value = os.getenv(key)
        if raw_value is None:
            return default
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    def _parse_binance_release_date(self, raw_value: Any) -> datetime:
        if raw_value in (None, ""):
            return datetime.utcnow()
        try:
            timestamp = float(raw_value)
        except (TypeError, ValueError):
            return datetime.utcnow()

        if timestamp > 10_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)

    def _is_binance_market_relevant(self, title: str, catalog_name: Optional[str]) -> bool:
        haystack = f"{title} {catalog_name or ''}".lower()
        return any(word in haystack for word in self.BINANCE_MARKET_HINT_WORDS)

    def _extract_binance_symbols_from_title(self, title: str) -> List[str]:
        return self._extract_symbols_from_text(title)

    def _extract_symbols_from_text(self, text: Optional[str]) -> List[str]:
        candidates: List[str] = []
        normalized_text = self._clean_text(text) or ""
        for symbol in re.findall(r"\(([A-Z0-9]{2,20})\)", normalized_text):
            candidates.append(symbol)
        for symbol in re.findall(r"\b([A-Z0-9]{2,20})(?:USDT|FDUSD|USDC|BUSD)\b", normalized_text):
            candidates.append(symbol)
        for symbol in re.findall(r"\b([A-Z0-9]{3,10})\b", normalized_text):
            if symbol in self.SYMBOL_STOP_WORDS:
                continue
            if symbol.isdigit():
                continue
            if symbol.endswith(("USDT", "FDUSD", "USDC", "BUSD")):
                continue
            candidates.append(symbol)

        unique_symbols: List[str] = []
        for symbol in candidates:
            normalized = symbol.upper()
            if normalized not in unique_symbols:
                unique_symbols.append(normalized)
        return unique_symbols

    def _parse_datetime(self, raw_value: Any) -> datetime:
        if not raw_value:
            return datetime.utcnow()
        if isinstance(raw_value, (int, float)):
            timestamp = float(raw_value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)

        raw_text = str(raw_value).strip()
        if not raw_text:
            return datetime.utcnow()

        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw_text, fmt)
            except ValueError:
                continue

        normalized = raw_text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw_text)
                if parsed.tzinfo is not None:
                    return parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed
            except (TypeError, ValueError, IndexError, OverflowError):
                logger.debug("news-service: failed to parse datetime %s", raw_text)
                return datetime.utcnow()

    def _extract_json_script_payload(self, html_text: str, script_id: str) -> Optional[Any]:
        pattern = re.compile(
            rf'<script[^>]+id=["\']{re.escape(script_id)}["\'][^>]*>(?P<payload>.*?)</script>',
            re.S,
        )
        match = pattern.search(html_text)
        if not match:
            return None
        try:
            return json.loads(match.group("payload"))
        except json.JSONDecodeError as exc:
            logger.debug("news-service: failed to decode json script %s: %s", script_id, exc)
            return None

    def _absolutize_url(self, url: Optional[str], base_url: str) -> Optional[str]:
        if not url:
            return None
        return urljoin(base_url, unescape(url).strip())

    def _is_bybit_market_relevant(
        self,
        title: str,
        summary: Optional[str],
        category_key: str,
        category_title: Optional[str],
    ) -> bool:
        if category_key in self.BYBIT_ALWAYS_RELEVANT_CATEGORY_KEYS:
            return True
        if category_key not in self.BYBIT_CONDITIONAL_CATEGORY_KEYS:
            return False
        haystack = f"{title} {summary or ''} {category_title or ''}".lower()
        return self._has_official_market_hint(haystack)

    def _is_official_market_relevant(self, title: str, summary: Optional[str]) -> bool:
        haystack = f"{title} {summary or ''}".lower()
        return self._has_official_market_hint(haystack)

    def _has_official_market_hint(self, haystack: str) -> bool:
        return any(word in haystack for word in self.OFFICIAL_MARKET_HINT_WORDS)

    def _extract_domain(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        parsed = urlparse(url)
        domain = (parsed.netloc or parsed.path).lower()
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or None

    def _clean_text(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        cleaned = re.sub(r"<[^>]+>", " ", unescape(value))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:500] or None

    def _strip_namespace(self, tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def _get_child_text(self, parent: ElementTree.Element, tag_name: str) -> Optional[str]:
        for child in parent.iter():
            if child is parent:
                continue
            if self._strip_namespace(child.tag) == tag_name:
                text = child.text or ""
                if text.strip():
                    return text.strip()
        return None

    def _extract_atom_link(self, entry: ElementTree.Element) -> Optional[str]:
        for child in entry:
            if self._strip_namespace(child.tag) != "link":
                continue
            href = child.attrib.get("href")
            if href:
                return href.strip()
            text = (child.text or "").strip()
            if text:
                return text
        return None

    def _is_too_old(self, published_at: datetime) -> bool:
        return published_at < datetime.utcnow() - timedelta(hours=self.rss_max_age_hours)

    def _dedupe_and_sort_news(self, news_items: List[MarketNews]) -> List[MarketNews]:
        seen: set[str] = set()
        deduped: List[MarketNews] = []
        for item in sorted(news_items, key=lambda news_item: news_item.published_at, reverse=True):
            key = (item.url or item.title).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped


news_service = NewsService()