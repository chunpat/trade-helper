import asyncio
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.polymarket_cache import PolymarketCacheEntry
from app.schemas.polymarket import (
    PolymarketActivityItem,
    PolymarketFollowabilityComponent,
    PolymarketFollowabilityReport,
    PolymarketTraderProfile,
    PolymarketTraderSummary,
)
from app.services.polymarket_trader_cache_service import PolymarketTraderCacheService


class FakeAnalyticsService:
    def __init__(self):
        self.list_call_count = 0
        self.profile_call_count = 0
        self.activity_call_count = 0
        self.list_wallets = [
            "0x1234567890abcdef1234567890abcdef12345678",
        ]

    async def list_traders(self, **kwargs):
        self.list_call_count += 1
        return [
            PolymarketTraderSummary(
                wallet_address=wallet,
                name="Trader One",
                leaderboard=None,
                trade_count_7d=4,
                trade_count_30d=10,
                trade_count_24h=1,
                volume_usdc_7d=220,
                volume_usdc_30d=640,
                markets_traded_30d=3,
                win_rate_30d=0.6,
                realized_pnl_30d=80,
                avg_realized_pnl_30d=16,
                open_positions_count=2,
                open_positions_value=150,
                activity_mix={"TRADE": 10},
                median_trade_interval_seconds=600,
                trades_per_hour_30d=0.5,
                avg_trade_size_usdc_30d=64,
                top_market_share_30d=0.5,
                trader_style="discretionary",
                followability=PolymarketFollowabilityReport(
                    score=72,
                    verdict="watchlist",
                    likely_bot=False,
                    skip_recommended=False,
                    reasons=["ok"],
                    components=[PolymarketFollowabilityComponent(name="latency", score=80, weight=0.35, reason="ok")],
                ),
            )
            for wallet in self.list_wallets
        ]

    async def analyze_trader(self, wallet: str):
        self.profile_call_count += 1
        return PolymarketTraderProfile(
            wallet_address=wallet,
            name="Trader One",
            leaderboard=None,
            trade_count_7d=4,
            trade_count_30d=10,
            trade_count_24h=1,
            volume_usdc_7d=220,
            volume_usdc_30d=640,
            markets_traded_30d=3,
            win_rate_30d=0.6,
            realized_pnl_30d=80,
            avg_realized_pnl_30d=16,
            open_positions_count=2,
            open_positions_value=150,
            activity_mix={"TRADE": 10},
            median_trade_interval_seconds=600,
            trades_per_hour_30d=0.5,
            avg_trade_size_usdc_30d=64,
            top_market_share_30d=0.5,
            latest_activity_at=datetime.utcnow(),
            trader_style="discretionary",
            followability=PolymarketFollowabilityReport(
                score=72,
                verdict="watchlist",
                likely_bot=False,
                skip_recommended=False,
                reasons=["ok"],
                components=[PolymarketFollowabilityComponent(name="latency", score=80, weight=0.35, reason="ok")],
            ),
            recent_markets=["Test Market"],
            recent_activities=[],
            current_positions=[],
            recent_closed_positions=[],
        )

    async def get_activity(self, wallet: str, *, limit: int, hours: int):
        self.activity_call_count += 1
        return [
            PolymarketActivityItem(
                proxy_wallet=wallet,
                timestamp=datetime.utcnow(),
                activity_type="TRADE",
                title=f"Activity {hours}h/{limit}",
            )
        ]


def test_get_pool_uses_cache_until_expired():
    analytics = FakeAnalyticsService()
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
        persist_to_db=False,
    )

    first = asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))
    second = asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))

    assert len(first) == 1
    assert len(second) == 1
    assert analytics.list_call_count == 1


def test_force_refresh_bypasses_cache():
    analytics = FakeAnalyticsService()
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
        persist_to_db=False,
    )

    asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))
    asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10, force_refresh=True))

    assert analytics.list_call_count == 2


def test_get_trader_profile_uses_cache_until_expired():
    analytics = FakeAnalyticsService()
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
        persist_to_db=False,
    )

    first = asyncio.run(service.get_trader_profile(wallet="0x1234567890abcdef1234567890abcdef12345678"))
    second = asyncio.run(service.get_trader_profile(wallet="0x1234567890abcdef1234567890abcdef12345678"))

    assert first.wallet_address == second.wallet_address
    assert analytics.profile_call_count == 1


def test_get_trader_activity_uses_cache_until_expired():
    analytics = FakeAnalyticsService()
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
        persist_to_db=False,
    )

    first = asyncio.run(
        service.get_trader_activity(wallet="0x1234567890abcdef1234567890abcdef12345678", limit=100, hours=168)
    )
    second = asyncio.run(
        service.get_trader_activity(wallet="0x1234567890abcdef1234567890abcdef12345678", limit=100, hours=168)
    )

    assert first[0].title == second[0].title
    assert analytics.activity_call_count == 1


def test_refresh_default_pools_prewarms_profile_and_activity_caches():
    analytics = FakeAnalyticsService()
    analytics.list_wallets = [
        "0x1234567890abcdef1234567890abcdef12345678",
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
    ]
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
        prewarm_profiles=True,
        prewarm_activities=True,
        prewarm_limit=1,
        prewarm_activity_limit=100,
        prewarm_activity_hours=168,
        prewarm_concurrency=1,
        persist_to_db=False,
    )

    asyncio.run(service.refresh_default_pools_once())

    profile = asyncio.run(service.get_trader_profile(wallet="0x1234567890abcdef1234567890abcdef12345678"))
    activity = asyncio.run(
        service.get_trader_activity(wallet="0x1234567890abcdef1234567890abcdef12345678", limit=100, hours=168)
    )

    assert profile.wallet_address == "0x1234567890abcdef1234567890abcdef12345678"
    assert activity[0].proxy_wallet == "0x1234567890abcdef1234567890abcdef12345678"
    assert analytics.list_call_count == 1
    assert analytics.profile_call_count == 1
    assert analytics.activity_call_count == 1


def test_refresh_default_pools_prewarm_limit_dedupes_wallets():
    analytics = FakeAnalyticsService()
    analytics.list_wallets = [
        "0x1234567890abcdef1234567890abcdef12345678",
        "0x1234567890abcdef1234567890abcdef12345678",
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
    ]
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
        prewarm_profiles=True,
        prewarm_activities=False,
        prewarm_limit=2,
        prewarm_concurrency=1,
        persist_to_db=False,
    )

    asyncio.run(service.refresh_default_pools_once())

    assert analytics.profile_call_count == 2


def test_get_pool_uses_database_cache_when_enabled():
    analytics = FakeAnalyticsService()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine, tables=[PolymarketCacheEntry.__table__])

    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
        persist_to_db=True,
        session_factory=session_factory,
    )

    first = asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))
    second = asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))
    status = service.get_status()

    assert len(first) == 1
    assert len(second) == 1
    assert analytics.list_call_count == 1
    assert len(status.pools) == 1
    assert status.pools[0].trader_count == 1
