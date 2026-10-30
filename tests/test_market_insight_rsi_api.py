import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.rsi_divergence import RsiDivergenceDetail, RsiDivergenceRadar


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "market_insight.py"
SPEC = importlib.util.spec_from_file_location("market_insight_rsi_api_module", MODULE_PATH)
market_insight_api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(market_insight_api)


def client():
    app = FastAPI()
    app.include_router(market_insight_api.router, prefix="/api/v1")
    return TestClient(app)


def test_rsi_radar_api_uses_fixed_hourly_defaults(monkeypatch):
    async def scan(preset="strict"):
        assert preset == "strict"
        return RsiDivergenceRadar(scanned_count=30, timestamp=datetime.now(timezone.utc))

    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "scan", scan)
    response = client().get("/api/v1/market-insight/rsi-divergence")
    assert response.status_code == 200
    assert response.json()["interval"] == "1h"
    assert response.json()["rsi_period"] == 14
    assert response.json()["min_quote_volume"] == 100_000_000
    assert response.json()["pivot_right"] == 5
    assert response.json()["min_bars"] == 10
    assert response.json()["min_price_change_percent"] == 0.5
    assert response.json()["min_rsi_change"] == 5
    assert response.json()["overbought"] == 70
    assert response.json()["oversold"] == 30
    assert response.json()["require_price_pivots"] is True
    assert response.json()["price_pivot_tolerance"] == 1


def test_rsi_detail_passes_valid_symbol(monkeypatch):
    async def detail(symbol, preset="strict"):
        assert symbol == "BTCUSDT"
        assert preset == "strict"
        return RsiDivergenceDetail(symbol=symbol)

    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "get_detail", detail)
    response = client().get("/api/v1/market-insight/rsi-divergence/detail", params={"symbol": "BTCUSDT"})
    assert response.status_code == 200
    assert response.json()["interval"] == "1h"
    assert response.json()["min_bars"] == 10
    assert response.json()["min_price_change_percent"] == 0.5
    assert response.json()["min_rsi_change"] == 5


@pytest.mark.parametrize("symbol", ["../BTCUSDT", "BTCUSD", "btcusdt", ""])
def test_invalid_symbol_rejected(symbol):
    response = client().get("/api/v1/market-insight/rsi-divergence/detail", params={"symbol": symbol})
    assert response.status_code == 422


def test_data_failure_is_visible_to_client(monkeypatch):
    async def scan(preset="strict"):
        raise ValueError("行情不可用")

    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "scan", scan)
    response = client().get("/api/v1/market-insight/rsi-divergence")
    assert response.status_code == 502
    assert "暂不可用" in response.json()["detail"]


@pytest.mark.parametrize("preset", ["balanced", "strong"])
def test_rsi_preset_is_forwarded_to_radar_and_detail(monkeypatch, preset):
    from app.schemas.rsi_divergence import get_rsi_rules

    async def scan(preset):
        return RsiDivergenceRadar(**get_rsi_rules(preset).model_dump(), timestamp=datetime.now(timezone.utc))

    async def detail(symbol, preset):
        return RsiDivergenceDetail(**get_rsi_rules(preset).model_dump(), symbol=symbol)

    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "scan", scan)
    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "get_detail", detail)
    for path in ("/rsi-divergence", "/rsi-divergence/detail"):
        response = client().get(f"/api/v1/market-insight{path}", params={"preset": preset, "symbol": "BTCUSDT"})
        assert response.status_code == 200
        assert response.json()["preset"] == preset
        assert response.json()["min_rsi_change"] == (3 if preset == "balanced" else 8)


@pytest.mark.parametrize("path", ["/rsi-divergence", "/rsi-divergence/detail"])
def test_invalid_rsi_preset_is_rejected(path):
    response = client().get(f"/api/v1/market-insight{path}", params={"symbol": "BTCUSDT", "preset": "unknown"})
    assert response.status_code == 422
