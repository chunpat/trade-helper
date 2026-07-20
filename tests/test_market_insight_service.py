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


def test_market_cap_stablecoin_filter_covers_symbol_id_and_category_name():
    service = MarketInsightService()

    assert service._is_stablecoin_market_row(
        {"id": "tether", "symbol": "usdt", "name": "Tether"}
    )
    assert service._is_stablecoin_market_row(
        {"id": "ethena-usde", "symbol": "usde", "name": "Ethena USDe"}
    )
    assert service._is_stablecoin_market_row(
        {"id": "new-dollar", "symbol": "new", "name": "New Stablecoin"}
    )
    assert not service._is_stablecoin_market_row(
        {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}
    )


def test_binance_equity_classifier_distinguishes_stock_etf_and_crypto():
    service = MarketInsightService()

    assert service._classify_binance_equity_contract(
        {"baseAsset": "TSLA", "underlyingType": "TRADFI", "underlyingSubType": ["STOCK"]}
    ) == "stock_perpetual"
    assert service._classify_binance_equity_contract(
        {"baseAsset": "QQQ", "underlyingType": "TRADFI", "underlyingSubType": "ETF"}
    ) == "etf_perpetual"
    assert service._classify_binance_equity_contract(
        {"baseAsset": "BTC", "underlyingType": "COIN", "underlyingSubType": ["PoW"]}
    ) is None


def test_market_cap_volatility_refills_after_removing_stablecoins(monkeypatch):
    service = MarketInsightService()
    url = f"{service.COINGECKO_API}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 45,
        "page": 1,
        "sparkline": "true",
        "price_change_percentage": "24h",
    }
    rows = [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "current_price": 100,
            "market_cap": 1000,
            "price_change_percentage_24h": 2,
            "sparkline_in_7d": {"price": [90, 95, 100]},
        },
        {
            "id": "tether",
            "symbol": "usdt",
            "name": "Tether",
            "current_price": 1,
            "market_cap": 900,
            "price_change_percentage_24h": 0,
            "sparkline_in_7d": {"price": [1, 1, 1]},
        },
        *[
            {
                "id": f"coin-{index}",
                "symbol": f"c{index}",
                "name": f"Coin {index}",
                "current_price": index,
                "market_cap": 800 - index,
                "price_change_percentage_24h": index / 10,
                "sparkline_in_7d": {"price": [index, index + 0.5, index + 1]},
            }
            for index in range(1, 21)
        ],
    ]
    responses = {
        (url, tuple(sorted(params.items()))): FakeResponse(200, rows),
    }

    async def fake_equities(client):
        return []

    monkeypatch.setattr(
        "app.services.market_insight_service.httpx.AsyncClient",
        lambda timeout=10.0: FakeAsyncClient(responses, []),
    )
    monkeypatch.setattr(service, "_fetch_binance_equity_volatility", fake_equities)

    result = asyncio.run(service.get_market_cap_volatility(limit=20))

    assert len(result.items) == 20
    assert all(item.symbol != "USDT" for item in result.items)
    assert [item.rank for item in result.items] == list(range(1, 21))


def test_fetch_binance_equities_includes_perpetual_etf_and_bstock():
    service = MarketInsightService()
    futures_exchange_url = f"{service.BINANCE_FAPI}/exchangeInfo"
    futures_ticker_url = f"{service.BINANCE_FAPI}/ticker/24hr"
    futures_kline_url = f"{service.BINANCE_FAPI}/klines"
    spot_exchange_url = f"{service.BINANCE_API}/exchangeInfo"
    spot_ticker_url = f"{service.BINANCE_API}/ticker/24hr"
    spot_kline_url = f"{service.BINANCE_API}/klines"
    klines = [
        [0, "0", "0", "0", "100", "0"],
        [0, "0", "0", "0", "102", "0"],
        [0, "0", "0", "0", "105", "0"],
    ]
    responses = {
        (futures_exchange_url, ()): FakeResponse(200, {
            "symbols": [
                {
                    "symbol": "TSLAUSDT",
                    "baseAsset": "TSLA",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                    "underlyingType": "TRADFI",
                    "underlyingSubType": ["STOCK"],
                },
                {
                    "symbol": "QQQUSDT",
                    "baseAsset": "QQQ",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                    "underlyingType": "TRADFI",
                    "underlyingSubType": ["ETF"],
                },
            ],
        }),
        (futures_ticker_url, ()): FakeResponse(200, [
            {
                "symbol": "TSLAUSDT",
                "lastPrice": "420",
                "priceChangePercent": "2.5",
                "quoteVolume": "2000000",
            },
            {
                "symbol": "QQQUSDT",
                "lastPrice": "650",
                "priceChangePercent": "1.2",
                "quoteVolume": "1000000",
            },
        ]),
        (spot_exchange_url, ()): FakeResponse(200, {
            "symbols": [
                {
                    "symbol": "TSLABUSDT",
                    "baseAsset": "TSLAB",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                },
            ],
        }),
        (
            futures_kline_url,
            (("interval", "1h"), ("limit", 169), ("symbol", "TSLAUSDT")),
        ): FakeResponse(200, klines),
        (
            futures_kline_url,
            (("interval", "1h"), ("limit", 169), ("symbol", "QQQUSDT")),
        ): FakeResponse(200, klines),
        (
            spot_ticker_url,
            (("symbol", "TSLABUSDT"),),
        ): FakeResponse(200, {
            "lastPrice": "421",
            "priceChangePercent": "2.6",
            "quoteVolume": "500000",
        }),
        (
            spot_kline_url,
            (("interval", "1h"), ("limit", 169), ("symbol", "TSLABUSDT")),
        ): FakeResponse(200, klines),
    }
    client = FakeAsyncClient(responses, [])

    result = asyncio.run(service._fetch_binance_equity_volatility(client))

    assert {item.product_type for item in result} == {
        "stock_perpetual",
        "etf_perpetual",
        "tokenized_stock",
    }
    assert {item.symbol for item in result} == {
        "TSLAUSDT",
        "QQQUSDT",
        "TSLABUSDT",
    }
    assert all(item.volatility_7d > 0 for item in result)
