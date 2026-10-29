import math

import httpx
import pytest

from app.services.bollinger_service import (
    INTERVAL_MS, BollingerService, build_signal, calculate_bands,
)

NOW = 400 * 3_600_000 + 45 * 60_000 + 1000


def klines(interval, now=NOW, last_close=120):
    duration = INTERVAL_MS[interval]
    boundary = now // duration * duration
    closes = [100] * 23 + [last_close, 10000]
    return [[boundary + (i - 24) * duration, value, value, value, value, 1000,
             boundary + (i - 23) * duration - 1] for i, value in enumerate(closes)]


@pytest.mark.parametrize("interval", INTERVAL_MS)
def test_bands_include_latest_closed_price_and_use_population_stddev(interval):
    band = calculate_bands(klines(interval), interval, NOW)
    assert band.middle == pytest.approx(100 + 20 / 24)
    assert band.upper == pytest.approx(100 + 20 / 24 + 2 * 20 * math.sqrt(23) / 24)
    assert band.lower == pytest.approx(100 + 20 / 24 - 2 * 20 * math.sqrt(23) / 24)
    assert band.close == 120
    assert band.closed_at == NOW // INTERVAL_MS[interval] * INTERVAL_MS[interval]


@pytest.mark.parametrize("last_close,direction", [(120, "above_upper"), (80, "below_lower")])
def test_all_three_periods_must_be_outside_in_same_direction(last_close, direction):
    bands = [calculate_bands(klines(interval, last_close=last_close), interval, NOW) for interval in INTERVAL_MS]
    signal = build_signal("BTCUSDT", 100_000_000, bands)
    assert signal.direction == direction
    # 15分钟收盘可独立触发，无需1h和4h在同一时刻收盘。
    assert signal.bands[0].closed_at != signal.bands[2].closed_at
    assert build_signal("BTCUSDT", 99_999_999, bands) is None
    assert build_signal("BTCUSDT", float("nan"), bands) is None
    assert build_signal("BTCUSDT", 100_000_000, bands[:2]) is None


@pytest.mark.parametrize("condition", ["inside", "touch", "opposite", "wick_only"])
def test_non_matching_period_never_alerts(condition):
    bands = [calculate_bands(klines(interval), interval, NOW) for interval in INTERVAL_MS]
    if condition == "inside":
        bands[-1].close = bands[-1].middle
    elif condition == "touch":
        bands[-1].close = bands[-1].upper
    elif condition == "opposite":
        bands[-1] = calculate_bands(klines("15m", last_close=80), "15m", NOW)
    else:
        rows = klines("15m", last_close=100)
        rows[-2][2] = 500
        bands[-1] = calculate_bands(rows, "15m", NOW)
    assert build_signal("BTCUSDT", 100_000_000, bands) is None


def test_live_candle_is_excluded_and_flat_market_does_not_alert():
    rows = klines("15m", last_close=100)
    band = calculate_bands(rows, "15m", NOW)
    assert band.close == band.upper == band.lower == 100
    rows[-1][4] = 0
    assert calculate_bands(rows, "15m", NOW) == band
    # 没有未收盘尾行时，仍保留最新已收盘K线。
    assert calculate_bands(rows[:-1], "15m", band.closed_at) == band


@pytest.mark.parametrize("problem", ["insufficient", "gap", "stale", "nan", "zero", "wrong_interval", "duplicate"])
def test_incomplete_or_bad_data_is_rejected(problem):
    rows = klines("1h")
    if problem in {"insufficient", "gap"}:
        rows.pop(10)
    elif problem == "stale":
        rows.pop(-2)
    elif problem in {"nan", "zero"}:
        rows[-2][4] = "nan" if problem == "nan" else 0
    elif problem == "wrong_interval":
        rows[-2][6] -= 1
    else:
        rows[10] = rows[9]
    with pytest.raises(ValueError):
        calculate_bands(rows, "1h", NOW)


def mock_exchange(monkeypatch, fail=None, count=2, stale=False, volumes=None):
    calls = []
    clock = [NOW]
    symbols = [f"COIN{i}USDT" for i in range(count)]
    active = symbols + ["SMALLUSDT", "DELISTUSDT", "DELIVERYUSDT", "STOCKUSDT"]
    info = [{"symbol": symbol, "quoteAsset": "USDT", "contractType": "PERPETUAL",
             "status": "TRADING", "underlyingType": "COIN"} for symbol in active]
    info[-3]["status"] = "SETTLING"
    info[-2]["contractType"] = "CURRENT_QUARTER"
    info[-1]["underlyingType"] = "EQUITY"

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("exchangeInfo"):
            return httpx.Response(200, json={"symbols": info})
        if request.url.path.endswith("24hr"):
            return httpx.Response(200, json=[{
                "symbol": symbol,
                "quoteVolume": (volumes or {}).get(symbol, 99_999_999 if symbol == "SMALLUSDT" else 100_000_000),
                "volume": 9_999_999_999, "closeTime": clock[0] - (600_000 if stale else 0),
            } for symbol in active])
        symbol = request.url.params["symbol"]
        interval = request.url.params["interval"]
        assert int(request.url.params["limit"]) == 25  # 24根已收盘及最多1根未收盘。
        if fail and symbol == symbols[-1] and interval == "1h":
            return httpx.Response(429, json={"msg": "limited"})
        return httpx.Response(200, json=klines(interval, now=clock[0]))

    client_class = httpx.AsyncClient
    monkeypatch.setattr("app.services.bollinger_service.httpx.AsyncClient", lambda **kwargs:
                        client_class(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr("app.services.bollinger_service.time.time", lambda: clock[0] / 1000)
    return calls, clock


@pytest.mark.asyncio
async def test_scan_rechecks_every_minute_and_refreshes_bands_at_their_close(monkeypatch):
    calls, clock = mock_exchange(monkeypatch, count=31)
    service = BollingerService()
    result = await service.scan()
    assert result.scanned_count == len(result.signals) == 31
    assert result.failed_count == 0
    assert result.period == 24 and result.stddev_multiplier == 2
    initial = len(calls)
    clock[0] += 30_000
    assert await service.scan() == result
    assert len(calls) == initial
    clock[0] = (clock[0] // 60_000 + 1) * 60_000
    minute_result = await service.scan()
    assert minute_result.timestamp > result.timestamp
    assert minute_result.signals == result.signals
    # 未到新的K线收盘时间，但每分钟仍重新检查成交额。
    assert len(calls) == initial + 2
    initial = len(calls)
    clock[0] = (clock[0] // 900_000 + 1) * 900_000
    refreshed = await service.scan()
    assert refreshed.timestamp > result.timestamp
    # 这一边界正好是新小时；4h数据可复用，1h和15m必须更新。
    intervals = [req.url.params["interval"] for req in calls[initial:] if req.url.path.endswith("klines")]
    assert len(intervals) == 62
    assert set(intervals) == {"1h", "15m"}


@pytest.mark.asyncio
async def test_volume_crossing_threshold_is_detected_within_same_15m_candle(monkeypatch):
    volumes = {"COIN0USDT": 99_999_999}
    _, clock = mock_exchange(monkeypatch, count=1, volumes=volumes)
    service = BollingerService()
    assert (await service.scan()).signals == []
    volumes["COIN0USDT"] = 100_000_000
    clock[0] += 60_000
    assert [item.symbol for item in (await service.scan()).signals] == ["COIN0USDT"]
    volumes["COIN0USDT"] = 99_999_999
    clock[0] += 60_000
    assert (await service.scan()).signals == []
    assert clock[0] // 900_000 == NOW // 900_000


@pytest.mark.asyncio
async def test_partial_failure_is_visible_and_retries_missing_period(monkeypatch):
    calls, _ = mock_exchange(monkeypatch, fail=True)
    service = BollingerService()
    result = await service.scan()
    assert result.scanned_count == result.failed_count == 1
    assert [signal.symbol for signal in result.signals] == ["COIN0USDT"]
    initial = len(calls)
    await service.scan()
    assert len(calls) == initial + 3  # 两个市场接口及失败的1h请求。


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
async def test_total_failure_or_stale_volume_never_returns_empty_success(monkeypatch, stale):
    mock_exchange(monkeypatch, count=1, fail=True, stale=stale)
    with pytest.raises(ValueError, match="全部合约"):
        await BollingerService().scan()
