import asyncio
from datetime import datetime

from app.services.market_insight_service import MarketInsightService


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class FakeAsyncClient:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        self._calls.append((url, params))
        key = (url, tuple(sorted((params or {}).items())))
        return self._responses[key]


def test_get_market_sentiment_uses_futures_data_ratio_endpoint(monkeypatch):
    service = MarketInsightService()
    calls = []
    responses = {
        (
            f"{service.BINANCE_FAPI}/fundingRate",
            (("limit", 1), ("symbol", "DOTUSDT")),
        ): FakeResponse(200, [{"fundingRate": "0.0004"}]),
        (
            f"{service.BINANCE_FUTURES_DATA}/topLongShortAccountRatio",
            (("limit", 1), ("period", "5m"), ("symbol", "DOTUSDT")),
        ): FakeResponse(200, [{"longShortRatio": "1.7159"}]),
        (
            f"{service.BINANCE_FAPI}/openInterest",
            (("symbol", "DOTUSDT"),),
        ): FakeResponse(200, {"openInterest": "123456.7"}),
    }

    monkeypatch.setattr(
        "app.services.market_insight_service.httpx.AsyncClient",
        lambda timeout=10.0: FakeAsyncClient(responses, calls),
    )

    sentiments = asyncio.run(service.get_market_sentiment(["DOTUSDT"]))

    assert len(sentiments) == 1
    assert sentiments[0].symbol == "DOTUSDT"
    assert sentiments[0].long_short_ratio == 1.7159
    assert all("/fapi/v1/topLongShortAccountRatio" not in url for url, _ in calls)
    assert any("/futures/data/topLongShortAccountRatio" in url for url, _ in calls)


def test_get_market_sentiment_falls_back_to_global_ratio_when_top_ratio_unavailable(monkeypatch):
    service = MarketInsightService()
    responses = {
        (
            f"{service.BINANCE_FAPI}/fundingRate",
            (("limit", 1), ("symbol", "DOTUSDT")),
        ): FakeResponse(200, [{"fundingRate": "0.0002"}]),
        (
            f"{service.BINANCE_FUTURES_DATA}/topLongShortAccountRatio",
            (("limit", 1), ("period", "5m"), ("symbol", "DOTUSDT")),
        ): FakeResponse(404, text="<html>not found</html>"),
        (
            f"{service.BINANCE_FUTURES_DATA}/globalLongShortAccountRatio",
            (("limit", 1), ("period", "5m"), ("symbol", "DOTUSDT")),
        ): FakeResponse(200, [{"longShortRatio": "1.4981"}]),
        (
            f"{service.BINANCE_FAPI}/openInterest",
            (("symbol", "DOTUSDT"),),
        ): FakeResponse(200, {"openInterest": "7890"}),
    }

    monkeypatch.setattr(
        "app.services.market_insight_service.httpx.AsyncClient",
        lambda timeout=10.0: FakeAsyncClient(responses, []),
    )

    sentiments = asyncio.run(service.get_market_sentiment(["DOTUSDT"]))

    assert len(sentiments) == 1
    assert sentiments[0].long_short_ratio == 1.4981
    assert sentiments[0].sentiment_score in {"neutral", "greed", "fear", "extreme_greed", "extreme_fear"}
