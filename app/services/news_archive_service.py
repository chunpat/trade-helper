import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.market_anomaly import NewsArchive
from app.schemas.market_insight import MarketNews
from app.services.news_service import news_service

logger = logging.getLogger(__name__)


class NewsArchiveService:
    def __init__(self):
        self.enabled = self._read_bool_env("NEWS_ARCHIVE_ENABLED", True)
        self.refresh_batch_size = int(os.getenv("NEWS_ARCHIVE_REFRESH_BATCH_SIZE", "80"))
        self.stale_after_seconds = int(os.getenv("NEWS_ARCHIVE_STALE_AFTER_SECONDS", "900"))
        self.symbol_stale_after_seconds = int(
            os.getenv("NEWS_ARCHIVE_SYMBOL_STALE_AFTER_SECONDS", str(self.stale_after_seconds))
        )

    async def refresh_general_news_if_stale(self) -> int:
        if not self.enabled:
            return 0
        latest_seen_at = self.get_latest_seen_at()
        if self._is_fresh(latest_seen_at, self.stale_after_seconds):
            return 0

        items = await news_service.fetch_general_news(limit=max(self.refresh_batch_size, 20))
        return self.archive_news_items(items)

    async def refresh_general_news(self, limit: Optional[int] = None) -> List[MarketNews]:
        if not self.enabled:
            return await news_service.fetch_general_news(limit=limit or 20)

        refresh_limit = max(limit or self.refresh_batch_size, self.refresh_batch_size)
        items = await news_service.fetch_general_news(limit=refresh_limit)
        self.archive_news_items(items)
        return self.list_news(limit=limit or refresh_limit)

    async def ensure_general_news(self, limit: int = 20, hours: Optional[int] = None) -> List[MarketNews]:
        if not self.enabled:
            return await news_service.fetch_general_news(limit=limit)

        archived = self.list_news(limit=limit, hours=hours)
        if archived and self._is_fresh(self.get_latest_seen_at(), self.stale_after_seconds):
            return archived

        try:
            await self.refresh_general_news(limit=max(limit, self.refresh_batch_size))
        except Exception:
            logger.exception("news-archive: failed to refresh general news")

        refreshed = self.list_news(limit=limit, hours=hours)
        return refreshed or archived

    async def ensure_symbol_news(
        self,
        symbol: str,
        limit: int = 6,
        hours: Optional[int] = None,
    ) -> List[MarketNews]:
        if not self.enabled:
            return await news_service.fetch_symbol_news(symbol, limit=limit)

        asset_symbol = self._normalize_asset_symbol(symbol)
        archived = self.list_news(limit=limit, symbol=asset_symbol, hours=hours)
        latest_seen_at = self.get_latest_seen_at(symbol=asset_symbol)
        if archived and self._is_fresh(latest_seen_at, self.symbol_stale_after_seconds):
            return archived

        try:
            fetched = await news_service.fetch_symbol_news(symbol, limit=max(limit, 6))
            self.archive_news_items(fetched)
        except Exception:
            logger.exception("news-archive: failed to refresh symbol news for %s", symbol)

        refreshed = self.list_news(limit=limit, symbol=asset_symbol, hours=hours)
        return refreshed or archived

    def archive_news_items(self, news_items: List[MarketNews]) -> int:
        if not self.enabled or not news_items:
            return 0

        normalized_items = self._prepare_unique_items(news_items)
        if not normalized_items:
            return 0

        dedupe_keys = list(normalized_items.keys())
        now = datetime.utcnow()

        for attempt in range(2):
            db = SessionLocal()
            try:
                existing_rows = (
                    db.query(NewsArchive)
                    .filter(NewsArchive.dedupe_key.in_(dedupe_keys))
                    .all()
                )
                existing_map = {row.dedupe_key: row for row in existing_rows}

                for dedupe_key, item in normalized_items.items():
                    row = existing_map.get(dedupe_key)
                    symbols = self._normalize_symbols(item.symbols)
                    payload = item.model_dump(mode="json")

                    if row:
                        row.title = self._truncate(item.title, 500)
                        row.source = self._truncate(item.source, 120)
                        row.source_domain = self._truncate(self._normalize_domain(item), 255)
                        row.url = self._truncate(self._normalize_url(item.url), 1000)
                        row.published_at = item.published_at
                        row.sentiment = self._truncate(item.sentiment, 20)
                        row.summary = item.summary
                        row.symbols = symbols
                        row.symbols_text = self._build_symbols_text(symbols)
                        row.last_seen_at = now
                        row.raw_payload = payload
                        continue

                    db.add(
                        NewsArchive(
                            dedupe_key=dedupe_key,
                            title=self._truncate(item.title, 500),
                            source=self._truncate(item.source, 120),
                            source_domain=self._truncate(self._normalize_domain(item), 255),
                            url=self._truncate(self._normalize_url(item.url), 1000),
                            published_at=item.published_at,
                            sentiment=self._truncate(item.sentiment, 20),
                            summary=item.summary,
                            symbols=symbols,
                            symbols_text=self._build_symbols_text(symbols),
                            first_seen_at=now,
                            last_seen_at=now,
                            raw_payload=payload,
                        )
                    )

                db.commit()
                return len(normalized_items)
            except IntegrityError:
                db.rollback()
                if attempt == 0:
                    continue
                logger.debug("news-archive: ignored duplicate insert race for %s items", len(normalized_items))
                return 0
            except Exception:
                db.rollback()
                logger.exception("news-archive: failed to archive news items")
                return 0
            finally:
                db.close()

        return 0

    def list_news(
        self,
        limit: int = 20,
        symbol: Optional[str] = None,
        hours: Optional[int] = None,
        source_domain: Optional[str] = None,
    ) -> List[MarketNews]:
        if limit <= 0:
            return []

        db = SessionLocal()
        try:
            query = db.query(NewsArchive)
            if symbol:
                asset_symbol = self._normalize_asset_symbol(symbol)
                query = query.filter(NewsArchive.symbols_text.like(f"%|{asset_symbol}|%"))
            if hours is not None:
                query = query.filter(NewsArchive.published_at >= datetime.utcnow() - timedelta(hours=hours))
            if source_domain:
                query = query.filter(NewsArchive.source_domain == source_domain.lower().strip())

            rows = (
                query.order_by(NewsArchive.published_at.desc(), NewsArchive.id.desc())
                .limit(limit)
                .all()
            )
            return [self._to_market_news(row) for row in rows]
        finally:
            db.close()

    def get_latest_seen_at(self, symbol: Optional[str] = None) -> Optional[datetime]:
        db = SessionLocal()
        try:
            query = db.query(NewsArchive.last_seen_at)
            if symbol:
                asset_symbol = self._normalize_asset_symbol(symbol)
                query = query.filter(NewsArchive.symbols_text.like(f"%|{asset_symbol}|%"))

            row = query.order_by(NewsArchive.last_seen_at.desc()).first()
            return row[0] if row else None
        finally:
            db.close()

    def _prepare_unique_items(self, news_items: List[MarketNews]) -> Dict[str, MarketNews]:
        deduped: Dict[str, MarketNews] = {}
        for item in news_items:
            if not item.title or not item.published_at:
                continue
            normalized_item = self._normalize_item(item)
            dedupe_key = self._build_dedupe_key(normalized_item)
            existing = deduped.get(dedupe_key)
            if not existing:
                deduped[dedupe_key] = normalized_item
                continue

            merged_symbols = sorted(
                set(self._normalize_symbols(existing.symbols)) | set(self._normalize_symbols(normalized_item.symbols))
            )
            deduped[dedupe_key] = MarketNews(
                id=existing.id,
                title=normalized_item.title or existing.title,
                source=normalized_item.source or existing.source,
                source_domain=normalized_item.source_domain or existing.source_domain,
                sentiment=normalized_item.sentiment or existing.sentiment,
                url=normalized_item.url or existing.url,
                summary=normalized_item.summary or existing.summary,
                published_at=normalized_item.published_at or existing.published_at,
                symbols=merged_symbols,
            )
        return deduped

    def _normalize_item(self, item: MarketNews) -> MarketNews:
        symbols = self._normalize_symbols(item.symbols)
        source_domain = self._normalize_domain(item)
        return MarketNews(
            id=item.id,
            title=(item.title or "").strip(),
            source=(item.source or "未知来源").strip(),
            source_domain=source_domain,
            sentiment=(item.sentiment or None),
            url=self._normalize_url(item.url),
            summary=(item.summary or None),
            published_at=item.published_at,
            symbols=symbols,
        )

    def _build_dedupe_key(self, item: MarketNews) -> str:
        published_at = item.published_at.replace(microsecond=0).isoformat()
        normalized_title = " ".join((item.title or "").lower().split())
        source_domain = (item.source_domain or item.source or "").lower().strip()
        normalized_url = item.url or ""
        raw_key = "|".join([normalized_title, source_domain, normalized_url, published_at])
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _normalize_symbols(self, symbols: Optional[List[str]]) -> List[str]:
        normalized: List[str] = []
        for symbol in symbols or []:
            asset_symbol = self._normalize_asset_symbol(symbol)
            if asset_symbol and asset_symbol not in normalized:
                normalized.append(asset_symbol)
        return normalized

    def _build_symbols_text(self, symbols: List[str]) -> Optional[str]:
        if not symbols:
            return None
        return "|" + "|".join(symbols) + "|"

    def _normalize_asset_symbol(self, symbol: Optional[str]) -> str:
        upper_symbol = (symbol or "").upper().strip()
        for suffix in ("USDT", "BUSD", "USDC", "FDUSD"):
            if upper_symbol.endswith(suffix):
                return upper_symbol[: -len(suffix)]
        return upper_symbol

    def _normalize_domain(self, item: MarketNews) -> Optional[str]:
        if item.source_domain:
            return item.source_domain.lower().strip()

        parsed = urlparse(item.url or "")
        if parsed.netloc:
            hostname = parsed.netloc.lower().strip()
            return hostname[4:] if hostname.startswith("www.") else hostname
        return None

    def _normalize_url(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        parsed = urlparse(url.strip())
        if not parsed.scheme or not parsed.netloc:
            return url.strip()

        normalized_netloc = parsed.netloc.lower()
        normalized_path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme.lower(), normalized_netloc, normalized_path, "", "", ""))

    def _to_market_news(self, row: NewsArchive) -> MarketNews:
        return MarketNews(
            id=row.id,
            title=row.title,
            source=row.source,
            source_domain=row.source_domain,
            sentiment=row.sentiment,
            url=row.url,
            summary=row.summary,
            published_at=row.published_at,
            symbols=row.symbols or [],
        )

    def _is_fresh(self, latest_seen_at: Optional[datetime], ttl_seconds: int) -> bool:
        return latest_seen_at is not None and latest_seen_at >= datetime.utcnow() - timedelta(seconds=ttl_seconds)

    def _truncate(self, value: Optional[str], limit: int) -> Optional[str]:
        if value is None:
            return None
        return value[:limit]

    def _read_bool_env(self, name: str, default: bool) -> bool:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        return raw_value.strip().lower() not in {"0", "false", "no", "off"}


news_archive_service = NewsArchiveService()