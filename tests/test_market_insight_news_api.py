from datetime import datetime, timedelta
import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.market_insight import MarketNews


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "market_insight.py"
SPEC = importlib.util.spec_from_file_location("market_insight_news_api_module", MODULE_PATH)
market_insight_api = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(market_insight_api)
router = market_insight_api.router


def create_test_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_get_market_news_endpoint_filters_recent_items(monkeypatch):
    now = datetime.utcnow()

    async def fake_get_market_news(limit: int, symbol: str = None, hours: int = None):
        assert limit == 5
        assert symbol == "BTCUSDT"
        assert hours == 24
        return [
            MarketNews(
                title="Fresh BTC archive item",
                source="CoinDesk",
                source_domain="coindesk.com",
                published_at=now - timedelta(hours=2),
                symbols=["BTC"],
            ),
            MarketNews(
                title="Old BTC archive item",
                source="CoinDesk",
                source_domain="coindesk.com",
                published_at=now - timedelta(hours=48),
                symbols=["BTC"],
            ),
        ]

    monkeypatch.setattr(market_insight_api.market_insight_service, "get_market_news", fake_get_market_news)

    client = TestClient(create_test_app())
    response = client.get(
        "/api/v1/market-insight/news",
        params={"limit": 5, "symbol": "BTCUSDT", "hours": 24},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "Fresh BTC archive item"


def test_get_market_news_endpoint_uses_archive_fallback_when_filtered_result_empty(monkeypatch):
    now = datetime.utcnow()

    async def fake_get_market_news(limit: int, symbol: str = None, hours: int = None):
        return []

    monkeypatch.setattr(market_insight_api.market_insight_service, "get_market_news", fake_get_market_news)
    monkeypatch.setattr(
        market_insight_api.news_archive_service,
        "list_news",
        lambda limit, symbol=None, hours=None: [
            MarketNews(
                title="Archive fallback item",
                source="PANews",
                source_domain="panewslab.com",
                published_at=now - timedelta(hours=3),
                symbols=["ETH"],
            )
        ],
    )

    client = TestClient(create_test_app())
    response = client.get(
        "/api/v1/market-insight/news",
        params={"limit": 5, "symbol": "ETHUSDT", "hours": 24},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "Archive fallback item"