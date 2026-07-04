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


def test_altcoin_starters_prefers_early_volume_expansion_and_rejects_chasing(monkeypatch):
    service = MarketInsightService()
    ticker_url = f"{service.BINANCE_FAPI}/ticker/24hr"
    kline_url = f"{service.BINANCE_FAPI}/klines"
    tickers = [
        {"symbol": "GOODUSDT", "priceChangePercent": "4", "quoteVolume": "20000000", "lastPrice": "1.04", "priceChange": ".04", "volume": "100", "highPrice": "1.1", "lowPrice": ".9"},
        {"symbol": "LATEUSDT", "priceChangePercent": "28", "quoteVolume": "90000000", "lastPrice": "2", "priceChange": ".4", "volume": "100", "highPrice": "2.1", "lowPrice": "1.5"},
        {"symbol": "BTCUSDT", "priceChangePercent": "3", "quoteVolume": "90000000", "lastPrice": "60000", "priceChange": "100", "volume": "100", "highPrice": "61000", "lowPrice": "59000"},
    ]
    # 12 complete candles + one live candle: latest complete candle has 3x volume
    klines = [[0, "1", "1.01", ".99", "1", "100"] for _ in range(13)]
    klines[-5][1] = "1"
    klines[-2][1] = "1.02"
    klines[-2][4] = "1.04"
    klines[-2][5] = "300"
    responses = {
        (ticker_url, ()): FakeResponse(200, tickers),
        (kline_url, (("interval", "15m"), ("limit", 13), ("symbol", "GOODUSDT"))): FakeResponse(200, klines),
    }
    monkeypatch.setattr(
        "app.services.market_insight_service.httpx.AsyncClient",
        lambda timeout=10.0: FakeAsyncClient(responses, []),
    )

    result = asyncio.run(service.get_altcoin_starters())

    assert [item.symbol for item in result] == ["GOODUSDT"]
    assert result[0].volume_ratio == 3.0
    assert 0 < result[0].momentum_1h < 6
    assert result[0].startup_score > 0


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


def test_get_rainbow_bands_returns_positive_realistic_price_ranges():
    service = MarketInsightService()

    bands = asyncio.run(service.get_rainbow_bands())

    assert len(bands) == 9
    prices = [band.price for band in bands]
    assert prices == sorted(prices, reverse=True)
    assert all(price > 1000 for price in prices)
    hold_band = next(band for band in bands if band.name == "持有")
    assert 10000 < hold_band.price < 500000
