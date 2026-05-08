import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.schemas.polymarket import (
    PolymarketActivityItem,
    PolymarketTraderCachePoolInfo,
    PolymarketTraderCacheStatus,
    PolymarketTraderProfile,
    PolymarketTraderSummary,
)
from app.services.polymarket_trader_analytics_service import (
    PolymarketTraderAnalyticsService,
    polymarket_trader_analytics_service,
)


logger = logging.getLogger(__name__)


class PolymarketTraderCacheService:
    def __init__(
        self,
        analytics_service: Optional[PolymarketTraderAnalyticsService] = None,
        interval_seconds: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
        default_pools: Optional[List[Tuple[str, str, str, int]]] = None,
    ):
        self.analytics_service = analytics_service or polymarket_trader_analytics_service
        self.interval_seconds = interval_seconds or int(os.getenv("POLYMARKET_TRADER_CACHE_INTERVAL", "300"))
        self.ttl_seconds = ttl_seconds or int(os.getenv("POLYMARKET_TRADER_CACHE_TTL", "600"))
        self.default_pools = default_pools or self._read_default_pools_from_env()
        self._cache: Dict[str, Dict] = {}
        self._profile_cache: Dict[str, Dict] = {}
        self._activity_cache: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._task = None
        self._running = False

    def _read_default_pools_from_env(self) -> List[Tuple[str, str, str, int]]:
        raw = os.getenv("POLYMARKET_TRADER_CACHE_POOLS", "OVERALL:WEEK:PNL:10")
        pools: List[Tuple[str, str, str, int]] = []
        for chunk in raw.split(","):
            item = chunk.strip()
            if not item:
                continue
            parts = [part.strip().upper() for part in item.split(":")]
            if len(parts) != 4:
                logger.warning("polymarket-cache: ignore invalid pool config %s", item)
                continue
            category, time_period, order_by, limit = parts
            try:
                pools.append((category, time_period, order_by, int(limit)))
            except ValueError:
                logger.warning("polymarket-cache: invalid pool limit %s", item)
        return pools or [("OVERALL", "WEEK", "PNL", 10)]

    @staticmethod
    def _build_cache_key(category: str, time_period: str, order_by: str, limit: int) -> str:
        return f"{category}:{time_period}:{order_by}:{limit}"

    @staticmethod
    def _build_profile_cache_key(wallet: str) -> str:
        return wallet.strip().lower()

    @staticmethod
    def _build_activity_cache_key(wallet: str, limit: int, hours: int) -> str:
        return f"{wallet.strip().lower()}:{hours}:{limit}"

    @staticmethod
    def _is_snapshot_valid(snapshot: Optional[Dict]) -> bool:
        if not snapshot:
            return False
        expires_at = snapshot.get("expires_at")
        if not expires_at:
            return False
        return datetime.utcnow() < expires_at

    def _is_cache_valid(self, key: str) -> bool:
        return self._is_snapshot_valid(self._cache.get(key))

    def _snapshot_to_pool_info(self, key: str, snapshot: Dict) -> PolymarketTraderCachePoolInfo:
        expires_at = snapshot.get("expires_at")
        return PolymarketTraderCachePoolInfo(
            cache_key=key,
            category=snapshot["category"],
            time_period=snapshot["time_period"],
            order_by=snapshot["order_by"],
            limit=snapshot["limit"],
            trader_count=len(snapshot.get("traders", [])),
            last_refresh_at=snapshot.get("last_refresh_at"),
            expires_at=expires_at,
            is_stale=not expires_at or datetime.utcnow() >= expires_at,
            last_error=snapshot.get("last_error"),
        )

    async def refresh_pool(
        self,
        *,
        category: str,
        time_period: str,
        order_by: str,
        limit: int,
    ) -> List[PolymarketTraderSummary]:
        cache_key = self._build_cache_key(category, time_period, order_by, limit)
        async with self._lock:
            try:
                traders = await self.analytics_service.list_traders(
                    category=category,
                    time_period=time_period,
                    order_by=order_by,
                    limit=limit,
                )
                now = datetime.utcnow()
                self._cache[cache_key] = {
                    "category": category,
                    "time_period": time_period,
                    "order_by": order_by,
                    "limit": limit,
                    "traders": traders,
                    "last_refresh_at": now,
                    "expires_at": now + timedelta(seconds=self.ttl_seconds),
                    "last_error": None,
                }
                return traders
            except Exception as exc:
                existing = self._cache.get(cache_key, {})
                existing.update(
                    {
                        "category": category,
                        "time_period": time_period,
                        "order_by": order_by,
                        "limit": limit,
                        "traders": existing.get("traders", []),
                        "last_refresh_at": existing.get("last_refresh_at"),
                        "expires_at": existing.get("expires_at"),
                        "last_error": str(exc),
                    }
                )
                self._cache[cache_key] = existing
                raise

    async def get_pool(
        self,
        *,
        category: str,
        time_period: str,
        order_by: str,
        limit: int,
        force_refresh: bool = False,
    ) -> List[PolymarketTraderSummary]:
        cache_key = self._build_cache_key(category, time_period, order_by, limit)
        if not force_refresh and self._is_cache_valid(cache_key):
            return self._cache[cache_key]["traders"]
        return await self.refresh_pool(
            category=category,
            time_period=time_period,
            order_by=order_by,
            limit=limit,
        )

    async def refresh_trader_profile(self, *, wallet: str) -> PolymarketTraderProfile:
        cache_key = self._build_profile_cache_key(wallet)
        async with self._lock:
            try:
                profile = await self.analytics_service.analyze_trader(wallet)
                now = datetime.utcnow()
                self._profile_cache[cache_key] = {
                    "wallet": wallet,
                    "profile": profile,
                    "last_refresh_at": now,
                    "expires_at": now + timedelta(seconds=self.ttl_seconds),
                    "last_error": None,
                }
                return profile
            except Exception as exc:
                existing = self._profile_cache.get(cache_key, {})
                existing.update(
                    {
                        "wallet": wallet,
                        "profile": existing.get("profile"),
                        "last_refresh_at": existing.get("last_refresh_at"),
                        "expires_at": existing.get("expires_at"),
                        "last_error": str(exc),
                    }
                )
                self._profile_cache[cache_key] = existing
                raise

    async def get_trader_profile(self, *, wallet: str, force_refresh: bool = False) -> PolymarketTraderProfile:
        cache_key = self._build_profile_cache_key(wallet)
        if not force_refresh and self._is_snapshot_valid(self._profile_cache.get(cache_key)):
            return self._profile_cache[cache_key]["profile"]
        return await self.refresh_trader_profile(wallet=wallet)

    async def refresh_trader_activity(
        self,
        *,
        wallet: str,
        limit: int,
        hours: int,
    ) -> List[PolymarketActivityItem]:
        cache_key = self._build_activity_cache_key(wallet, limit, hours)
        async with self._lock:
            try:
                activities = await self.analytics_service.get_activity(wallet, limit=limit, hours=hours)
                now = datetime.utcnow()
                self._activity_cache[cache_key] = {
                    "wallet": wallet,
                    "limit": limit,
                    "hours": hours,
                    "activities": activities,
                    "last_refresh_at": now,
                    "expires_at": now + timedelta(seconds=self.ttl_seconds),
                    "last_error": None,
                }
                return activities
            except Exception as exc:
                existing = self._activity_cache.get(cache_key, {})
                existing.update(
                    {
                        "wallet": wallet,
                        "limit": limit,
                        "hours": hours,
                        "activities": existing.get("activities", []),
                        "last_refresh_at": existing.get("last_refresh_at"),
                        "expires_at": existing.get("expires_at"),
                        "last_error": str(exc),
                    }
                )
                self._activity_cache[cache_key] = existing
                raise

    async def get_trader_activity(
        self,
        *,
        wallet: str,
        limit: int,
        hours: int,
        force_refresh: bool = False,
    ) -> List[PolymarketActivityItem]:
        cache_key = self._build_activity_cache_key(wallet, limit, hours)
        if not force_refresh and self._is_snapshot_valid(self._activity_cache.get(cache_key)):
            return self._activity_cache[cache_key]["activities"]
        return await self.refresh_trader_activity(wallet=wallet, limit=limit, hours=hours)

    async def refresh_default_pools_once(self) -> None:
        for category, time_period, order_by, limit in self.default_pools:
            try:
                await self.refresh_pool(
                    category=category,
                    time_period=time_period,
                    order_by=order_by,
                    limit=limit,
                )
            except Exception:
                logger.exception(
                    "polymarket-cache: failed to refresh pool %s/%s/%s/%s",
                    category,
                    time_period,
                    order_by,
                    limit,
                )

    async def poller(self) -> None:
        self._running = True
        logger.info("polymarket-cache: poller started interval=%s pools=%s", self.interval_seconds, len(self.default_pools))
        while self._running:
            await self.refresh_default_pools_once()
            await asyncio.sleep(self.interval_seconds)

    def start(self) -> None:
        if self._task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.poller())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    def get_status(self) -> PolymarketTraderCacheStatus:
        pool_infos = [
            self._snapshot_to_pool_info(cache_key, snapshot)
            for cache_key, snapshot in sorted(self._cache.items())
        ]
        return PolymarketTraderCacheStatus(
            running=self._running,
            interval_seconds=self.interval_seconds,
            ttl_seconds=self.ttl_seconds,
            default_pools=[self._build_cache_key(*pool) for pool in self.default_pools],
            pools=pool_infos,
        )


polymarket_trader_cache_service = PolymarketTraderCacheService()