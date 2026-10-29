"""扫描成交额达1亿USDT、4h/1h/15m收盘价同向位于布林带外的合约。"""
import asyncio
import logging
import math
import statistics
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.bollinger import BollingerBandSnapshot, BollingerRadarResponse, BollingerSignal

logger = logging.getLogger(__name__)
INTERVAL_MS = {"4h": 14_400_000, "1h": 3_600_000, "15m": 900_000}
MIN_QUOTE_VOLUME = 100_000_000
BOLL_PERIOD = 24
BOLL_MULTIPLIER = 2
BOLL_SCAN_INTERVAL_MS = 60_000


def calculate_bands(rows: List[List[Any]], interval: str, now_ms: int) -> BollingerBandSnapshot:
    """含被判断K线的24个收盘价，SMA ± 2倍总体标准差。"""
    duration = INTERVAL_MS[interval]
    if not isinstance(rows, list):
        raise ValueError("布林带K线格式错误")
    closed = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("布林带K线数据不完整")
        start, end = int(row[0]), int(row[6])
        if start % duration or end != start + duration - 1:
            raise ValueError("布林带K线周期不匹配")
        if end >= now_ms:
            continue
        value = float(row[4])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("布林带收盘价无效")
        closed[start] = value
    window = sorted(closed.items())[-BOLL_PERIOD:]
    if len(window) < BOLL_PERIOD:
        raise ValueError(f"不足{BOLL_PERIOD}根已收盘K线")
    if window[-1][0] + duration != now_ms // duration * duration:
        raise ValueError("布林带K线未更新")
    if any(b[0] - a[0] != duration for a, b in zip(window, window[1:])):
        raise ValueError("布林带K线存在缺口")
    prices = [value for _, value in window]
    middle = statistics.fmean(prices)
    deviation = statistics.pstdev(prices)
    return BollingerBandSnapshot(
        interval=interval, close=prices[-1], middle=middle,
        upper=middle + BOLL_MULTIPLIER * deviation,
        lower=middle - BOLL_MULTIPLIER * deviation,
        closed_at=window[-1][0] + duration,
    )


def build_signal(
    symbol: str, quote_volume: float, bands: List[BollingerBandSnapshot],
) -> Optional[BollingerSignal]:
    if not math.isfinite(quote_volume) or quote_volume < MIN_QUOTE_VOLUME:
        return None
    if len(bands) != 3 or {band.interval for band in bands} != set(INTERVAL_MS):
        return None
    if all(band.close > band.upper for band in bands):
        direction = "above_upper"
    elif all(band.close < band.lower for band in bands):
        direction = "below_lower"
    else:
        return None
    return BollingerSignal(symbol=symbol, direction=direction, quote_volume_24h=quote_volume, bands=bands)


class BollingerService:
    BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._scan_lock = asyncio.Lock()

    def _cached(self, key: str, now_ms: int):
        entry = self._cache.get(key)
        return entry[1] if entry and now_ms < entry[0] else None

    async def _fetch_band(self, client, semaphore, symbol, interval, now_ms):
        key = f"{symbol}:{interval}"
        cached = self._cached(key, now_ms)
        if cached is not None:
            return cached
        async with semaphore:
            response = await client.get(f"{self.BINANCE_FAPI}/klines", params={
                "symbol": symbol, "interval": interval, "limit": BOLL_PERIOD + 1, "endTime": now_ms,
            })
            response.raise_for_status()
        result = calculate_bands(response.json(), interval, now_ms)
        duration = INTERVAL_MS[interval]
        # 已收盘值只在该周期的下一根K线收盘后变化。
        self._cache[key] = ((now_ms // duration + 1) * duration, result)
        return result

    async def scan(self) -> BollingerRadarResponse:
        async with self._scan_lock:
            now_ms = int(time.time() * 1000)
            cached = self._cached("radar", now_ms)
            if cached is not None:
                return cached
            self._cache = {key: entry for key, entry in self._cache.items() if entry[0] > now_ms}
            async with httpx.AsyncClient(timeout=8.0) as client:
                exchange, tickers = await asyncio.gather(
                    client.get(f"{self.BINANCE_FAPI}/exchangeInfo"),
                    client.get(f"{self.BINANCE_FAPI}/ticker/24hr"),
                )
                exchange.raise_for_status()
                tickers.raise_for_status()
                active = {
                    item["symbol"] for item in exchange.json()["symbols"]
                    if item.get("status") == "TRADING" and item.get("quoteAsset") == "USDT"
                    and item.get("contractType") == "PERPETUAL"
                    and item.get("underlyingType", "COIN") == "COIN"
                }
                ticker_rows = tickers.json()
                if not isinstance(ticker_rows, list):
                    raise ValueError("24小时成交额数据格式错误")
                candidates = []
                for ticker in ticker_rows:
                    if ticker.get("symbol") not in active:
                        continue
                    volume = float(ticker.get("quoteVolume") or 0)
                    if math.isfinite(volume) and volume >= MIN_QUOTE_VOLUME:
                        candidates.append(ticker)
                # 不限Top N，覆盖全部达到1亿USDT门槛的合约。
                candidates.sort(key=lambda item: float(item["quoteVolume"]), reverse=True)
                semaphore = asyncio.Semaphore(6)

                async def inspect(ticker):
                    try:
                        close_time = int(ticker["closeTime"])
                        if not now_ms - 300_000 <= close_time <= now_ms + 60_000:
                            raise ValueError("24小时成交额数据已过期")
                        bands = await asyncio.gather(*(
                            self._fetch_band(client, semaphore, ticker["symbol"], interval, now_ms)
                            for interval in INTERVAL_MS
                        ), return_exceptions=True)
                        for band in bands:
                            if isinstance(band, Exception):
                                raise band
                        return True, build_signal(ticker["symbol"], float(ticker["quoteVolume"]), bands)
                    except Exception:
                        logger.exception("BOLL多周期扫描失败：%s", ticker["symbol"])
                        return False, None

                results = await asyncio.gather(*(inspect(ticker) for ticker in candidates))
            scanned_count = sum(success for success, _ in results)
            if candidates and scanned_count == 0:
                raise ValueError("全部合约的布林带行情均不可用")
            result = BollingerRadarResponse(
                signals=[signal for _, signal in results if signal is not None],
                scanned_count=scanned_count, failed_count=len(results) - scanned_count,
                period=BOLL_PERIOD, stddev_multiplier=BOLL_MULTIPLIER,
                timestamp=datetime.fromtimestamp(now_ms / 1000, timezone.utc),
            )
            if not result.failed_count:
                # 每分钟重新检查成交额和信号，已收盘轨道值按各自周期复用。
                expires = (now_ms // BOLL_SCAN_INTERVAL_MS + 1) * BOLL_SCAN_INTERVAL_MS
                self._cache["radar"] = (expires, result)
            return result


bollinger_service = BollingerService()
