import asyncio
from datetime import datetime, timedelta

from app.services.polymarket_trader_analytics_service import PolymarketTraderAnalyticsService


class FakePolymarketDataClient:
    def __init__(self, *, profile=None, activity=None, positions=None, closed_positions=None, leaderboard=None, leaderboard_by_request=None):
        self.profile = profile or {}
        self.activity = activity or []
        self.positions = positions or []
        self.closed_positions = closed_positions or []
        self.leaderboard = leaderboard or []
        self.leaderboard_by_request = leaderboard_by_request or {}
        self.leaderboard_calls = []

    async def get_public_profile(self, address: str):
        return self.profile

    async def get_activity(self, user: str, *, limit: int = 100, offset: int = 0, activity_type=None, start=None, end=None):
        return self.activity[:limit]

    async def get_positions(self, user: str, *, limit: int = 50, offset: int = 0):
        return self.positions[:limit]

    async def get_closed_positions(self, user: str, *, limit: int = 50, offset: int = 0, sort_by: str = "TIMESTAMP", sort_direction: str = "DESC"):
        return self.closed_positions[:limit]

    async def get_leaderboard(self, *, category: str = "OVERALL", time_period: str = "WEEK", order_by: str = "PNL", limit: int = 10, offset: int = 0):
        self.leaderboard_calls.append((category, time_period, order_by, limit, offset))
        if self.leaderboard_by_request:
            return self.leaderboard_by_request.get((category, time_period, order_by, offset), [])[:limit]
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


def test_analyze_trader_followability_uses_grouped_trades_for_split_fills():
    now = datetime.utcnow()
    activity = []
    for group_index in range(15):
        base_time = now - timedelta(minutes=group_index * 2)
        for fill_index in range(3):
            activity.append(
                {
                    "proxyWallet": "0x9999999999999999999999999999999999999999",
                    "timestamp": int((base_time - timedelta(seconds=fill_index)).timestamp()),
                    "type": "TRADE",
                    "conditionId": "0xmarket-split",
                    "asset": "0xasset-yes",
                    "side": "BUY",
                    "outcome": "Yes",
                    "size": 10,
                    "usdcSize": 5,
                    "price": 0.5,
                    "title": "Will grouped fills be merged?",
                }
            )

    client = FakePolymarketDataClient(activity=activity, positions=[], closed_positions=[])
    service = PolymarketTraderAnalyticsService(client=client)

    profile = asyncio.run(service.analyze_trader("0x9999999999999999999999999999999999999999"))

    assert profile.trade_count_24h == 15
    assert profile.trade_count_30d == 15
    assert profile.followability.likely_bot is False
    assert profile.followability.median_trade_interval_seconds == 120.0
    assert any("聚合成交口径" in note for note in profile.analysis_notes)


def test_analyze_trader_classifies_five_minute_cadence_as_active_systematic():
    now = datetime.utcnow()
    activity = []
    for day_offset in range(10):
        session_start = now - timedelta(days=day_offset * 3)
        for trade_index in range(18):
            activity.append(
                {
                    "proxyWallet": "0x7777777777777777777777777777777777777777",
                    "timestamp": int((session_start - timedelta(minutes=trade_index * 5)).timestamp()),
                    "type": "TRADE",
                    "conditionId": f"0xmarket-{trade_index % 4}",
                    "asset": f"0xasset-{trade_index % 2}",
                    "side": "BUY" if trade_index % 2 == 0 else "SELL",
                    "outcome": "Yes" if trade_index % 2 == 0 else "No",
                    "size": 20,
                    "usdcSize": 35,
                    "price": 0.55,
                    "title": "Five minute cadence trader",
                }
            )

    closed_positions = [
        {
            "conditionId": "0xmarket-1",
            "realizedPnl": 120,
            "timestamp": int((now - timedelta(days=2)).timestamp()),
            "title": "Profitable closed trade",
            "outcome": "Yes",
        }
    ]

    client = FakePolymarketDataClient(activity=activity, positions=[], closed_positions=closed_positions)
    service = PolymarketTraderAnalyticsService(client=client)

    profile = asyncio.run(service.analyze_trader("0x7777777777777777777777777777777777777777"))

    assert profile.trader_style == "active_systematic"
    assert profile.followability.likely_bot is False
    assert profile.followability.median_trade_interval_seconds == 300.0
    assert any("数分钟级别" in note for note in profile.analysis_notes)


def test_list_traders_expands_candidate_discovery_and_dedupes_wallets():
    wallets = [
        "0x1234567890abcdef1234567890abcdef12345678",
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        "0x1111111111111111111111111111111111111111",
    ]
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": wallets[0],
            "timestamp": int((now - timedelta(days=1)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "side": "BUY",
            "size": 100,
            "usdcSize": 1200,
            "price": 0.64,
        }
    ]
    closed_positions = [
        {
            "conditionId": "0xmarket1",
            "realizedPnl": 250,
            "timestamp": int((now - timedelta(days=4)).timestamp()),
            "title": "Will BTC exceed 120k?",
            "outcome": "Yes",
        }
    ]
    client = FakePolymarketDataClient(
        profile={"name": "Trader One", "verifiedBadge": True},
        activity=activity,
        positions=[],
        closed_positions=closed_positions,
        leaderboard_by_request={
            ("OVERALL", "WEEK", "PNL", 0): [
                {"proxyWallet": wallets[0], "rank": 1, "pnl": 100, "vol": 5000},
                {"proxyWallet": wallets[1], "rank": 2, "pnl": 80, "vol": 4000},
            ],
            ("OVERALL", "WEEK", "PNL", 20): [
                {"proxyWallet": wallets[2], "rank": 21, "pnl": 60, "vol": 3000},
            ],
            ("OVERALL", "WEEK", "VOL", 0): [
                {"proxyWallet": wallets[1], "rank": 1, "pnl": 75, "vol": 9000},
                {"proxyWallet": wallets[2], "rank": 2, "pnl": 55, "vol": 8000},
            ],
        },
    )
    service = PolymarketTraderAnalyticsService(client=client)

    traders = asyncio.run(service.list_traders(category="OVERALL", time_period="WEEK", order_by="PNL", limit=3))

    assert len(traders) == 3
    assert len({item.wallet_address for item in traders}) == 3
    assert any(call[2] == "VOL" for call in client.leaderboard_calls)
    assert any(call[4] == 20 for call in client.leaderboard_calls)


def test_list_traders_scans_adjacent_periods_and_related_categories():
    wallets = [
        "0x2000000000000000000000000000000000000001",
        "0x2000000000000000000000000000000000000002",
        "0x2000000000000000000000000000000000000003",
        "0x2000000000000000000000000000000000000004",
        "0x2000000000000000000000000000000000000005",
    ]
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": wallets[0],
            "timestamp": int((now - timedelta(days=1)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarketx",
            "side": "BUY",
            "size": 120,
            "usdcSize": 1400,
            "price": 0.55,
        }
    ]
    closed_positions = [
        {
            "conditionId": "0xmarketx",
            "realizedPnl": 180,
            "timestamp": int((now - timedelta(days=3)).timestamp()),
            "title": "Will ETH break ATH?",
            "outcome": "Yes",
        }
    ]
    client = FakePolymarketDataClient(
        profile={"name": "Cross Pool Trader"},
        activity=activity,
        positions=[],
        closed_positions=closed_positions,
        leaderboard_by_request={
            ("CRYPTO", "WEEK", "PNL", 0): [
                {"proxyWallet": wallets[0], "rank": 1, "pnl": 90, "vol": 5000},
            ],
            ("CRYPTO", "WEEK", "PNL", 20): [
                {"proxyWallet": wallets[1], "rank": 21, "pnl": 88, "vol": 4200},
            ],
            ("CRYPTO", "WEEK", "VOL", 0): [
                {"proxyWallet": wallets[2], "rank": 1, "pnl": 80, "vol": 9000},
            ],
            ("CRYPTO", "MONTH", "PNL", 0): [
                {"proxyWallet": wallets[3], "rank": 5, "pnl": 150, "vol": 7000},
            ],
            ("OVERALL", "WEEK", "PNL", 0): [
                {"proxyWallet": wallets[4], "rank": 3, "pnl": 120, "vol": 6500},
            ],
            ("OVERALL", "MONTH", "PNL", 0): [
                {"proxyWallet": wallets[4], "rank": 6, "pnl": 160, "vol": 8300},
            ],
        },
    )
    service = PolymarketTraderAnalyticsService(client=client)

    traders = asyncio.run(service.list_traders(category="CRYPTO", time_period="WEEK", order_by="PNL", limit=5))

    assert len(traders) == 5
    assert {item.wallet_address for item in traders} == set(wallets)
    assert any(call[:3] == ("CRYPTO", "MONTH", "PNL") for call in client.leaderboard_calls)
    assert any(call[:3] == ("OVERALL", "WEEK", "PNL") for call in client.leaderboard_calls)
    assert any(call[:3] == ("OVERALL", "MONTH", "PNL") for call in client.leaderboard_calls)
