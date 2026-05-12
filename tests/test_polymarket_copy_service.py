import asyncio
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.polymarket_copy import (
    PolymarketCopySignalLog,
    PolymarketCopySimulationRun,
    PolymarketCopySourcePosition,
    PolymarketCopyStrategy,
)
from app.models.risk_control import Account
from app.schemas.polymarket_copy import PolymarketCopySimulationRequest, PolymarketCopyStrategyCreate
from app.services.polymarket_copy_service import PolymarketCopyService
from app.services.polymarket_trader_analytics_service import PolymarketTraderAnalyticsService


class FakePolymarketDataClient:
    def __init__(self, activity=None):
        self.activity = activity or []
        self.activity_calls = []

    async def get_public_profile(self, address: str):
        return {}

    async def get_activity(self, user: str, *, limit: int = 100, offset: int = 0, activity_type=None, start=None, end=None):
        self.activity_calls.append({"user": user, "limit": limit, "offset": offset, "start": start, "end": end})
        rows = list(self.activity)
        if activity_type:
            rows = [row for row in rows if row.get("type") == activity_type]
        if start is not None:
            rows = [row for row in rows if int(row.get("timestamp") or 0) >= int(start)]
        if end is not None:
            rows = [row for row in rows if int(row.get("timestamp") or 0) <= int(end)]
        rows = sorted(rows, key=lambda row: int(row.get("timestamp") or 0), reverse=True)
        return rows[offset: offset + limit]

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
            Account.__table__,
            PolymarketCopyStrategy.__table__,
            PolymarketCopySimulationRun.__table__,
            PolymarketCopySourcePosition.__table__,
            PolymarketCopySignalLog.__table__,
        ],
    )
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _create_account(session_factory, *, account_id: int = 1, exchange: str = "binance", is_active: bool = True):
    db = session_factory()
    try:
        api_key = "key"
        api_secret = "secret"
        if exchange == "polymarket":
            api_key = f"0x{account_id:040x}"[-42:]
            api_secret = "0x" + ("1" * 64)
        account = Account(
            id=account_id,
            name=f"Test Account {account_id}",
            exchange=exchange,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase="passphrase" if exchange == "okx" else None,
            is_active=is_active,
            settings={},
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account
    finally:
        db.close()


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


def test_create_strategy_defaults_to_one_to_one_and_unlimited_limits():
    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient())
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="默认策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
        )
    )

    assert strategy.copy_ratio == 1.0
    assert strategy.min_copy_order_usdc == 0.0
    assert strategy.max_order_usdc == 0.0
    assert strategy.max_position_notional_usdc == 0.0
    assert strategy.max_market_exposure_usdc == 0.0


def test_zero_limits_are_treated_as_unlimited_when_simulating():
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(hours=1)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "BUY",
            "outcome": "Yes",
            "size": 300,
            "usdcSize": 150,
            "price": 0.5,
            "title": "Will BTC rise?",
        },
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(minutes=30)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "BUY",
            "outcome": "Yes",
            "size": 400,
            "usdcSize": 200,
            "price": 0.5,
            "title": "Will BTC rise?",
        },
    ]

    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient(activity=activity))
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="默认不限策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
        )
    )

    result = asyncio.run(
        service.simulate_strategy(
            strategy.id,
            payload=PolymarketCopySimulationRequest(lookback_hours=24, activity_limit=50),
        )
    )

    assert result is not None
    assert result.summary.executed_signal_count == 2
    assert result.summary.skipped_signal_count == 0
    assert result.summary.total_copied_notional_usdc == 350.0


def test_create_live_strategy_requires_active_execution_account():
    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient())
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    _create_account(session_factory, account_id=7, exchange="polymarket", is_active=True)

    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="真实策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            execution_account_id=7,
            dry_run=False,
            copy_ratio=0.2,
        )
    )

    assert strategy.execution_account_id == 7
    assert strategy.execution_account_name == "Test Account 7"
    assert strategy.execution_account_exchange == "polymarket"
    assert strategy.dry_run is False


def test_create_strategy_rejects_non_polymarket_execution_account():
    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient())
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    _create_account(session_factory, account_id=8, exchange="binance", is_active=True)

    try:
        service.create_strategy(
            payload=PolymarketCopyStrategyCreate(
                strategy_name="真实策略",
                source_wallet="0x1234567890abcdef1234567890abcdef12345678",
                execution_account_id=8,
                dry_run=False,
                copy_ratio=0.2,
            )
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "Polymarket 跟单策略只能绑定 Polymarket 账户"


def test_create_live_strategy_rejects_missing_execution_account():
    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient())
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    try:
        service.create_strategy(
            payload=PolymarketCopyStrategyCreate(
                strategy_name="真实策略",
                source_wallet="0x1234567890abcdef1234567890abcdef12345678",
                dry_run=False,
                copy_ratio=0.2,
            )
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "真实交易模式必须绑定一个有效的交易账户"


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


def test_run_cycle_persists_shadow_positions_and_processes_incremental_trades_only():
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(hours=2)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "BUY",
            "outcome": "Yes",
            "size": 100,
            "usdcSize": 40,
            "price": 0.4,
            "title": "Will BTC rise?",
        }
    ]

    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient(activity=activity))
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="runner策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            copy_ratio=0.5,
            min_copy_order_usdc=10,
        )
    )

    started = service.start_strategy(strategy.id)
    assert started is not None
    assert started.status == "running"
    assert started.last_started_at is not None

    first_run = asyncio.run(service.run_strategy_cycle(strategy.id))
    assert first_run is not None
    assert first_run.summary.grouped_trade_count == 1
    assert first_run.summary.executed_signal_count == 1

    db = session_factory()
    try:
        shadow_position = db.query(PolymarketCopySourcePosition).filter(PolymarketCopySourcePosition.strategy_id == strategy.id).one()
        assert shadow_position.estimated_source_size == 100.0
        assert shadow_position.estimated_source_notional_usdc == 40.0
        assert shadow_position.estimated_follower_size == 50.0
        assert shadow_position.estimated_follower_notional_usdc == 20.0
    finally:
        db.close()

    activity.append(
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(hours=1)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "0xyes",
            "side": "SELL",
            "outcome": "Yes",
            "size": 100,
            "usdcSize": 40,
            "price": 0.4,
            "title": "Will BTC rise?",
        }
    )

    second_run = asyncio.run(service.run_strategy_cycle(strategy.id))
    assert second_run is not None
    assert second_run.summary.grouped_trade_count == 1
    assert second_run.summary.executed_signal_count == 1
    assert [item.signal_type for item in second_run.signals] == ["CLOSE"]

    third_run = asyncio.run(service.run_strategy_cycle(strategy.id))
    assert third_run is not None
    assert third_run.summary.grouped_trade_count == 0
    assert third_run.summary.executed_signal_count == 0
    assert third_run.simulation_run_id is None
    assert third_run.signals == []

    runs = service.list_simulation_runs(strategy.id)
    assert len(runs) == 2

    db = session_factory()
    try:
        signal_logs = db.query(PolymarketCopySignalLog).filter(PolymarketCopySignalLog.strategy_id == strategy.id).count()
        shadow_position = db.query(PolymarketCopySourcePosition).filter(PolymarketCopySourcePosition.strategy_id == strategy.id).one()
    finally:
        db.close()

    assert signal_logs == 2
    assert shadow_position.estimated_source_size == 0.0
    assert shadow_position.estimated_source_notional_usdc == 0.0
    assert shadow_position.estimated_follower_size == 0.0
    assert shadow_position.estimated_follower_notional_usdc == 0.0

    stopped = service.stop_strategy(strategy.id)
    assert stopped is not None
    assert stopped.status == "stopped"
    assert stopped.last_stopped_at is not None


def test_start_live_strategy_succeeds_with_polymarket_execution_account():
    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient())
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    _create_account(session_factory, account_id=9, exchange="polymarket", is_active=True)
    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="真实策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            execution_account_id=9,
            dry_run=False,
            copy_ratio=0.2,
        )
    )

    started = service.start_strategy(strategy.id)
    assert started is not None
    assert started.status == "running"

    stopped = service.stop_strategy(strategy.id)
    assert stopped is not None
    assert stopped.status == "stopped"


def test_preflight_live_strategy_runs_adapter_checks_without_persisting_run(monkeypatch):
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(minutes=30)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket1",
            "asset": "123",
            "side": "BUY",
            "outcome": "Yes",
            "size": 100,
            "usdcSize": 50,
            "price": 0.5,
            "title": "Will BTC rise?",
        }
    ]

    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient(activity=activity))
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    _create_account(session_factory, account_id=10, exchange="polymarket", is_active=True)
    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="真实策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            execution_account_id=10,
            dry_run=False,
        )
    )

    class FakeAdapter:
        async def test_connectivity(self):
            return {
                "overall_hint": "ok",
                "account_mode_note": "EOA",
                "checks": [
                    {"scope": "clob_l1", "endpoint": "/auth/api-key", "ok": True, "status_code": 200, "message": "ok", "hint": "ok"}
                ],
            }

        async def preflight_orderbook(self, token_id: str, side: str):
            assert token_id == "123"
            assert side == "BUY"
            return {"scope": "orderbook", "endpoint": "/book", "ok": True, "status_code": 200, "message": "book ok", "hint": "ok"}

    monkeypatch.setattr("app.services.polymarket_copy_service.create_adapter_for_account", lambda account: FakeAdapter())

    result = asyncio.run(service.preflight_live_strategy(strategy.id))

    assert result is not None
    assert result.overall_ok is True
    assert result.executable_signal_count == 1
    assert result.sample_signal is not None
    assert result.sample_signal.asset == "123"

    runs = service.list_simulation_runs(strategy.id)
    assert runs == []


def test_live_run_cycle_places_order_persists_receipt_and_cancels_on_stop(monkeypatch):
    now = datetime.utcnow()
    activity = [
        {
            "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
            "timestamp": int((now - timedelta(minutes=15)).timestamp()),
            "type": "TRADE",
            "conditionId": "0xmarket2",
            "asset": "0xyes",
            "side": "BUY",
            "outcome": "Yes",
            "size": 100,
            "usdcSize": 55,
            "price": 0.55,
            "title": "Will ETH rise?",
        }
    ]

    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=FakePolymarketDataClient(activity=activity))
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    _create_account(session_factory, account_id=11, exchange="polymarket", is_active=True)
    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="live runner 策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            execution_account_id=11,
            dry_run=False,
        )
    )

    calls = {"place": [], "cancel": []}

    class FakeAdapter:
        def place_order(self, **kwargs):
            calls["place"].append(kwargs)
            return {
                "order_id": "order-123",
                "status": "live",
                "response": {"orderID": "order-123", "status": "live"},
            }

        def cancel_order(self, order_id: str):
            calls["cancel"].append(order_id)
            return {
                "order_id": order_id,
                "status": "canceled",
                "response": {"canceled": True},
            }

    monkeypatch.setattr("app.services.polymarket_copy_service.create_adapter_for_account", lambda account: FakeAdapter())

    started = service.start_strategy(strategy.id)
    assert started is not None
    assert started.status == "running"

    result = asyncio.run(service.run_strategy_cycle(strategy.id))

    assert result is not None
    assert result.summary.executed_signal_count == 1
    assert len(calls["place"]) == 1
    assert calls["place"][0]["token_id"] == "0xyes"
    assert calls["place"][0]["side"] == "BUY"

    db = session_factory()
    try:
        signal_log = db.query(PolymarketCopySignalLog).filter(PolymarketCopySignalLog.strategy_id == strategy.id).one()
        assert signal_log.live_execution_status == "submitted"
        assert signal_log.live_order_id == "order-123"
        assert signal_log.live_order_status == "live"
        assert signal_log.live_order_response["orderID"] == "order-123"
    finally:
        db.close()

    stopped = service.stop_strategy(strategy.id)
    assert stopped is not None
    assert stopped.status == "stopped"
    assert calls["cancel"] == ["order-123"]

    db = session_factory()
    try:
        signal_log = db.query(PolymarketCopySignalLog).filter(PolymarketCopySignalLog.strategy_id == strategy.id).one()
        assert signal_log.live_execution_status == "canceled"
        assert signal_log.live_canceled_at is not None
        assert signal_log.live_cancel_response["canceled"] is True
    finally:
        db.close()


def test_run_cycle_paginates_incremental_activity_fetch_for_active_wallets():
    now = datetime.utcnow()
    activity = []
    for index in range(5):
        activity.append(
            {
                "proxyWallet": "0x1234567890abcdef1234567890abcdef12345678",
                "timestamp": int((now - timedelta(minutes=5 - index)).timestamp()),
                "type": "TRADE",
                "conditionId": f"0xmarket{index}",
                "asset": f"0xasset{index}",
                "side": "BUY",
                "outcome": "Yes",
                "size": 100,
                "usdcSize": 20,
                "price": 0.2,
                "title": f"Market {index}",
            }
        )

    client = FakePolymarketDataClient(activity=activity)
    session_factory = _build_session_factory()
    analytics_service = PolymarketTraderAnalyticsService(client=client)
    service = PolymarketCopyService(analytics_service=analytics_service, session_factory=session_factory)

    strategy = service.create_strategy(
        payload=PolymarketCopyStrategyCreate(
            strategy_name="分页 runner 策略",
            source_wallet="0x1234567890abcdef1234567890abcdef12345678",
            copy_ratio=0.5,
            min_copy_order_usdc=10,
            runner_activity_limit=2,
        )
    )

    result = asyncio.run(service.run_strategy_cycle(strategy.id))

    assert result is not None
    assert result.summary.raw_trade_count == 5
    assert result.summary.grouped_trade_count == 5
    assert result.summary.executed_signal_count == 5
    assert [call["offset"] for call in client.activity_calls] == [0, 2, 4]