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
    async def scan():
        return RsiDivergenceRadar(scanned_count=30, timestamp=datetime.now(timezone.utc))

    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "scan", scan)
    response = client().get("/api/v1/market-insight/rsi-divergence")
    assert response.status_code == 200
    assert response.json()["interval"] == "1h"
    assert response.json()["rsi_period"] == 14
    assert response.json()["pivot_right"] == 5


def test_rsi_detail_passes_valid_symbol(monkeypatch):
    async def detail(symbol):
        assert symbol == "BTCUSDT"
        return RsiDivergenceDetail(symbol=symbol)

    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "get_detail", detail)
    response = client().get("/api/v1/market-insight/rsi-divergence/detail", params={"symbol": "BTCUSDT"})
    assert response.status_code == 200
    assert response.json()["interval"] == "1h"


@pytest.mark.parametrize("symbol", ["../BTCUSDT", "BTCUSD", "btcusdt", ""])
def test_invalid_symbol_rejected(symbol):
    response = client().get("/api/v1/market-insight/rsi-divergence/detail", params={"symbol": symbol})
    assert response.status_code == 422


def test_data_failure_is_visible_to_client(monkeypatch):
    async def scan():
        raise ValueError("行情不可用")

    monkeypatch.setattr(market_insight_api.rsi_divergence_service, "scan", scan)
    response = client().get("/api/v1/market-insight/rsi-divergence")
    assert response.status_code == 502
    assert "暂不可用" in response.json()["detail"]
