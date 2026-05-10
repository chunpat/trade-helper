import importlib.util
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.polymarket import (
    PolymarketActivityItem,
    PolymarketTraderCachePoolInfo,
    PolymarketTraderCacheStatus,
    PolymarketFollowabilityComponent,
    PolymarketFollowabilityReport,
    PolymarketTraderProfile,
    PolymarketTraderSummary,
)
from app.schemas.polymarket_copy import (
    PolymarketCopyRunnerStatus,
    PolymarketCopySimulationRequest,
    PolymarketCopySimulationResult,
    PolymarketCopySimulationSignal,
    PolymarketCopySimulationRunRead,
    PolymarketCopySimulationSummary,
    PolymarketCopyStrategyRead,
)


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "polymarket.py"
SPEC = importlib.util.spec_from_file_location("polymarket_api_module", MODULE_PATH)
polymarket_api = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(polymarket_api)
router = polymarket_api.router


def create_test_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _followability(score: float = 72.0) -> PolymarketFollowabilityReport:
    return PolymarketFollowabilityReport(
        score=score,
        verdict="watchlist",
        likely_bot=False,
        skip_recommended=False,
        reasons=["测试用"],
        bot_reasons=[],
        median_trade_interval_seconds=300,
        trades_per_hour_30d=1.2,
        avg_trade_size_usdc_30d=120,
        top_market_share_30d=0.4,
        components=[
            PolymarketFollowabilityComponent(name="latency", score=80, weight=0.35, reason="ok")
        ],
    )


def test_list_polymarket_traders_endpoint(monkeypatch):
    async def fake_get_pool(**kwargs):
        assert kwargs["category"] == "OVERALL"
        assert kwargs["time_period"] == "WEEK"
        assert kwargs["order_by"] == "PNL"
        assert kwargs["limit"] == 5
        return [
            PolymarketTraderSummary(
                wallet_address="0x1234567890abcdef1234567890abcdef12345678",
                name="Trader One",
                pseudonym="Calm-Owl",
                verified_badge=True,
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
                followability=_followability(),
                analysis_notes=["测试"],
            )
        ]

    monkeypatch.setattr(polymarket_api.polymarket_trader_cache_service, "get_pool", fake_get_pool)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/polymarket/traders", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["wallet_address"] == "0x1234567890abcdef1234567890abcdef12345678"
    assert payload[0]["followability"]["verdict"] == "watchlist"


def test_polymarket_trader_cache_status_endpoint(monkeypatch):
    def fake_status():
        return PolymarketTraderCacheStatus(
            running=True,
            interval_seconds=300,
            ttl_seconds=600,
            default_pools=["OVERALL:WEEK:PNL:10"],
            pools=[
                PolymarketTraderCachePoolInfo(
                    cache_key="OVERALL:WEEK:PNL:10",
                    category="OVERALL",
                    time_period="WEEK",
                    order_by="PNL",
                    limit=10,
                    trader_count=10,
                    is_stale=False,
                )
            ],
        )

    monkeypatch.setattr(polymarket_api.polymarket_trader_cache_service, "get_status", fake_status)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/polymarket/traders/cache/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["running"] is True
    assert payload["pools"][0]["cache_key"] == "OVERALL:WEEK:PNL:10"


def test_polymarket_trader_cache_refresh_endpoint(monkeypatch):
    async def fake_refresh_pool(**kwargs):
        assert kwargs["category"] == "OVERALL"
        assert kwargs["time_period"] == "WEEK"
        assert kwargs["order_by"] == "PNL"
        assert kwargs["limit"] == 10
        return []

    def fake_status():
        return PolymarketTraderCacheStatus(
            running=True,
            interval_seconds=300,
            ttl_seconds=600,
            default_pools=["OVERALL:WEEK:PNL:10"],
            pools=[
                PolymarketTraderCachePoolInfo(
                    cache_key="OVERALL:WEEK:PNL:10",
                    category="OVERALL",
                    time_period="WEEK",
                    order_by="PNL",
                    limit=10,
                    trader_count=10,
                    is_stale=False,
                )
            ],
        )

    monkeypatch.setattr(polymarket_api.polymarket_trader_cache_service, "refresh_pool", fake_refresh_pool)
    monkeypatch.setattr(polymarket_api.polymarket_trader_cache_service, "get_status", fake_status)

    client = TestClient(create_test_app())
    response = client.post("/api/v1/polymarket/traders/cache/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cache_key"] == "OVERALL:WEEK:PNL:10"


def test_get_polymarket_trader_activity_endpoint(monkeypatch):
    async def fake_get_activity(wallet: str, *, limit: int, hours: int, force_refresh: bool):
        assert wallet == "0x1234567890abcdef1234567890abcdef12345678"
        assert limit == 20
        assert hours == 48
        assert force_refresh is False
        return [
            PolymarketActivityItem(
                proxy_wallet=wallet,
                timestamp=datetime.utcnow(),
                activity_type="TRADE",
                title="Will BTC exceed 120k?",
            )
        ]

    monkeypatch.setattr(polymarket_api.polymarket_trader_cache_service, "get_trader_activity", fake_get_activity)

    client = TestClient(create_test_app())
    response = client.get(
        "/api/v1/polymarket/traders/0x1234567890abcdef1234567890abcdef12345678/activity",
        params={"limit": 20, "hours": 48},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["activity_type"] == "TRADE"


def test_get_polymarket_trader_profile_endpoint(monkeypatch):
    async def fake_get_trader_profile(wallet: str, *, force_refresh: bool):
        assert force_refresh is False
        return PolymarketTraderProfile(
            wallet_address=wallet,
            name="Trader One",
            pseudonym="Calm-Owl",
            verified_badge=True,
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
            followability=_followability(81),
            analysis_notes=["测试"],
            created_at=datetime.utcnow(),
            recent_markets=["Will BTC exceed 120k?"],
            recent_activities=[],
            current_positions=[],
            recent_closed_positions=[],
        )

    monkeypatch.setattr(polymarket_api.polymarket_trader_cache_service, "get_trader_profile", fake_get_trader_profile)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/polymarket/traders/0x1234567890abcdef1234567890abcdef12345678")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Trader One"
    assert payload["followability"]["score"] == 81.0


def _copy_strategy(strategy_id: int = 1) -> PolymarketCopyStrategyRead:
    now = datetime.utcnow()
    return PolymarketCopyStrategyRead(
        id=strategy_id,
        strategy_name="测试同比例跟单",
        source_wallet="0x1234567890abcdef1234567890abcdef12345678",
        execution_account_id=3,
        execution_account_name="主账户",
        execution_account_exchange="binance",
        status="draft",
        copy_mode="proportional_notional",
        copy_ratio=0.25,
        min_copy_order_usdc=20.0,
        max_order_usdc=200.0,
        max_position_notional_usdc=1000.0,
        max_market_exposure_usdc=500.0,
        max_signal_delay_seconds=120,
        max_slippage_bps=80,
        close_only=False,
        dry_run=True,
        same_outcome_only=True,
        follow_reduce_only_after_open=True,
        allow_partial_close_sync=True,
        signal_cooldown_seconds=15,
        runner_lookback_hours=24,
        runner_activity_limit=120,
        allowed_markets=[],
        blocked_markets=[],
        last_started_at=None,
        last_stopped_at=None,
        last_run_at=None,
        last_error=None,
        notes=None,
        created_at=now,
        updated_at=now,
    )


def test_create_polymarket_copy_strategy_endpoint(monkeypatch):
    def fake_create_strategy(payload):
        assert payload.strategy_name == "测试同比例跟单"
        assert payload.copy_ratio == 0.25
        assert payload.execution_account_id == 3
        return _copy_strategy(3)

    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "create_strategy", fake_create_strategy)

    client = TestClient(create_test_app())
    response = client.post(
        "/api/v1/polymarket/strategies",
        json={
            "strategy_name": "测试同比例跟单",
            "source_wallet": "0x1234567890abcdef1234567890abcdef12345678",
            "execution_account_id": 3,
            "copy_ratio": 0.25,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 3
    assert payload["copy_mode"] == "proportional_notional"
    assert payload["execution_account_id"] == 3


def test_simulate_polymarket_copy_strategy_endpoint(monkeypatch):
    async def fake_simulate(strategy_id, payload: PolymarketCopySimulationRequest):
        assert strategy_id == 5
        assert payload.lookback_hours == 96
        return PolymarketCopySimulationResult(
            strategy=_copy_strategy(5),
            simulation_run_id=8,
            lookback_hours=payload.lookback_hours,
            activity_limit=payload.activity_limit,
            summary=PolymarketCopySimulationSummary(
                raw_trade_count=12,
                grouped_trade_count=8,
                simulated_signal_count=8,
                executed_signal_count=6,
                skipped_signal_count=2,
                total_source_notional_usdc=640.0,
                total_copied_notional_usdc=160.0,
                skip_reason_counts={"below_min_copy_order": 2},
            ),
            signals=[
                PolymarketCopySimulationSignal(
                    signal_index=1,
                    signal_type="OPEN",
                    source_timestamp=datetime.utcnow(),
                    title="Test market",
                    condition_id="0xmarket",
                    asset="0xasset",
                    outcome="Yes",
                    side="BUY",
                    source_trade_usdc=100.0,
                    source_position_before=0.0,
                    source_position_after=200.0,
                    follower_order_usdc=25.0,
                    follower_position_before=0.0,
                    follower_position_after=50.0,
                    status="executed",
                )
            ],
            notes=["测试"],
        )

    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "simulate_strategy", fake_simulate)

    client = TestClient(create_test_app())
    response = client.post(
        "/api/v1/polymarket/strategies/5/simulate",
        json={"lookback_hours": 96, "activity_limit": 150},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["simulation_run_id"] == 8
    assert payload["summary"]["executed_signal_count"] == 6
    assert payload["signals"][0]["signal_type"] == "OPEN"


def test_list_polymarket_copy_strategies_endpoint(monkeypatch):
    def fake_list_strategies():
        return [_copy_strategy(1), _copy_strategy(2)]

    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "list_strategies", fake_list_strategies)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/polymarket/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["copy_mode"] == "proportional_notional"


def test_start_stop_polymarket_copy_strategy_endpoints(monkeypatch):
    def fake_start(strategy_id: int):
        assert strategy_id == 7
        strategy = _copy_strategy(7)
        strategy.status = "running"
        return strategy

    def fake_stop(strategy_id: int):
        assert strategy_id == 7
        strategy = _copy_strategy(7)
        strategy.status = "stopped"
        return strategy

    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "start_strategy", fake_start)
    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "stop_strategy", fake_stop)

    client = TestClient(create_test_app())
    start_response = client.post("/api/v1/polymarket/strategies/7/start")
    stop_response = client.post("/api/v1/polymarket/strategies/7/stop")

    assert start_response.status_code == 200
    assert start_response.json()["status"] == "running"
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"


def test_start_polymarket_copy_strategy_endpoint_returns_400_for_live_block(monkeypatch):
    def fake_start(_strategy_id: int):
        raise ValueError("当前仓库尚未实现 Polymarket 私有下单适配器，暂时不能启动真实交易策略")

    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "start_strategy", fake_start)

    client = TestClient(create_test_app())
    response = client.post("/api/v1/polymarket/strategies/7/start")

    assert response.status_code == 400
    assert response.json()["detail"] == "当前仓库尚未实现 Polymarket 私有下单适配器，暂时不能启动真实交易策略"


def test_list_polymarket_copy_strategy_runs_endpoint(monkeypatch):
    def fake_get_strategy(strategy_id: int):
        return _copy_strategy(strategy_id)

    def fake_list_runs(strategy_id: int, limit: int = 20):
        assert strategy_id == 9
        assert limit == 5
        now = datetime.utcnow()
        return [
            PolymarketCopySimulationRunRead(
                id=11,
                strategy_id=9,
                lookback_hours=72,
                activity_limit=200,
                raw_trade_count=20,
                grouped_trade_count=12,
                simulated_signal_count=12,
                executed_signal_count=10,
                skipped_signal_count=2,
                total_source_notional_usdc=900.0,
                total_copied_notional_usdc=225.0,
                summary={"executed_signal_count": 10},
                created_at=now,
                updated_at=now,
            )
        ]

    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "get_strategy", fake_get_strategy)
    monkeypatch.setattr(polymarket_api.polymarket_copy_service, "list_simulation_runs", fake_list_runs)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/polymarket/strategies/9/runs", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == 11
    assert payload[0]["executed_signal_count"] == 10


def test_get_polymarket_copy_runner_status_endpoint(monkeypatch):
    def fake_status():
        return PolymarketCopyRunnerStatus(running=True, interval_seconds=15, strategy_count=2)

    monkeypatch.setattr(polymarket_api.polymarket_copy_runner_service, "get_status", fake_status)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/polymarket/copy-runner/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["running"] is True
    assert payload["strategy_count"] == 2