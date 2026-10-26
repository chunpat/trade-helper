"""基于已收盘1小时K线的 RSI 常规顶/底背离扫描。"""
import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.rsi_divergence import (
    RsiCandle,
    RsiDivergenceDetail,
    RsiDivergencePoint,
    RsiDivergenceRadar,
    RsiDivergenceSignal,
)

logger = logging.getLogger(__name__)
HOUR_MS = 3_600_000


def calculate_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder RSI：首值用简单均值初始化，后续使用 RMA 平滑。"""
    if period < 1:
        raise ValueError("RSI周期必须为正数")
    values: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return values
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gain = sum(max(delta, 0) for delta in changes[:period]) / period
    loss = sum(max(-delta, 0) for delta in changes[:period]) / period
    for index in range(period, len(closes)):
        if index > period:
            delta = changes[index - 1]
            gain = (gain * (period - 1) + max(delta, 0)) / period
            loss = (loss * (period - 1) + max(-delta, 0)) / period
        # 无涨跌时保持中性；单向上涨/下跌分别为100/0。
        values[index] = 50.0 if gain == loss == 0 else (
            100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
        )
    return values


def detect_divergences(
    symbol: str,
    candles: List[RsiCandle],
    pivot_left: int = 5,
    pivot_right: int = 5,
    min_bars: int = 5,
    max_bars: int = 60,
) -> List[RsiDivergenceSignal]:
    """比较相邻同类 RSI 拐点及对应价格高/低点，不使用未确认拐点。"""
    if not candles:
        return []
    previous = {"bullish": None, "bearish": None}
    signals = []
    for index in range(pivot_left, len(candles) - pivot_right):
        candle = candles[index]
        window = candles[index - pivot_left:index + pivot_right + 1]
        if any(item.rsi is None for item in window):
            continue
        left = [item.rsi for item in window[:pivot_left]]
        right = [item.rsi for item in window[pivot_left + 1:]]
        # 相等平台仅取最右侧拐点，避免同一平台重复发信号。
        for direction, is_pivot in (
            ("bullish", all(candle.rsi <= value for value in left)
             and all(candle.rsi < value for value in right)),
            ("bearish", all(candle.rsi >= value for value in left)
             and all(candle.rsi > value for value in right)),
        ):
            if not is_pivot:
                continue
            prior_index = previous[direction]
            previous[direction] = index
            if prior_index is None or not min_bars <= index - prior_index <= max_bars:
                continue
            prior = candles[prior_index]
            bullish = direction == "bullish"
            prior_price = prior.low if bullish else prior.high
            price = candle.low if bullish else candle.high
            diverges = (price < prior_price and candle.rsi > prior.rsi) if bullish else (
                price > prior_price and candle.rsi < prior.rsi
            )
            if not diverges:
                continue
            signals.append(RsiDivergenceSignal(
                symbol=symbol,
                direction=direction,
                label="底背离" if bullish else "顶背离",
                previous=RsiDivergencePoint(time=prior.time, price=prior_price, rsi=prior.rsi),
                current=RsiDivergencePoint(time=candle.time, price=price, rsi=candle.rsi),
                confirmed_at=candles[index + pivot_right].time + HOUR_MS,
                bars_between=index - prior_index,
                last_close=candles[-1].close,
                last_rsi=candles[-1].rsi,
            ))
    return sorted(signals, key=lambda item: item.confirmed_at, reverse=True)


def analyze_klines(symbol: str, rows: List[List[Any]], now_ms: int) -> RsiDivergenceDetail:
    """剔除未收盘K线，校验连续小时数据，避免跨缺失K线计算。"""
    if not isinstance(rows, list):
        raise ValueError("K线数据格式错误")
    candles_by_time = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("K线数据不完整")
        start, end = int(row[0]), int(row[6])
        if start % HOUR_MS or end != start + HOUR_MS - 1:
            raise ValueError("K线周期不是1小时")
        if end >= now_ms:
            continue
        prices = [float(value) for value in row[1:5]]
        if not all(math.isfinite(value) and value > 0 for value in prices):
            raise ValueError("K线价格无效")
        opened, high, low, close = prices
        if low > min(opened, close) or high < max(opened, close) or low > high:
            raise ValueError("K线高低价无效")
        candles_by_time[start] = RsiCandle(time=start, open=opened, high=high, low=low, close=close)
    candles = sorted(candles_by_time.values(), key=lambda item: item.time)
    if any(b.time - a.time != HOUR_MS for a, b in zip(candles, candles[1:])):
        raise ValueError("小时K线存在缺口")
    if not candles or candles[-1].time + HOUR_MS != now_ms // HOUR_MS * HOUR_MS:
        raise ValueError("小时K线数据未更新")
    for candle, value in zip(candles, calculate_rsi([item.close for item in candles])):
        candle.rsi = value
    return RsiDivergenceDetail(symbol=symbol, candles=candles, signals=detect_divergences(symbol, candles))


class RsiDivergenceService:
    BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
    SCAN_LIMIT = 30
    HISTORY_LIMIT = 499

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._scan_lock = asyncio.Lock()

    def _cached(self, key: str, now_ms: int):
        entry = self._cache.get(key)
        if entry and now_ms < entry[0]:
            return entry[1]
        return None

    def _save(self, key: str, value: Any, now_ms: int):
        # 最长缓存5分钟，整点立即失效，确保新确认信号及时展示。
        expires = min(now_ms + 300_000, (now_ms // HOUR_MS + 1) * HOUR_MS)
        self._cache = {key: entry for key, entry in self._cache.items() if entry[0] > now_ms}
        self._cache[key] = (expires, value)

    async def _fetch_detail(self, client: httpx.AsyncClient, symbol: str, now_ms: int):
        cached = self._cached(symbol, now_ms)
        if cached is not None:
            return cached
        response = await client.get(f"{self.BINANCE_FAPI}/klines", params={
            "symbol": symbol, "interval": "1h", "limit": self.HISTORY_LIMIT,
            "endTime": now_ms,
        })
        response.raise_for_status()
        result = analyze_klines(symbol, response.json(), now_ms)
        self._save(symbol, result, now_ms)
        return result

    async def get_detail(self, symbol: str) -> RsiDivergenceDetail:
        async with httpx.AsyncClient(timeout=8.0) as client:
            return await self._fetch_detail(client, symbol, int(time.time() * 1000))

    async def scan(self) -> RsiDivergenceRadar:
        async with self._scan_lock:
            now_ms = int(time.time() * 1000)
            cached = self._cached("radar", now_ms)
            if cached is not None:
                return cached
            async with httpx.AsyncClient(timeout=8.0) as client:
                exchange_response, ticker_response = await asyncio.gather(
                    client.get(f"{self.BINANCE_FAPI}/exchangeInfo"),
                    client.get(f"{self.BINANCE_FAPI}/ticker/24hr"),
                )
                exchange_response.raise_for_status()
                ticker_response.raise_for_status()
                active = {
                    item["symbol"] for item in exchange_response.json()["symbols"]
                    if item.get("status") == "TRADING" and item.get("quoteAsset") == "USDT"
                    and item.get("contractType") == "PERPETUAL"
                    and item.get("baseAsset") not in {"USDC", "USDE", "FDUSD", "TUSD", "BUSD"}
                    and item.get("underlyingType", "COIN") == "COIN"
                }
                tickers = ticker_response.json()
                if not isinstance(tickers, list):
                    raise ValueError("合约行情数据格式错误")
                candidates = sorted(
                    (item for item in tickers if item.get("symbol") in active
                     and float(item.get("quoteVolume") or 0) >= 5_000_000),
                    key=lambda item: float(item["quoteVolume"]), reverse=True,
                )[:self.SCAN_LIMIT]
                semaphore = asyncio.Semaphore(6)

                async def inspect(ticker):
                    async with semaphore:
                        try:
                            return await self._fetch_detail(client, ticker["symbol"], now_ms)
                        except Exception:
                            logger.exception("RSI背离扫描失败：%s", ticker["symbol"])
                            return None

                results = await asyncio.gather(*(inspect(item) for item in candidates))
            successful = [item for item in results if item is not None]
            if candidates and not successful:
                raise ValueError("所有合约的小时K线均不可用")
            signals = [signal for item in successful for signal in item.signals
                       if now_ms - 24 * HOUR_MS < signal.confirmed_at <= now_ms]
            result = RsiDivergenceRadar(
                signals=sorted(signals, key=lambda item: item.confirmed_at, reverse=True),
                scanned_count=len(successful), failed_count=len(results) - len(successful),
                timestamp=datetime.fromtimestamp(now_ms / 1000, timezone.utc),
            )
            # 部分失败时保留成功币种缓存，下次刷新重试失败币种。
            if result.failed_count == 0:
                self._save("radar", result, now_ms)
            return result


rsi_divergence_service = RsiDivergenceService()
