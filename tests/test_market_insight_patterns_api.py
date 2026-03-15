import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "market_insight.py"
SPEC = importlib.util.spec_from_file_location("market_insight_patterns_api_module", MODULE_PATH)
market_insight_api = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(market_insight_api)
router = market_insight_api.router


def create_test_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_get_patterns_endpoint_passes_tolerance(monkeypatch):
    captured = {}

    async def fake_get_patterns(symbol: str, interval: str, limit: int, tolerance: float):
        captured.update({
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "tolerance": tolerance,
        })
        return []

    monkeypatch.setattr(market_insight_api.market_insight_service, "get_patterns", fake_get_patterns)

    client = TestClient(create_test_app())
    response = client.get(
        "/api/v1/market-insight/patterns",
        params={"symbol": "BTCUSDT", "interval": "1h", "limit": 150, "tolerance": 0.45},
    )

    assert response.status_code == 200
    assert captured == {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "limit": 150,
        "tolerance": 0.45,
    }


def test_scan_patterns_endpoint_passes_tolerance(monkeypatch):
    captured = {}

    async def fake_scan_patterns(symbols=None, interval: str = '1h', tolerance: float = 0.35):
        captured.update({
            "symbols": symbols,
            "interval": interval,
            "tolerance": tolerance,
        })
        return []

    monkeypatch.setattr(market_insight_api.market_insight_service, "scan_patterns", fake_scan_patterns)

    client = TestClient(create_test_app())
    response = client.get(
        "/api/v1/market-insight/patterns/scan",
        params={"interval": "1h", "tolerance": 0.55},
    )

    assert response.status_code == 200
    assert captured == {
        "symbols": None,
        "interval": "1h",
        "tolerance": 0.55,
    }