import asyncio
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.polymarket_copy import PolymarketCopySimulationRun, PolymarketCopySourcePosition, PolymarketCopyStrategy
from app.schemas.polymarket_copy import PolymarketCopySimulationRequest, PolymarketCopyStrategyCreate
from app.services.polymarket_copy_service import PolymarketCopyService
from app.services.polymarket_trader_analytics_service import PolymarketTraderAnalyticsService


class FakePolymarketDataClient:
    def __init__(self, activity=None):
        self.activity = activity or []

    async def get_public_profile(self, address: str):
        return {}

    async def get_activity(self, user: str, *, limit: int = 100, offset: int = 0, activity_type=None, start=None, end=None):
        return self.activity[:limit]

    async def get_positions(self, user: str, *, limit: int = 50, offset: int = 0):
        return []

    async def get_closed_positions(self, user: str, *, limit: int = 50, offset: int = 0, sort_by: str = "TIMESTAMP", sort_direction: str = "DESC"):
        return []


def _build_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            PolymarketCopyStrategy.__table__,
            PolymarketCopySimulationRun.__table__,
            PolymarketCopySourcePosition.__table__,
        ],
    )
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def test_create_strategy_persists_defaults():
    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient())
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="同比例策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            copy_ratio=0.2,
        )
    )

    assert strategy.strategy_name == "同比例策略"
    assert strategy.copy_mode == "proportional_notional"
    assert strategy.copy_ratio == 0.2
    assert strategy.status == "draft"


def test_simulate_strategy_builds_proportional_open_and_close_signals():
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(hours=6)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "BUY",
            "outcome": "Yes",
            "size": 200,
            "usdcSize": 100,
            "price": 0.5,
            "title": "Will BTC rise?",
        },
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(hours=5)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "BUY",
            "outcome": "Yes",
            "size": 100,
            "usdcSize": 50,
            "price": 0.5,
            "title": "Will BTC rise?",
        },
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(hours=4)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "SELL",
            "outcome": "Yes",
            "size": 150,
            "usdcSize": 75,
            "price": 0.5,
            "title": "Will BTC rise?",
        },
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(hours=3)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "SELL",
            "outcome": "Yes",
            "size": 150,
            "usdcSize": 75,
            "price": 0.5,
            "title": "Will BTC rise?",
        },
    ]

    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient(activity=activity))
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="同比例策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            copy_ratio=0.25,
            min_copy_order_usdc=10,
            max_order_usdc=200,
            max_position_notional_usdc=1000,
            max_market_exposure_usdc=500,
        )
    )

    result = asyncio.run(
        service.simulate_strategy(
            strategy.id,
            payload=PolymarketCopySimulationRequest(lookback_hours=24, activity_limit=50),
        )
    )

    assert result is not None
    assert result.summary.executed_signal_count == 4
    assert result.summary.total_source_notional_usdc == 300.0
    assert result.summary.total_copied_notional_usdc == 75.0
    assert [item.signal_type for item in result.signals] == ["OPEN", "ADD", "REDUCE", "CLOSE"]
    assert result.signals[0].follower_order_usdc == 25.0
    assert result.signals[2].source_reduce_ratio == 0.5
    assert result.signals[3].follower_position_after == 0.0