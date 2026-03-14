import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "market_insight.py"
SPEC = importlib.util.spec_from_file_location("market_insight_api_module_klines", MODULE_PATH)
market_insight_api = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(market_insight_api)
router = market_insight_api.router


def create_test_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_get_klines_endpoint_accepts_1500_limit(monkeypatch):
    async def fake_get_klines(symbol: str, interval: str, limit: int):
        assert symbol == "BTCUSDT"
        assert interval == "1h"
        assert limit == 1500
        return [[1, "100", "101", "99", "100", "10"]]

    monkeypatch.setattr(market_insight_api.market_insight_service, "get_klines", fake_get_klines)

    client = TestClient(create_test_app())
    response = client.get(
        "/api/v1/market-insight/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "limit": 1500},
    )

    assert response.status_code == 200
    assert response.json() == [[1, "100", "101", "99", "100", "10"]]
