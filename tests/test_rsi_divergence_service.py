import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.schemas.rsi_divergence import RsiCandle, RsiDivergenceDetail, get_rsi_rules
from app.services.rsi_divergence_service import (
    HOUR_MS,
    RsiDivergenceService,
    analyze_klines,
    calculate_rsi,
    detect_divergences,
)


def pivot_candles(direction="bullish", first=20, second=30, length=36):
    candles = [RsiCandle(time=i * HOUR_MS, open=100, high=101, low=99, close=100, rsi=50)
               for i in range(length)]
    if direction == "bullish":
        candles[first].rsi, candles[first].low = 20, 95
        candles[second].rsi, candles[second].low = 30, 90
    else:
        candles[first].rsi, candles[first].high = 80, 105
        candles[second].rsi, candles[second].high = 70, 110
    return candles


def raw_klines(count=60):
    return [[i * HOUR_MS, "100", "101", "99", "100", "1000", (i + 1) * HOUR_MS - 1]
            for i in range(count)]


def test_rsi_matches_wilder_reference_and_does_not_repeat_seed_delta():
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
              46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03]
    values = calculate_rsi(closes)
    assert values[:14] == [None] * 14
    assert values[14:] == pytest.approx([70.464135, 66.249619, 66.480942], abs=0.00001)


@pytest.mark.parametrize("closes,expected", [
    (list(range(1, 31)), 100), (list(range(31, 1, -1)), 0), ([100] * 30, 50),
])
def test_rsi_handles_one_direction_and_flat_prices(closes, expected):
    assert calculate_rsi(closes)[14:] == [expected] * 16
    assert calculate_rsi(closes[:14]) == [None] * 14


@pytest.mark.parametrize("direction,label", [("bullish", "底背离"), ("bearish", "顶背离")])
def test_divergence_waits_for_five_closed_confirmation_bars(direction, label):
    candles = pivot_candles(direction)
    assert detect_divergences("BTCUSDT", candles[:-1]) == []
    signals = detect_divergences("BTCUSDT", candles)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.direction == direction
    assert signal.label == label
    assert signal.previous.time == 20 * HOUR_MS
    assert signal.current.time == 30 * HOUR_MS
    assert signal.confirmed_at == 36 * HOUR_MS
    assert signal.bars_between == 10
    assert signal.last_rsi == 50


def test_later_candles_cannot_rewrite_already_confirmed_signal():
    candles = pivot_candles()
    original = detect_divergences("BTCUSDT", candles)[0]
    candles.extend(RsiCandle(time=i * HOUR_MS, open=100, high=101, low=50, close=100, rsi=10)
                   for i in range(36, 45))
    repeated = next(item for item in detect_divergences("BTCUSDT", candles)
                    if item.confirmed_at == original.confirmed_at)
    assert repeated.previous == original.previous
    assert repeated.current == original.current


@pytest.mark.parametrize("same", ["price", "rsi"])
def test_equal_price_or_rsi_is_not_divergence(same):
    candles = pivot_candles()
    if same == "price":
        candles[30].low = candles[20].low
    else:
        candles[30].rsi = candles[20].rsi
    assert detect_divergences("BTCUSDT", candles) == []


@pytest.mark.parametrize("gap,expected", [(9, 0), (10, 1), (60, 1), (61, 0)])
def test_pivot_distance_is_bounded(gap, expected):
    candles = pivot_candles(second=20 + gap, length=26 + gap)
    assert len(detect_divergences("BTCUSDT", candles)) == expected


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("failure", ["price_change", "rsi_change", "extreme_zone", "prior_price_pivot", "current_price_pivot", "equal_price_neighbor"])
def test_strict_filters_reject_weak_or_misaligned_divergence(direction, failure):
    candles = pivot_candles(direction)
    bullish = direction == "bullish"
    price_field = "low" if bullish else "high"
    first, second = candles[20], candles[30]
    if failure == "price_change":
        setattr(second, price_field, getattr(first, price_field) * (0.996 if bullish else 1.004))
    elif failure == "rsi_change":
        second.rsi = first.rsi + (4.99 if bullish else -4.99)
    elif failure == "extreme_zone":
        first.rsi, second.rsi = (31, 40) if bullish else (69, 60)
    else:
        pivot = 20 if failure == "prior_price_pivot" else 30
        value = getattr(candles[pivot], price_field)
        if failure != "equal_price_neighbor":
            value += -1 if bullish else 1
        setattr(candles[pivot + 1], price_field, value)
    assert detect_divergences("BTCUSDT", candles) == []


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_strict_thresholds_are_inclusive(direction):
    candles = pivot_candles(direction)
    if direction == "bullish":
        candles[20].rsi, candles[30].rsi = 30, 35
        candles[30].low = candles[20].low * 0.995
    else:
        candles[20].rsi, candles[30].rsi = 70, 65
        candles[30].high = candles[20].high * 1.005
    assert len(detect_divergences("BTCUSDT", candles)) == 1


@pytest.mark.parametrize("prior_price,price,prior_rsi,rsi", [
    (81527.7, 81594.3, 69.90, 64.92),
    (0.9454, 0.9455, 69.43, 68.29),
    (0.0050556, 0.0051853, 72.77, 68.14),
])
def test_screenshot_weak_bearish_signals_are_filtered(prior_price, price, prior_rsi, rsi):
    candles = pivot_candles("bearish")
    for candle in candles:
        candle.open = candle.close = prior_price * 0.98
        candle.high, candle.low = prior_price * 0.99, prior_price * 0.97
    candles[20].high, candles[20].rsi = prior_price, prior_rsi
    candles[30].high, candles[30].rsi = price, rsi
    assert detect_divergences("BTCUSDT", candles) == []


def test_invalid_price_pivot_is_not_skipped_to_find_an_older_pair():
    candles = pivot_candles(second=40, length=46)
    # 20→40满足强背离，但中间30也是RSI低点，不能跳过它配对。
    candles[30].rsi, candles[30].low = 25, 89
    candles[31].low = 88
    assert detect_divergences("BTCUSDT", candles) == []


def test_only_adjacent_rsi_pivots_are_compared():
    candles = pivot_candles(second=40, length=46)
    candles[30].rsi, candles[30].low = 35, 91
    signals = detect_divergences("BTCUSDT", candles)
    assert all(item.current.time != 40 * HOUR_MS for item in signals)


def test_open_candle_is_excluded_and_last_closed_candle_is_kept():
    rows = raw_klines()
    result = analyze_klines("BTCUSDT", rows, 59 * HOUR_MS + 100)
    assert len(result.candles) == 59
    assert result.candles[-1].time == 58 * HOUR_MS
    rows[-1][4] = "1000000"
    assert analyze_klines("BTCUSDT", rows, 59 * HOUR_MS + 100) == result
    closed = analyze_klines("BTCUSDT", raw_klines(), 60 * HOUR_MS)
    assert len(closed.candles) == 60
    assert closed.candles[-1].rsi == 50


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_real_prices_produce_divergence_only_after_confirmation(direction):
    closes = ([100 + i % 2 for i in range(50)]
              + [100 - 3 * i for i in range(1, 11)]
              + [70 + 2 * i for i in range(1, 11)]
              + [90 - 1.5 * i for i in range(1, 16)]
              + [67.5 + 2 * i for i in range(1, 11)])
    if direction == "bearish":
        closes = [300 - price for price in closes]
    rows = [[i * HOUR_MS, price, price + 1, price - 1, price, 100, (i + 1) * HOUR_MS - 1]
            for i, price in enumerate(closes)]
    before = analyze_klines("BTCUSDT", rows[:90], 89 * HOUR_MS + 1)
    assert before.signals == []
    after = analyze_klines("BTCUSDT", rows[:91], 90 * HOUR_MS)
    assert len(after.signals) == 1
    signal = after.signals[0]
    assert signal.direction == direction
    assert signal.previous.time == 59 * HOUR_MS
    assert signal.current.time == 84 * HOUR_MS
    assert signal.confirmed_at == 90 * HOUR_MS


@pytest.mark.parametrize("problem", ["gap", "non_finite", "stale", "wrong_interval"])
def test_invalid_or_stale_data_is_not_reported_as_no_signal(problem):
    rows = raw_klines()
    if problem == "gap":
        rows.pop(25)
    elif problem == "non_finite":
        rows[25][4] = "NaN"
    elif problem == "stale":
        rows.pop()
    else:
        rows[25][6] -= 1
    with pytest.raises(ValueError):
        analyze_klines("BTCUSDT", rows, 60 * HOUR_MS)


def install_exchange(monkeypatch, fail_symbols=(), old_signal=False):
    now_ms = 60 * HOUR_MS + 100
    calls = []
    symbols = ["BTCUSDT", "ETHUSDT", "SMALLUSDT", "USDCUSDT", "STOCKUSDT", "OLDUSDT", "DELIVERYUSDT"]
    info = [{"symbol": symbol, "baseAsset": symbol[:-4], "status": "TRADING",
             "quoteAsset": "USDT", "contractType": "PERPETUAL", "underlyingType": "COIN"}
            for symbol in symbols]
    info[4]["underlyingType"] = "EQUITY"
    info[5]["status"] = "SETTLING"
    info[6]["contractType"] = "CURRENT_QUARTER"

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("exchangeInfo"):
            return httpx.Response(200, json={"symbols": info})
        if request.url.path.endswith("24hr"):
            return httpx.Response(200, json=[{"symbol": symbol,
                "quoteVolume": "100" if symbol == "SMALLUSDT" else "50000000"} for symbol in symbols])
        assert request.url.params["interval"] == "1h"
        assert request.url.params["limit"] == "499"
        assert request.url.params["endTime"] == str(now_ms)
        if request.url.params["symbol"] in fail_symbols:
            return httpx.Response(429, json={"msg": "rate limit"})
        return httpx.Response(200, json=raw_klines())

    client_class = httpx.AsyncClient
    monkeypatch.setattr("app.services.rsi_divergence_service.httpx.AsyncClient",
                        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr("app.services.rsi_divergence_service.time.time", lambda: now_ms / 1000)

    def fake_analyze(symbol, rows, now):
        signal = detect_divergences(symbol, pivot_candles())[0]
        signal.confirmed_at = now - (25 if old_signal else 1) * HOUR_MS
        return RsiDivergenceDetail(symbol=symbol, signals=[signal])

    monkeypatch.setattr("app.services.rsi_divergence_service.analyze_klines", fake_analyze)
    return calls, now_ms


def test_scan_includes_btc_eth_independently_of_breakout_and_caches(monkeypatch):
    calls, now_ms = install_exchange(monkeypatch)
    service = RsiDivergenceService()

    async def run():
        first, second = await asyncio.gather(service.scan(), service.scan())
        assert first == second
        assert [item.symbol for item in first.signals] == ["BTCUSDT", "ETHUSDT"]
        assert first.scanned_count == 2
        assert first.failed_count == 0
        assert first.timestamp == datetime.fromtimestamp(now_ms / 1000, timezone.utc)
        await service.get_detail("BTCUSDT")

    asyncio.run(run())
    assert len(calls) == 4
    assert service._cached("radar", 61 * HOUR_MS) is None


def test_scan_reports_partial_failure_and_retries_failed_symbol(monkeypatch):
    calls, _ = install_exchange(monkeypatch, fail_symbols={"ETHUSDT"})
    service = RsiDivergenceService()

    async def run():
        result = await service.scan()
        assert result.scanned_count == result.failed_count == 1
        assert [item.symbol for item in result.signals] == ["BTCUSDT"]
        await service.scan()

    asyncio.run(run())
    kline_calls = [request for request in calls if request.url.path.endswith("klines")]
    assert len(kline_calls) == 3


def test_total_failure_raises_instead_of_empty_success(monkeypatch):
    install_exchange(monkeypatch, fail_symbols={"BTCUSDT", "ETHUSDT"})
    with pytest.raises(ValueError, match="所有合约"):
        asyncio.run(RsiDivergenceService().scan())


def test_scan_excludes_signals_confirmed_more_than_24_hours_ago(monkeypatch):
    install_exchange(monkeypatch, old_signal=True)
    result = asyncio.run(RsiDivergenceService().scan())
    assert result.signals == []
    assert result.scanned_count == 2


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_presets_apply_increasing_thresholds_to_same_candles(direction):
    candles = pivot_candles(direction, second=32, length=38)
    if direction == "bullish":
        candles[20].rsi, candles[32].rsi = 30, 36
    else:
        candles[20].rsi, candles[32].rsi = 70, 64
    assert len(detect_divergences("BTCUSDT", candles, rules=get_rsi_rules("balanced"))) == 1
    assert len(detect_divergences("BTCUSDT", candles, rules=get_rsi_rules("strict"))) == 1
    assert detect_divergences("BTCUSDT", candles, rules=get_rsi_rules("strong")) == []
    candles = pivot_candles(direction, second=32, length=38)
    assert len(detect_divergences("BTCUSDT", candles, rules=get_rsi_rules("strong"))) == 1


def test_presets_reuse_market_data_without_mutating_strict_cache(monkeypatch):
    calls, _ = install_exchange(monkeypatch)

    def analyze(symbol, rows, now):
        candles = pivot_candles(second=32, length=38)
        return RsiDivergenceDetail(symbol=symbol, candles=candles, signals=detect_divergences(symbol, candles))

    monkeypatch.setattr("app.services.rsi_divergence_service.analyze_klines", analyze)
    service = RsiDivergenceService()

    async def run():
        strict = await service.scan()
        strong = await service.scan(preset="strong")
        balanced = await service.get_detail("BTCUSDT", preset="balanced")
        assert strong.preset == "strong" and strong.min_rsi_change == 8
        assert balanced.preset == "balanced" and balanced.min_rsi_change == 3
        assert await service.scan() == strict
        assert strict.preset == "strict" and strict.min_rsi_change == 5

    asyncio.run(run())
    assert len([request for request in calls if request.url.path.endswith("klines")]) == 2
