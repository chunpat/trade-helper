import asyncio

from app.schemas.polymarket import PolymarketFollowabilityComponent, PolymarketFollowabilityReport, PolymarketTraderSummary
from app.services.polymarket_trader_cache_service import PolymarketTraderCacheService


class FakeAnalyticsService:
    def __init__(self):
        self.call_count = 0

    async def list_traders(self, **kwargs):
        self.call_count += 1
        return [
            PolymarketTraderSummary(
                wallet_address="0x1234567890abcdef1234567890abcdef12345678",
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
        ]


def test_get_pool_uses_cache_until_expired():
    analytics = FakeAnalyticsService()
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
    )

    first = asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))
    second = asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))

    assert len(first) == 1
    assert len(second) == 1
    assert analytics.call_count == 1


def test_force_refresh_bypasses_cache():
    analytics = FakeAnalyticsService()
    service = PolymarketTraderCacheService(
        analytics_service=analytics,
        interval_seconds=300,
        ttl_seconds=3600,
        default_pools=[("OVERALL", "WEEK", "PNL", 10)],
    )

    asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10))
    asyncio.run(service.get_pool(category="OVERALL", time_period="WEEK", order_by="PNL", limit=10, force_refresh=True))

    assert analytics.call_count == 2
