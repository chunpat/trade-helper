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
    async def fake_get_activity(wallet: str, *, limit: int, hours: int):
        assert wallet == "0x1234567890abcdef1234567890abcdef12345678"
        assert limit == 20
        assert hours == 48
        return [
            PolymarketActivityItem(
                proxy_wallet=wallet,
                timestamp=datetime.utcnow(),
                activity_type="TRADE",
                title="Will BTC exceed 120k?",
            )
        ]

    monkeypatch.setattr(polymarket_api.polymarket_trader_analytics_service, "get_activity", fake_get_activity)

    client = TestClient(create_test_app())
    response = client.get(
        "/api/v1/polymarket/traders/0x1234567890abcdef1234567890abcdef12345678/activity",
        params={"limit": 20, "hours": 48},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["activity_type"] == "TRADE"


def test_get_polymarket_trader_profile_endpoint(monkeypatch):
    async def fake_analyze_trader(wallet: str):
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

    monkeypatch.setattr(polymarket_api.polymarket_trader_analytics_service, "analyze_trader", fake_analyze_trader)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/polymarket/traders/0x1234567890abcdef1234567890abcdef12345678")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Trader One"
    assert payload["followability"]["score"] == 81.0