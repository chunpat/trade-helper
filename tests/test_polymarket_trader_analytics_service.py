import asyncio
from datetime import datetime, timedelta

from app.services.polymarket_trader_analytics_service import PolymarketTraderAnalyticsService


class FakePolymarketDataClient:
    def __init__(self, *, profile=None, activity=None, positions=None, closed_positions=None, leaderboard=None):
        self.profile = profile or {}
        self.activity = activity or []
        self.positions = positions or []
        self.closed_positions = closed_positions or []
        self.leaderboard = leaderboard or []

    async def get_public_profile(self, address: str):
        return self.profile

    async def get_activity(self, user: str, *, limit: int = 100, offset: int = 0, activity_type=None, start=None, end=None):
        return self.activity[:limit]

    async def get_positions(self, user: str, *, limit: int = 50, offset: int = 0):
        return self.positions[:limit]

    async def get_closed_positions(self, user: str, *, limit: int = 50, offset: int = 0, sort_by: str = "TIMESTAMP", sort_direction: str = "DESC"):
        return self.closed_positions[:limit]

    async def get_leaderboard(self, *, category: str = "OVERALL", time_period: str = "WEEK", order_by: str = "PNL", limit: int = 10, offset: int = 0):
        return self.leaderboard[:limit]


def test_analyze_trader_builds_summary_and_followability():
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(days=1)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "side": "BUY",
            "size": 100,
            "usdcSize": 64,
            "price": 0.64,
            "title": "Will BTC exceed 120k?",
            "slug": "btc-120k",
            "eventSlug": "btc-2026",
        },
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(days=2)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket2",
            "side": "SELL",
            "size": 80,
            "usdcSize": 52,
            "price": 0.65,
            "title": "Will ETH ETF launch?",
            "slug": "eth-etf",
            "eventSlug": "eth-2026",
        },
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(days=3)).timestamp()),
            "type": "MERGE",
            "conditionId": "0xmarket2",
        },
    ]
    positions = [
        {
            "conditionId": "0xmarket-open",
            "size": 150,
            "currentValue": 123.5,
            "cashPnl": 14.2,
            "percentPnl": 0.12,
            "title": "Will SOL ETF launch?",
            "outcome": "Yes",
        }
    ]
    closed_positions = [
        {
            "conditionId": "0xmarket1",
            "realizedPnl": 25,
            "timestamp": int((now - timedelta(days=4)).timestamp()),
            "title": "Will BTC exceed 120k?",
            "outcome": "Yes",
        },
        {
            "conditionId": "0xmarket2",
            "realizedPnl": -8,
            "timestamp": int((now - timedelta(days=5)).timestamp()),
            "title": "Will ETH ETF launch?",
            "outcome": "No",
        },
    ]
    client = FakePolymarketDataClient(
        profile={
            "name": "Trader One",
            "pseudonym": "Calm-Owl",
            "bio": "manual trader",
            "verifiedBadge": True,
        },
        activity=activity,
        positions=positions,
        closed_positions=closed_positions,
    )
    service = PolymarketTraderAnalyticsService(client=client)

    profile = asyncio.run(service.analyze_trader("0x1234567890abcdef1234567890abcdef12345678"))

    assert profile.name == "Trader One"
    assert profile.trade_count_30d == 2
    assert profile.volume_usdc_30d == 116.0
    assert profile.win_rate_30d == 0.5
    assert profile.open_positions_count == 1
    assert profile.followability.verdict in {"watchlist", "candidate"}
    assert profile.followability.likely_bot is False


def test_analyze_trader_flags_likely_bot_when_high_frequency_and_tiny_size():
    now = datetime.utcnow()
    activity = []
    for index in range(45):
        activity.append(
            {
                "proxyWallet": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
                "timestamp": int((now - timedelta(minutes=index)).timestamp()),
                "type": "TRADE",
                "conditionId": f"0xmarket{index % 5}",
                "side": "BUY",
                "size": 10,
                "usdcSize": 5,
                "price": 0.5,
            }
        )

    client = FakePolymarketDataClient(activity=activity, positions=[], closed_positions=[])
    service = PolymarketTraderAnalyticsService(client=client)

    profile = asyncio.run(service.analyze_trader("0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"))

    assert profile.followability.likely_bot is True
    assert profile.followability.verdict == "avoid"
    assert profile.trade_count_24h == 45
