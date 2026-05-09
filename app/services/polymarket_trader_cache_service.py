import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.database import SessionLocal
from app.models.polymarket_cache import PolymarketCacheEntry
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
        prewarm_profiles: Optional[bool] = None,
        prewarm_activities: Optional[bool] = None,
        prewarm_limit: Optional[int] = None,
        prewarm_activity_limit: Optional[int] = None,
        prewarm_activity_hours: Optional[int] = None,
        prewarm_concurrency: Optional[int] = None,
        persist_to_db: Optional[bool] = None,
        session_factory: Optional[Callable[[], Any]] = None,
    ):
        self.analytics_service = analytics_service or polymarket_trader_analytics_service
        self.interval_seconds = interval_seconds or int(os.getenv("POLYMARKET_TRADER_CACHE_INTERVAL", "300"))
        self.ttl_seconds = ttl_seconds or int(os.getenv("POLYMARKET_TRADER_CACHE_TTL", "600"))
        self.default_pools = default_pools or self._read_default_pools_from_env()
        self.prewarm_profiles = self._read_bool_env("POLYMARKET_TRADER_CACHE_PREWARM_PROFILES", True) if prewarm_profiles is None else prewarm_profiles
        self.prewarm_activities = self._read_bool_env("POLYMARKET_TRADER_CACHE_PREWARM_ACTIVITIES", True) if prewarm_activities is None else prewarm_activities
        self.prewarm_limit = max(0, prewarm_limit if prewarm_limit is not None else int(os.getenv("POLYMARKET_TRADER_CACHE_PREWARM_LIMIT", "5")))
        self.prewarm_activity_limit = max(1, prewarm_activity_limit if prewarm_activity_limit is not None else int(os.getenv("POLYMARKET_TRADER_CACHE_PREWARM_ACTIVITY_LIMIT", "100")))
        self.prewarm_activity_hours = max(1, prewarm_activity_hours if prewarm_activity_hours is not None else int(os.getenv("POLYMARKET_TRADER_CACHE_PREWARM_ACTIVITY_HOURS", "168")))
        self.prewarm_concurrency = max(1, prewarm_concurrency if prewarm_concurrency is not None else int(os.getenv("POLYMARKET_TRADER_CACHE_PREWARM_CONCURRENCY", "3")))
        self.persist_to_db = self._read_bool_env("POLYMARKET_TRADER_CACHE_USE_DB", True) if persist_to_db is None else persist_to_db
        self.session_factory = session_factory or SessionLocal
        self._cache: Dict[str, Dict] = {}
        self._profile_cache: Dict[str, Dict] = {}
        self._activity_cache: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._task = None
        self._running = False

    @staticmethod
    def _read_bool_env(key: str, default: bool) -> bool:
        raw = os.getenv(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

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

    @staticmethod
    def _serialize_traders(traders: List[PolymarketTraderSummary]) -> List[Dict[str, Any]]:
        return [trader.model_dump(mode="json") for trader in traders]

    @staticmethod
    def _deserialize_traders(payload: Any) -> List[PolymarketTraderSummary]:
        if not isinstance(payload, list):
            return []
        return [PolymarketTraderSummary.model_validate(item) for item in payload]

    @staticmethod
    def _serialize_profile(profile: PolymarketTraderProfile) -> Dict[str, Any]:
        return profile.model_dump(mode="json")

    @staticmethod
    def _deserialize_profile(payload: Any) -> Optional[PolymarketTraderProfile]:
        if not isinstance(payload, dict):
            return None
        return PolymarketTraderProfile.model_validate(payload)

    @staticmethod
    def _serialize_activities(activities: List[PolymarketActivityItem]) -> List[Dict[str, Any]]:
        return [activity.model_dump(mode="json") for activity in activities]

    @staticmethod
    def _deserialize_activities(payload: Any) -> List[PolymarketActivityItem]:
        if not isinstance(payload, list):
            return []
        return [PolymarketActivityItem.model_validate(item) for item in payload]

    def _is_entry_valid(self, entry: Optional[PolymarketCacheEntry]) -> bool:
        if not entry or not entry.expires_at:
            return False
        return datetime.utcnow() < entry.expires_at

    def _load_cache_entry(self, *, cache_type: str, cache_key: str) -> Optional[PolymarketCacheEntry]:
        db = self.session_factory()
        try:
            return (
                db.query(PolymarketCacheEntry)
                .filter(
                    PolymarketCacheEntry.cache_type == cache_type,
                    PolymarketCacheEntry.cache_key == cache_key,
                )
                .first()
            )
        finally:
            db.close()

    def _list_pool_entries(self) -> List[PolymarketCacheEntry]:
        db = self.session_factory()
        try:
            return (
                db.query(PolymarketCacheEntry)
                .filter(PolymarketCacheEntry.cache_type == "pool")
                .order_by(PolymarketCacheEntry.cache_key.asc())
                .all()
            )
        finally:
            db.close()

    def _upsert_cache_entry(
        self,
        *,
        cache_type: str,
        cache_key: str,
        payload: Optional[Any] = None,
        wallet_address: Optional[str] = None,
        category: Optional[str] = None,
        time_period: Optional[str] = None,
        order_by: Optional[str] = None,
        limit_value: Optional[int] = None,
        hours_value: Optional[int] = None,
        last_refresh_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        last_error: Optional[str] = None,
    ) -> None:
        db = self.session_factory()
        try:
            row = (
                db.query(PolymarketCacheEntry)
                .filter(
                    PolymarketCacheEntry.cache_type == cache_type,
                    PolymarketCacheEntry.cache_key == cache_key,
                )
                .first()
            )
            if row is None:
                row = PolymarketCacheEntry(cache_type=cache_type, cache_key=cache_key)
                db.add(row)

            row.wallet_address = wallet_address or row.wallet_address
            row.category = category or row.category
            row.time_period = time_period or row.time_period
            row.order_by = order_by or row.order_by
            row.limit_value = limit_value if limit_value is not None else row.limit_value
            row.hours_value = hours_value if hours_value is not None else row.hours_value
            if payload is not None:
                row.payload = payload
            if last_refresh_at is not None:
                row.last_refresh_at = last_refresh_at
            if expires_at is not None:
                row.expires_at = expires_at
            row.last_error = last_error
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _entry_to_pool_info(self, entry: PolymarketCacheEntry) -> PolymarketTraderCachePoolInfo:
        expires_at = entry.expires_at
        payload = entry.payload if isinstance(entry.payload, list) else []
        return PolymarketTraderCachePoolInfo(
            cache_key=entry.cache_key,
            category=entry.category or "",
            time_period=entry.time_period or "",
            order_by=entry.order_by or "",
            limit=entry.limit_value or 0,
            trader_count=len(payload),
            last_refresh_at=entry.last_refresh_at,
            expires_at=expires_at,
            is_stale=not expires_at or datetime.utcnow() >= expires_at,
            last_error=entry.last_error,
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
                expires_at = now + timedelta(seconds=self.ttl_seconds)
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="pool",
                        cache_key=cache_key,
                        category=category,
                        time_period=time_period,
                        order_by=order_by,
                        limit_value=limit,
                        payload=self._serialize_traders(traders),
                        last_refresh_at=now,
                        expires_at=expires_at,
                        last_error=None,
                    )
                else:
                    self._cache[cache_key] = {
                        "category": category,
                        "time_period": time_period,
                        "order_by": order_by,
                        "limit": limit,
                        "traders": traders,
                        "last_refresh_at": now,
                        "expires_at": expires_at,
                        "last_error": None,
                    }
                return traders
            except Exception as exc:
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="pool",
                        cache_key=cache_key,
                        category=category,
                        time_period=time_period,
                        order_by=order_by,
                        limit_value=limit,
                        last_error=str(exc),
                    )
                else:
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
        if not force_refresh:
            if self.persist_to_db:
                entry = self._load_cache_entry(cache_type="pool", cache_key=cache_key)
                if self._is_entry_valid(entry):
                    return self._deserialize_traders(entry.payload)
            elif self._is_cache_valid(cache_key):
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
                expires_at = now + timedelta(seconds=self.ttl_seconds)
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="profile",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        payload=self._serialize_profile(profile),
                        last_refresh_at=now,
                        expires_at=expires_at,
                        last_error=None,
                    )
                else:
                    self._profile_cache[cache_key] = {
                        "wallet": wallet,
                        "profile": profile,
                        "last_refresh_at": now,
                        "expires_at": expires_at,
                        "last_error": None,
                    }
                return profile
            except Exception as exc:
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="profile",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        last_error=str(exc),
                    )
                else:
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
        if not force_refresh:
            if self.persist_to_db:
                entry = self._load_cache_entry(cache_type="profile", cache_key=cache_key)
                if self._is_entry_valid(entry):
                    profile = self._deserialize_profile(entry.payload)
                    if profile is not None:
                        return profile
            elif self._is_snapshot_valid(self._profile_cache.get(cache_key)):
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
                expires_at = now + timedelta(seconds=self.ttl_seconds)
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="activity",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        limit_value=limit,
                        hours_value=hours,
                        payload=self._serialize_activities(activities),
                        last_refresh_at=now,
                        expires_at=expires_at,
                        last_error=None,
                    )
                else:
                    self._activity_cache[cache_key] = {
                        "wallet": wallet,
                        "limit": limit,
                        "hours": hours,
                        "activities": activities,
                        "last_refresh_at": now,
                        "expires_at": expires_at,
                        "last_error": None,
                    }
                return activities
            except Exception as exc:
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="activity",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        limit_value=limit,
                        hours_value=hours,
                        last_error=str(exc),
                    )
                else:
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
        if not force_refresh:
            if self.persist_to_db:
                entry = self._load_cache_entry(cache_type="activity", cache_key=cache_key)
                if self._is_entry_valid(entry):
                    return self._deserialize_activities(entry.payload)
            elif self._is_snapshot_valid(self._activity_cache.get(cache_key)):
                return self._activity_cache[cache_key]["activities"]
        return await self.refresh_trader_activity(wallet=wallet, limit=limit, hours=hours)

    async def refresh_default_pools_once(self) -> None:
        traders_to_prewarm: List[PolymarketTraderSummary] = []
        for category, time_period, order_by, limit in self.default_pools:
            try:
                traders = await self.refresh_pool(
                    category=category,
                    time_period=time_period,
                    order_by=order_by,
                    limit=limit,
                )
                traders_to_prewarm.extend(traders)
            except Exception:
                logger.exception(
                    "polymarket-cache: failed to refresh pool %s/%s/%s/%s",
                    category,
                    time_period,
                    order_by,
                    limit,
                )

        await self._prewarm_trader_caches(traders_to_prewarm)

    async def _prewarm_trader_caches(self, traders: List[PolymarketTraderSummary]) -> None:
        if not traders or self.prewarm_limit <= 0:
            return
        if not self.prewarm_profiles and not self.prewarm_activities:
            return

        wallets: List[str] = []
        seen = set()
        for trader in traders:
            wallet = (trader.wallet_address or "").strip()
            if not wallet:
                continue
            key = wallet.lower()
            if key in seen:
                continue
            seen.add(key)
            wallets.append(wallet)
            if len(wallets) >= self.prewarm_limit:
                break

        if not wallets:
            return

        logger.info(
            "polymarket-cache: prewarming trader caches wallets=%s profiles=%s activities=%s",
            len(wallets),
            self.prewarm_profiles,
            self.prewarm_activities,
        )
        semaphore = asyncio.Semaphore(self.prewarm_concurrency)

        async def warm_wallet(wallet: str) -> None:
            async with semaphore:
                tasks = []
                if self.prewarm_profiles:
                    tasks.append(self._prewarm_profile(wallet))
                if self.prewarm_activities:
                    tasks.append(
                        self._prewarm_activity(
                            wallet,
                            limit=self.prewarm_activity_limit,
                            hours=self.prewarm_activity_hours,
                        )
                    )
                try:
                    if tasks:
                        await asyncio.gather(*tasks)
                except Exception:
                    logger.exception("polymarket-cache: failed to prewarm wallet %s", wallet)

        await asyncio.gather(*(warm_wallet(wallet) for wallet in wallets))

    async def _prewarm_profile(self, wallet: str) -> None:
        cache_key = self._build_profile_cache_key(wallet)
        try:
            profile = await self.analytics_service.analyze_trader(wallet)
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=self.ttl_seconds)
            async with self._lock:
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="profile",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        payload=self._serialize_profile(profile),
                        last_refresh_at=now,
                        expires_at=expires_at,
                        last_error=None,
                    )
                else:
                    self._profile_cache[cache_key] = {
                        "wallet": wallet,
                        "profile": profile,
                        "last_refresh_at": now,
                        "expires_at": expires_at,
                        "last_error": None,
                    }
        except Exception as exc:
            async with self._lock:
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="profile",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        last_error=str(exc),
                    )
                else:
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

    async def _prewarm_activity(self, wallet: str, *, limit: int, hours: int) -> None:
        cache_key = self._build_activity_cache_key(wallet, limit, hours)
        try:
            activities = await self.analytics_service.get_activity(wallet, limit=limit, hours=hours)
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=self.ttl_seconds)
            async with self._lock:
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="activity",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        limit_value=limit,
                        hours_value=hours,
                        payload=self._serialize_activities(activities),
                        last_refresh_at=now,
                        expires_at=expires_at,
                        last_error=None,
                    )
                else:
                    self._activity_cache[cache_key] = {
                        "wallet": wallet,
                        "limit": limit,
                        "hours": hours,
                        "activities": activities,
                        "last_refresh_at": now,
                        "expires_at": expires_at,
                        "last_error": None,
                    }
        except Exception as exc:
            async with self._lock:
                if self.persist_to_db:
                    self._upsert_cache_entry(
                        cache_type="activity",
                        cache_key=cache_key,
                        wallet_address=wallet.strip().lower(),
                        limit_value=limit,
                        hours_value=hours,
                        last_error=str(exc),
                    )
                else:
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
        if self.persist_to_db:
            pool_infos = [self._entry_to_pool_info(entry) for entry in self._list_pool_entries()]
        else:
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