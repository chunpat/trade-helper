"""市场洞察数据聚合服务"""
import asyncio
import logging
import os
import math
import statistics
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import httpx

from app.schemas.market_insight import (
    AnomalyEventSummary,
    BinanceEquityVolatility,
    MarketCapVolatility,
    MarketCapVolatilityResponse,
    MarketInsightDashboard,
    MarketMetrics,
    MomentumRadarResponse,
    MomentumSignal,
    TokenizedRwaVolatility,
    MarketSentiment,
    MarketNews,
    TradingSignal,
    MarketOverview,
    FearGreedIndex,
    RainbowBand,
    FundingRateRanking
)
from app.services.anomaly_monitor_service import anomaly_monitor_service
from app.services.news_archive_service import news_archive_service
from app.services.pattern_recognition import pattern_recognizer

logger = logging.getLogger(__name__)


class MarketInsightService:
    """市场洞察数据聚合服务
    
    整合多个数据源提供：
    - 市场情绪指标（恐惧贪婪指数、资金费率、多空比）
    - 价格涨跌幅排行（Binance合约）
    - 成交量数据
    - 市场新闻消息
    - 交易信号生成
    """
    
    BINANCE_API = "https://api.binance.com/api/v3"
    BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
    BINANCE_FUTURES_DATA = "https://fapi.binance.com/futures/data"
    MAX_KLINES_LIMIT = 1500
    COINGECKO_API = "https://api.coingecko.com/api/v3"
    ALTERNATIVE_ME_API = "https://api.alternative.me/fng/"
    
    # 默认关注的交易对
    DEFAULT_WATCHLIST = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "MATICUSDT", "DOTUSDT", "AVAXUSDT"
    ]

    STABLECOIN_SYMBOLS = {
        "BUSD", "CRVUSD", "DAI", "EURC", "EURS", "EURT", "FDUSD", "FRAX",
        "GHO", "LUSD", "PYUSD", "RLUSD", "SUSD", "TUSD", "USD1", "USDC",
        "USDD", "USDE", "USDG", "USDP", "USDS", "USDT", "USDTB", "USDX",
    }
    STABLECOIN_IDS = {
        "binance-usd", "crvusd", "dai", "ethena-usde", "first-digital-usd",
        "frax", "gho", "global-dollar", "liquity-usd", "paypal-usd",
        "ripple-usd", "true-usd", "usd1", "usdd", "usds", "usdtb",
        "usd-coin", "usdx-money-usdx",
    }
    TOKENIZED_RWA_ASSETS = {
        "FIGRHELOC": (
            "tokenized_credit",
            "代币化私人信贷",
            "报告规模按链上 HELOC 未偿本金余额统计，不等同于可流通加密币市值",
        ),
        "USYC": (
            "tokenized_fund",
            "代币化货币市场基金",
            "报告规模代表基金份额价值，不等同于原生加密币流通市值",
        ),
        "BUIDL": (
            "tokenized_fund",
            "代币化国债基金",
            "报告规模代表基金资产管理规模，不等同于原生加密币流通市值",
        ),
        "XAUT": (
            "tokenized_commodity",
            "代币化黄金",
            "每枚代币对应一金衡盎司实物黄金，规模随黄金价格与发行量变化",
        ),
        "PAXG": (
            "tokenized_commodity",
            "代币化黄金",
            "每枚代币对应一金衡盎司实物黄金，规模随黄金价格与发行量变化",
        ),
    }
    TOKENIZED_RWA_IDS = {
        "figure-heloc": "FIGRHELOC",
        "hashnote-usyc": "USYC",
        "blackrock-usd-institutional-digital-liquidity-fund": "BUIDL",
        "tether-gold": "XAUT",
        "pax-gold": "PAXG",
    }
    BINANCE_EQUITY_NAMES = {
        "AAPL": "Apple",
        "AMZN": "Amazon",
        "AVGO": "Broadcom",
        "BABA": "Alibaba",
        "COIN": "Coinbase",
        "CRCL": "Circle",
        "GOOGL": "Alphabet",
        "HOOD": "Robinhood",
        "INTC": "Intel",
        "META": "Meta Platforms",
        "MSFT": "Microsoft",
        "MSTR": "Strategy",
        "MU": "Micron Technology",
        "NVDA": "NVIDIA",
        "PAYP": "PayPay",
        "PLTR": "Palantir",
        "SPCX": "SpaceX",
        "SNDK": "SanDisk",
        "TSLA": "Tesla",
        "TSM": "TSMC",
    }
    BINANCE_EQUITY_ETFS = {
        "EWJ": "iShares MSCI Japan ETF",
        "EWY": "iShares MSCI South Korea ETF",
        "QQQ": "Invesco QQQ Trust",
        "SPY": "SPDR S&P 500 ETF",
    }
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 60  # 缓存60秒
        
    async def get_market_overview(self) -> MarketOverview:
        """获取市场总览数据"""
        cache_key = "market_overview"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 获取币安合约24小时ticker统计 (用户要求看合约)
                response = await client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
                tickers = response.json()
                
                # 计算总成交量
                total_volume = sum(float(t.get("quoteVolume", 0)) for t in tickers if "USDT" in t.get("symbol", ""))
                
                overview = MarketOverview(
                    total_volume_24h=total_volume,
                    active_cryptocurrencies=len(tickers),
                    timestamp=datetime.now()
                )
                
                # 尝试从CoinGecko获取更多数据
                try:
                    cg_response = await client.get(
                        f"{self.COINGECKO_API}/global",
                        timeout=5.0
                    )
                    if cg_response.status_code == 200:
                        global_data = cg_response.json().get("data", {})
                        overview.total_market_cap = global_data.get("total_market_cap", {}).get("usd")
                        overview.btc_dominance = global_data.get("market_cap_percentage", {}).get("btc")
                except Exception as e:
                    logger.warning(f"Failed to fetch CoinGecko data: {e}")
                
                self._update_cache(cache_key, overview)
                return overview
                
        except Exception as e:
            logger.error(f"Error fetching market overview: {e}")
            return MarketOverview(timestamp=datetime.now())
    
    async def get_top_gainers(self, limit: int = 10) -> List[MarketMetrics]:
        """获取合约涨幅榜"""
        return await self._get_top_movers(limit, ascending=False)
    
    async def get_top_losers(self, limit: int = 10) -> List[MarketMetrics]:
        """获取合约跌幅榜"""
        return await self._get_top_movers(limit, ascending=True)

    async def get_altcoin_starters(self, limit: int = 10) -> List[MarketMetrics]:
        """筛选刚开始放量、但24H涨幅尚未透支的山寨币合约。"""
        cache_key = f"altcoin_starters_{limit}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]

        excluded_bases = {"BTC", "ETH", *self.STABLECOIN_SYMBOLS}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
                tickers = response.json()
                candidates = []
                for ticker in tickers:
                    symbol = ticker.get("symbol", "")
                    change_24h = float(ticker.get("priceChangePercent", 0) or 0)
                    quote_volume = float(ticker.get("quoteVolume", 0) or 0)
                    base = symbol[:-4] if symbol.endswith("USDT") else ""
                    # 只看有基本流动性的山寨，且拒绝已经大幅拉升的24H榜首型标的。
                    if (
                        symbol.endswith("USDT")
                        and base not in excluded_bases
                        and 0 < change_24h <= 15
                        and quote_volume >= 5_000_000
                    ):
                        candidates.append(ticker)

                # 先按流动性和温和涨幅预筛，避免对全部合约逐一请求K线。
                candidates.sort(
                    key=lambda item: float(item.get("quoteVolume", 0) or 0)
                    * (1 + min(float(item.get("priceChangePercent", 0) or 0), 8) / 8),
                    reverse=True,
                )

                async def inspect(ticker: dict) -> Optional[MarketMetrics]:
                    symbol = ticker["symbol"]
                    kline_response = await client.get(
                        f"{self.BINANCE_FAPI}/klines",
                        params={"symbol": symbol, "interval": "15m", "limit": 13},
                    )
                    klines = kline_response.json()
                    if not isinstance(klines, list) or len(klines) < 10:
                        return None

                    # 最后一根可能尚未收盘，使用倒数第二根完整K线判断真实放量。
                    closed = klines[:-1]
                    latest = closed[-1]
                    previous = closed[-9:-1]
                    previous_avg_volume = sum(float(k[5]) for k in previous) / len(previous)
                    volume_ratio = float(latest[5]) / previous_avg_volume if previous_avg_volume else 0
                    hour_open = float(closed[-4][1])
                    latest_close = float(latest[4])
                    momentum_1h = ((latest_close / hour_open) - 1) * 100 if hour_open else 0
                    candle_change = ((latest_close / float(latest[1])) - 1) * 100 if float(latest[1]) else 0

                    if volume_ratio < 1.5 or not (0.2 <= momentum_1h <= 6) or candle_change <= 0:
                        return None

                    change_24h = float(ticker.get("priceChangePercent", 0) or 0)
                    # 放量和短时转强权重最高；24H涨幅越大，追高惩罚越重。
                    score = min(volume_ratio, 5) * 14 + min(momentum_1h, 4) * 8 + max(0, 24 - change_24h * 1.6)
                    metric = self._ticker_to_metrics(ticker)
                    metric.startup_score = round(min(score, 100), 1)
                    metric.volume_ratio = round(volume_ratio, 2)
                    metric.momentum_1h = round(momentum_1h, 2)
                    metric.startup_reason = f"15分钟量比 {volume_ratio:.1f}x，近1小时 +{momentum_1h:.2f}%"
                    return metric

                inspected = await asyncio.gather(
                    *(inspect(ticker) for ticker in candidates[:30]),
                    return_exceptions=True,
                )
                metrics = [item for item in inspected if isinstance(item, MarketMetrics)]
                metrics.sort(key=lambda item: item.startup_score or 0, reverse=True)
                result = metrics[:limit]
                self._update_cache(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Error fetching altcoin starters: {e}")
            return []

    async def get_momentum_radar(
        self,
        limit: int = 15,
        volume_ratio_min: float = 1.3,
        resistance_hours: int = 48,
        exclude_recent_hours: int = 3,
        volatility_days: int = 7,
        noise_multiplier: float = 0.35,
        min_breakout_percent: float = 0.08,
        max_24h_change: float = 15,
    ) -> MomentumRadarResponse:
        """一次请求返回5分钟和15分钟的山寨币放量启动信号。"""
        cache_key = (
            f"momentum_radar_{limit}_{volume_ratio_min}_{resistance_hours}_"
            f"{exclude_recent_hours}_{volatility_days}_{noise_multiplier}_"
            f"{min_breakout_percent}_{max_24h_change}"
        )
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]

        excluded_bases = {"BTC", "ETH", *self.STABLECOIN_SYMBOLS}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
                tickers = response.json()
                candidates = []
                for ticker in tickers if isinstance(tickers, list) else []:
                    symbol = ticker.get("symbol", "")
                    base = symbol[:-4] if symbol.endswith("USDT") else ""
                    change_24h = float(ticker.get("priceChangePercent", 0) or 0)
                    quote_volume = float(ticker.get("quoteVolume", 0) or 0)
                    if (
                        symbol.endswith("USDT")
                        and base not in excluded_bases
                        and -5 <= change_24h <= max_24h_change
                        and quote_volume >= 5_000_000
                    ):
                        candidates.append(ticker)

                candidates.sort(
                    key=lambda item: float(item.get("quoteVolume", 0) or 0),
                    reverse=True,
                )

                async def inspect(ticker: dict) -> Optional[MomentumSignal]:
                    kline_response = await client.get(
                        f"{self.BINANCE_FAPI}/klines",
                        params={"symbol": ticker["symbol"], "interval": "5m", "limit": 17},
                    )
                    klines = kline_response.json()
                    if not isinstance(klines, list) or len(klines) < 17:
                        return None

                    closed = klines[:-1]
                    latest = closed[-1]
                    previous_12 = closed[-13:-1]
                    previous_avg_5m = sum(float(item[5]) for item in previous_12) / 12
                    volume_ratio_5m = float(latest[5]) / previous_avg_5m if previous_avg_5m else 0

                    latest_15m = closed[-3:]
                    previous_15m_blocks = [closed[index:index + 3] for index in range(len(closed) - 15, len(closed) - 3, 3)]
                    latest_15m_volume = sum(float(item[5]) for item in latest_15m)
                    previous_avg_15m = (
                        sum(sum(float(item[5]) for item in block) for block in previous_15m_blocks)
                        / len(previous_15m_blocks)
                        if previous_15m_blocks else 0
                    )
                    volume_ratio_15m = latest_15m_volume / previous_avg_15m if previous_avg_15m else 0

                    close_price = float(latest[4])
                    open_5m = float(latest[1])
                    open_15m = float(latest_15m[0][1])
                    change_5m = ((close_price / open_5m) - 1) * 100 if open_5m else 0
                    change_15m = ((close_price / open_15m) - 1) * 100 if open_15m else 0
                    change_24h = float(ticker.get("priceChangePercent", 0) or 0)

                    score = (
                        min(max(volume_ratio_5m - 1, 0), 4) * 12
                        + min(max(volume_ratio_15m - 1, 0), 4) * 10
                        + min(max(change_5m, 0), 3) * 8
                        + min(max(change_15m, 0), 6) * 5
                        + max(0, 18 - max(change_24h, 0) * 1.2)
                    )
                    return MomentumSignal(
                        symbol=ticker["symbol"],
                        last_price=close_price,
                        change_5m=round(change_5m, 2),
                        change_15m=round(change_15m, 2),
                        volume_ratio_5m=round(volume_ratio_5m, 2),
                        volume_ratio_15m=round(volume_ratio_15m, 2),
                        quote_volume_24h=float(ticker.get("quoteVolume", 0) or 0),
                        price_change_percent_24h=round(change_24h, 2),
                        score=round(min(score, 100), 1),
                        reason=f"5m量比 {volume_ratio_5m:.1f}x / 15m量比 {volume_ratio_15m:.1f}x",
                    )

                inspected = await asyncio.gather(
                    *(inspect(ticker) for ticker in candidates[:20]),
                    return_exceptions=True,
                )
                signals = [item for item in inspected if isinstance(item, MomentumSignal)]

                preliminary = [
                    item for item in signals
                    if (
                        (0.15 <= item.change_5m <= 3 and item.volume_ratio_5m >= volume_ratio_min)
                        or (0.3 <= item.change_15m <= 6 and item.volume_ratio_15m >= volume_ratio_min)
                    )
                ]

                async def enrich_breakout(signal: MomentumSignal) -> MomentumSignal:
                    history_limit = max(
                        volatility_days * 24,
                        resistance_hours + exclude_recent_hours,
                    ) + 1
                    history_response = await client.get(
                        f"{self.BINANCE_FAPI}/klines",
                        params={"symbol": signal.symbol, "interval": "1h", "limit": history_limit},
                    )
                    history = history_response.json()
                    minimum_history = resistance_hours + exclude_recent_hours + 1
                    if not isinstance(history, list) or len(history) < minimum_history:
                        return signal

                    closed_hours = history[:-1]
                    volatility_hours = closed_hours[-(volatility_days * 24):]
                    closes = [float(item[4]) for item in volatility_hours if float(item[4]) > 0]
                    hourly_returns = [
                        math.log(closes[index] / closes[index - 1])
                        for index in range(1, len(closes))
                        if closes[index - 1] > 0
                    ]
                    volatility_7d = (
                        statistics.pstdev(hourly_returns) * math.sqrt(volatility_days * 24) * 100
                        if len(hourly_returns) >= 2 else 0
                    )

                    # 排除最近若干小时，避免把正在发生的突破本身算进压力位。
                    level_end = -exclude_recent_hours if exclude_recent_hours else None
                    level_start = -(resistance_hours + exclude_recent_hours)
                    level_window = closed_hours[level_start:level_end]
                    resistance = max(float(item[2]) for item in level_window)
                    support = min(float(item[3]) for item in level_window)
                    breakout_percent = (
                        ((signal.last_price / resistance) - 1) * 100 if resistance > 0 else 0
                    )

                    # 将7日实现波动率折算成5分钟噪声，波动越大的币要求突破越深。
                    expected_5m_move = (
                        volatility_7d / math.sqrt(volatility_days * 24 * 12)
                        if volatility_7d else 0
                    )
                    breakout_threshold = max(min_breakout_percent, expected_5m_move * noise_multiplier)
                    relevant_volume_ratio = max(signal.volume_ratio_5m, signal.volume_ratio_15m)
                    signal.volatility_7d = round(volatility_7d, 2)
                    signal.resistance = resistance
                    signal.support = support
                    signal.breakout_percent = round(breakout_percent, 2)
                    signal.breakout_threshold = round(breakout_threshold, 2)
                    signal.breakout_confirmed = (
                        breakout_percent >= breakout_threshold
                        and relevant_volume_ratio >= volume_ratio_min
                    )
                    if signal.breakout_confirmed:
                        signal.score = round(min(signal.score + min(breakout_percent, 3) * 10, 100), 1)
                        signal.reason = (
                            f"放量突破48H压力位 {breakout_percent:.2f}%，"
                            f"7日波动率 {volatility_7d:.1f}%"
                        )
                    return signal

                enriched = await asyncio.gather(
                    *(enrich_breakout(signal) for signal in preliminary),
                    return_exceptions=True,
                )
                confirmed = [
                    item for item in enriched
                    if isinstance(item, MomentumSignal) and item.breakout_confirmed
                ]
                five_minute = sorted(
                    [item for item in confirmed if 0.15 <= item.change_5m <= 3 and item.volume_ratio_5m >= volume_ratio_min],
                    key=lambda item: item.score,
                    reverse=True,
                )[:limit]
                fifteen_minute = sorted(
                    [item for item in confirmed if 0.3 <= item.change_15m <= 6 and item.volume_ratio_15m >= volume_ratio_min],
                    key=lambda item: item.score,
                    reverse=True,
                )[:limit]
                result = MomentumRadarResponse(
                    five_minute=five_minute,
                    fifteen_minute=fifteen_minute,
                    scanned_count=len(signals),
                    timestamp=datetime.now(),
                )
                self._update_cache(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Error fetching momentum radar: {e}")
            return MomentumRadarResponse(timestamp=datetime.now())

    async def get_market_cap_volatility(self, limit: int = 30) -> MarketCapVolatilityResponse:
        """获取原生加密资产、链上 RWA 与币安股票类产品的7日实现波动率。"""
        normalized_limit = 20 if limit <= 20 else 30
        cache_key = f"market_cap_volatility_{normalized_limit}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                crypto_response, binance_equities = await asyncio.gather(
                    client.get(
                        f"{self.COINGECKO_API}/coins/markets",
                        params={
                            "vs_currency": "usd",
                            "order": "market_cap_desc",
                            "per_page": min(normalized_limit + 25, 100),
                            "page": 1,
                            "sparkline": "true",
                            "price_change_percentage": "24h",
                        },
                    ),
                    self._fetch_binance_equity_volatility(client),
                )
                rows = crypto_response.json()
                market_rows = rows if isinstance(rows, list) else []
                items = []
                crypto_rows = [
                    row for row in market_rows
                    if not self._is_stablecoin_market_row(row)
                    and self._classify_tokenized_rwa_market_row(row) is None
                ][:normalized_limit]
                for display_rank, row in enumerate(crypto_rows, start=1):
                    prices = [
                        float(value) for value in (row.get("sparkline_in_7d") or {}).get("price", [])
                        if value is not None and float(value) > 0
                    ]
                    items.append(MarketCapVolatility(
                        rank=display_rank,
                        symbol=str(row.get("symbol") or "").upper(),
                        name=str(row.get("name") or ""),
                        last_price=float(row.get("current_price") or 0),
                        market_cap=float(row.get("market_cap") or 0),
                        price_change_percent_24h=round(float(row.get("price_change_percentage_24h") or 0), 2),
                        volatility_7d=self._calculate_realized_volatility(prices),
                    ))

                rwa_items = []
                rwa_rows = [
                    row for row in market_rows
                    if self._classify_tokenized_rwa_market_row(row) is not None
                ]
                for display_rank, row in enumerate(rwa_rows, start=1):
                    classification = self._classify_tokenized_rwa_market_row(row)
                    if classification is None:
                        continue
                    asset_type, asset_type_label, market_size_note = classification
                    prices = [
                        float(value) for value in (row.get("sparkline_in_7d") or {}).get("price", [])
                        if value is not None and float(value) > 0
                    ]
                    rwa_items.append(TokenizedRwaVolatility(
                        rank=display_rank,
                        symbol=str(row.get("symbol") or "").upper(),
                        name=str(row.get("name") or ""),
                        last_price=float(row.get("current_price") or 0),
                        market_cap=float(row.get("market_cap") or 0),
                        price_change_percent_24h=round(float(row.get("price_change_percentage_24h") or 0), 2),
                        volatility_7d=self._calculate_realized_volatility(prices),
                        asset_type=asset_type,
                        asset_type_label=asset_type_label,
                        market_size_note=market_size_note,
                    ))

                result = MarketCapVolatilityResponse(
                    items=items,
                    rwa_items=rwa_items,
                    binance_equities=binance_equities,
                    timestamp=datetime.now(),
                )
                self._cache[cache_key] = {
                    "data": result,
                    "timestamp": datetime.now(),
                    "ttl": 300,
                }
                return result
        except Exception as e:
            logger.error(f"Error fetching market cap volatility: {e}")
            return MarketCapVolatilityResponse(timestamp=datetime.now())

    @classmethod
    def _is_stablecoin_market_row(cls, row: Dict[str, Any]) -> bool:
        symbol = cls._normalize_market_symbol(row.get("symbol"))
        coin_id = str(row.get("id") or "").lower()
        name = str(row.get("name") or "").lower()
        return (
            symbol in cls.STABLECOIN_SYMBOLS
            or coin_id in cls.STABLECOIN_IDS
            or "stablecoin" in name
        )

    @staticmethod
    def _normalize_market_symbol(value: Any) -> str:
        return "".join(character for character in str(value or "").upper() if character.isalnum())

    @classmethod
    def _classify_tokenized_rwa_market_row(
        cls,
        row: Dict[str, Any],
    ) -> Optional[tuple[str, str, str]]:
        symbol = cls._normalize_market_symbol(row.get("symbol"))
        coin_id = str(row.get("id") or "").lower()
        asset_key = cls.TOKENIZED_RWA_IDS.get(coin_id, symbol)
        return cls.TOKENIZED_RWA_ASSETS.get(asset_key)

    @staticmethod
    def _calculate_realized_volatility(prices: List[float]) -> float:
        returns = [
            math.log(prices[index] / prices[index - 1])
            for index in range(1, len(prices))
            if prices[index - 1] > 0 and prices[index] > 0
        ]
        volatility = (
            statistics.pstdev(returns) * math.sqrt(len(returns)) * 100
            if len(returns) >= 2 else 0
        )
        return round(volatility, 2)

    @classmethod
    def _classify_binance_equity_contract(
        cls,
        contract: Dict[str, Any],
    ) -> Optional[str]:
        base_asset = str(contract.get("baseAsset") or "").upper()
        raw_subtypes = contract.get("underlyingSubType") or []
        subtypes = [raw_subtypes] if isinstance(raw_subtypes, str) else raw_subtypes
        classification = " ".join(
            [
                str(contract.get("underlyingType") or ""),
                *[str(value) for value in subtypes],
            ]
        ).upper()
        if base_asset in cls.BINANCE_EQUITY_ETFS or "ETF" in classification:
            return "etf_perpetual"
        if (
            base_asset in cls.BINANCE_EQUITY_NAMES
            or "STOCK" in classification
            or "EQUITY" in classification
        ):
            return "stock_perpetual"
        return None

    async def _fetch_binance_equity_volatility(
        self,
        client: httpx.AsyncClient,
    ) -> List[BinanceEquityVolatility]:
        try:
            futures_exchange_task = client.get(f"{self.BINANCE_FAPI}/exchangeInfo")
            futures_ticker_task = client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
            spot_exchange_task = client.get(f"{self.BINANCE_API}/exchangeInfo")
            futures_exchange_response, futures_ticker_response, spot_exchange_response = (
                await asyncio.gather(
                    futures_exchange_task,
                    futures_ticker_task,
                    spot_exchange_task,
                )
            )
            futures_exchange = futures_exchange_response.json()
            futures_tickers = futures_ticker_response.json()
            spot_exchange = spot_exchange_response.json()

            ticker_map = {
                str(item.get("symbol") or ""): item
                for item in (futures_tickers if isinstance(futures_tickers, list) else [])
            }
            futures_products = []
            supported_stock_symbols = set(self.BINANCE_EQUITY_NAMES)
            supported_stock_symbols.update(self.BINANCE_EQUITY_ETFS)
            for contract in futures_exchange.get("symbols", []) if isinstance(futures_exchange, dict) else []:
                product_type = self._classify_binance_equity_contract(contract)
                base_asset = str(contract.get("baseAsset") or "").upper()
                if product_type and base_asset:
                    # 币安 bStock 现货没有独立的资产类型字段，因此使用同一底层
                    # 在合约 exchangeInfo 中的 EQUITY / ETF 元数据动态确认，避免新品
                    # 依赖静态白名单。静态名单仅用于接口暂时缺少对应合约时兜底。
                    supported_stock_symbols.add(base_asset)
                if (
                    product_type
                    and contract.get("status") == "TRADING"
                    and contract.get("contractType") == "PERPETUAL"
                    and contract.get("quoteAsset") == "USDT"
                ):
                    futures_products.append(
                        {
                            "symbol": contract.get("symbol"),
                            "underlying_symbol": contract.get("baseAsset"),
                            "product_type": product_type,
                            "ticker": ticker_map.get(contract.get("symbol"), {}),
                            "market": "futures",
                        }
                    )

            quote_priority = {"USDT": 0, "USDC": 1, "FDUSD": 2, "USD1": 3}
            spot_by_underlying: Dict[str, Dict[str, Any]] = {}
            for market in spot_exchange.get("symbols", []) if isinstance(spot_exchange, dict) else []:
                base_asset = str(market.get("baseAsset") or "").upper()
                quote_asset = str(market.get("quoteAsset") or "").upper()
                if (
                    market.get("status") != "TRADING"
                    or not base_asset.endswith("B")
                    or quote_asset not in quote_priority
                ):
                    continue
                underlying_symbol = base_asset[:-1]
                if underlying_symbol not in supported_stock_symbols:
                    continue
                existing = spot_by_underlying.get(underlying_symbol)
                if (
                    existing is None
                    or quote_priority[quote_asset] < quote_priority[existing["quote_asset"]]
                ):
                    spot_by_underlying[underlying_symbol] = {
                        "symbol": market.get("symbol"),
                        "underlying_symbol": underlying_symbol,
                        "product_type": "tokenized_stock",
                        "market": "spot",
                        "quote_asset": quote_asset,
                    }

            products = futures_products + list(spot_by_underlying.values())

            async def inspect(product: Dict[str, Any]) -> Optional[BinanceEquityVolatility]:
                symbol = str(product.get("symbol") or "")
                if not symbol:
                    return None
                api_base = self.BINANCE_FAPI if product["market"] == "futures" else self.BINANCE_API
                kline_task = client.get(
                    f"{api_base}/klines",
                    params={"symbol": symbol, "interval": "1h", "limit": 169},
                )
                ticker = product.get("ticker") or {}
                if product["market"] == "spot":
                    ticker_response, kline_response = await asyncio.gather(
                        client.get(
                            f"{self.BINANCE_API}/ticker/24hr",
                            params={"symbol": symbol},
                        ),
                        kline_task,
                    )
                    ticker = ticker_response.json()
                else:
                    kline_response = await kline_task
                klines = kline_response.json()
                prices = [
                    float(row[4])
                    for row in (klines if isinstance(klines, list) else [])
                    if isinstance(row, list) and len(row) > 4 and float(row[4]) > 0
                ]
                underlying = str(product["underlying_symbol"])
                product_type = str(product["product_type"])
                names = {**self.BINANCE_EQUITY_NAMES, **self.BINANCE_EQUITY_ETFS}
                labels = {
                    "stock_perpetual": "股票永续",
                    "etf_perpetual": "ETF 永续",
                    "tokenized_stock": "bStock 股票代币",
                }
                return BinanceEquityVolatility(
                    symbol=symbol,
                    underlying_symbol=underlying,
                    name=names.get(underlying, underlying),
                    product_type=product_type,
                    product_type_label=labels[product_type],
                    last_price=float(ticker.get("lastPrice") or 0),
                    price_change_percent_24h=round(
                        float(ticker.get("priceChangePercent") or 0),
                        2,
                    ),
                    quote_volume_24h=float(ticker.get("quoteVolume") or 0),
                    volatility_7d=self._calculate_realized_volatility(prices),
                )

            inspected = await asyncio.gather(
                *(inspect(product) for product in products),
                return_exceptions=True,
            )
            items = [
                item for item in inspected
                if isinstance(item, BinanceEquityVolatility)
            ]
            return sorted(
                items,
                key=lambda item: (
                    item.product_type == "tokenized_stock",
                    item.quote_volume_24h,
                ),
                reverse=True,
            )
        except Exception as exc:
            logger.warning("market-insight: failed to fetch Binance equities: %s", exc)
            return []
    
    async def get_top_volume(self, limit: int = 10) -> List[MarketMetrics]:
        """获取合约成交量排行"""
        cache_key = f"top_volume_{limit}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
                tickers = response.json()
                
                # 过滤USDT交易对并按成交量排序
                usdt_pairs = [t for t in tickers if t.get("symbol", "").endswith("USDT")]
                sorted_pairs = sorted(
                    usdt_pairs,
                    key=lambda x: float(x.get("quoteVolume", 0)),
                    reverse=True
                )[:limit]
                
                metrics = [self._ticker_to_metrics(t) for t in sorted_pairs]
                self._update_cache(cache_key, metrics)
                return metrics
                
        except Exception as e:
            logger.error(f"Error fetching top volume: {e}")
            return []
    
    async def get_watchlist_metrics(self, symbols: Optional[List[str]] = None) -> List[MarketMetrics]:
        """获取自选币种数据（优先从合约获取）"""
        if not symbols:
            symbols = self.DEFAULT_WATCHLIST
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
                tickers = response.json()
                
                # 筛选自选币种
                symbol_set = set(symbols)
                filtered = [t for t in tickers if t.get("symbol") in symbol_set]
                
                return [self._ticker_to_metrics(t) for t in filtered]
                
        except Exception as e:
            logger.error(f"Error fetching watchlist metrics: {e}")
            return []
    
    async def get_fear_greed_data(self, limit: int = 30) -> Dict[str, Any]:
        """从 alternative.me 获取恐惧贪婪指数数据"""
        cache_key = f"fear_greed_{limit}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.ALTERNATIVE_ME_API}", params={"limit": limit})
                data = response.json()
                
                history = []
                for item in data.get("data", []):
                    history.append(FearGreedIndex(
                        value=int(item["value"]),
                        value_classification=item["value_classification"],
                        timestamp=datetime.fromtimestamp(int(item["timestamp"])).strftime('%Y-%m-%d')
                    ))
                
                result = {
                    "current": history[0] if history else None,
                    "history": history
                }
                self._update_cache(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Error fetching fear grease index: {e}")
            return {"current": None, "history": []}
            
    async def get_rainbow_bands(self) -> List[RainbowBand]:
        """计算 BTC 彩虹图带价格区间"""
        # Use a log-power approximation for BTC fair value and derive rainbow
        # bands around it. The previous coefficients produced near-zero prices,
        # which broke the frontend reference line and always pushed BTC into the
        # highest band.
        genesis_date = datetime(2009, 1, 3)
        today = datetime.now()
        days = (today - genesis_date).days
        
        if days <= 0: return []
        
        bands_config = [
            {"name": "极度泡沫", "color": "#FF0000", "offset": 0.42},
            {"name": "卖出！", "color": "#FF4500", "offset": 0.30},
            {"name": "郁金香泡沫？", "color": "#FFA500", "offset": 0.18},
            {"name": "由于FOMO增加", "color": "#FFD700", "offset": 0.08},
            {"name": "持有", "color": "#00C853", "offset": 0.00},
            {"name": "仍处于廉价", "color": "#20B2AA", "offset": -0.10},
            {"name": "积累", "color": "#4682B4", "offset": -0.20},
            {"name": "买入！", "color": "#3F51B5", "offset": -0.30},
            {"name": "基本上是甩卖", "color": "#4B0082", "offset": -0.40},
        ]

        base_log10_price = (3.465 * math.log10(days)) - 8.17
        
        results = []
        for b in bands_config:
            price = 10 ** (base_log10_price + b["offset"])
            results.append(RainbowBand(
                name=b["name"],
                color=b["color"],
                price=price
            ))
        return results

    async def get_market_sentiment(self, symbols: Optional[List[str]] = None) -> List[MarketSentiment]:
        """获取市场情绪数据"""
        if not symbols:
            symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        
        sentiments = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for symbol in symbols:
                    try:
                        # 获取资金费率
                        funding_data = await self._request_json(
                            client,
                            f"{self.BINANCE_FAPI}/fundingRate",
                            {"symbol": symbol, "limit": 1},
                            context=f"funding rate for {symbol}",
                        )
                        funding_rate = float(funding_data[0].get("fundingRate", 0)) if funding_data else None
                        
                        # 获取多空比
                        ratio_data = await self._request_json(
                            client,
                            f"{self.BINANCE_FUTURES_DATA}/topLongShortAccountRatio",
                            {"symbol": symbol, "period": "5m", "limit": 1},
                            context=f"top long short ratio for {symbol}",
                        )
                        if not ratio_data:
                            ratio_data = await self._request_json(
                                client,
                                f"{self.BINANCE_FUTURES_DATA}/globalLongShortAccountRatio",
                                {"symbol": symbol, "period": "5m", "limit": 1},
                                context=f"global long short ratio for {symbol}",
                            )
                        long_short_ratio = float(ratio_data[0].get("longShortRatio", 0)) if ratio_data else None
                        
                        # 获取未平仓合约
                        oi_data = await self._request_json(
                            client,
                            f"{self.BINANCE_FAPI}/openInterest",
                            {"symbol": symbol},
                            context=f"open interest for {symbol}",
                        )
                        open_interest = float(oi_data.get("openInterest", 0)) if oi_data else None
                        
                        # 计算情绪评分
                        sentiment_score = self._calculate_sentiment_score(funding_rate, long_short_ratio)
                        
                        sentiments.append(MarketSentiment(
                            symbol=symbol,
                            funding_rate=funding_rate,
                            long_short_ratio=long_short_ratio,
                            open_interest=open_interest,
                            sentiment_score=sentiment_score,
                            timestamp=datetime.now()
                        ))
                        
                    except Exception as e:
                        logger.warning(f"Error fetching sentiment for {symbol}: {e}")
                        
        except Exception as e:
            logger.error(f"Error in get_market_sentiment: {e}")
        
        return sentiments

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Dict[str, Any],
        context: str,
    ) -> Optional[Any]:
        try:
            response = await client.get(url, params=params)
        except Exception as exc:
            logger.warning("Error requesting %s: %s", context, exc)
            return None

        if response.status_code != 200:
            log = logger.debug if response.status_code in {400, 404} else logger.warning
            log(
                "Skipped %s: status=%s body=%s",
                context,
                response.status_code,
                response.text[:200],
            )
            return None

        try:
            return response.json()
        except ValueError:
            logger.warning(
                "Skipped %s: non-json response body=%s",
                context,
                response.text[:200],
            )
            return None
    
    async def get_market_news(
        self,
        limit: int = 20,
        symbol: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> List[MarketNews]:
        """获取市场新闻"""
        if symbol:
            return await news_archive_service.ensure_symbol_news(symbol=symbol, limit=limit, hours=hours)
        return await news_archive_service.ensure_general_news(limit=limit, hours=hours)
    
    async def generate_trading_signals(self, symbols: Optional[List[str]] = None) -> List[TradingSignal]:
        """生成交易信号"""
        if not symbols:
            symbols = ["BTCUSDT", "ETHUSDT"]
        
        signals = []
        try:
            # 获取市场数据
            metrics = await self.get_watchlist_metrics(symbols)
            sentiments = await self.get_market_sentiment(symbols)
            
            for metric in metrics:
                sentiment = next((s for s in sentiments if s.symbol == metric.symbol), None)
                signal = self._analyze_trading_signal(metric, sentiment)
                if signal:
                    signals.append(signal)
                    
        except Exception as e:
            logger.error(f"Error generating trading signals: {e}")
        
        return signals

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[List[Any]]:
        """获取K线数据"""
        normalized_limit = max(1, min(limit, self.MAX_KLINES_LIMIT))
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BINANCE_FAPI}/klines",
                    params={
                        "symbol": symbol.upper(),
                        "interval": interval,
                        "limit": normalized_limit
                    }
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to fetch klines for {symbol}: {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            return []

    async def get_patterns(self, symbol: str, interval: str = "1h", limit: int = 500, tolerance: float = 0.35) -> List[Dict[str, Any]]:
        """识别 K 线形态（单K线形态如锤子线、吞没等）"""
        try:
            klines = await self.get_klines(symbol, interval, limit=limit)
            if not klines:
                return []
            
            # Run analysis
            patterns = pattern_recognizer.analyze(klines, tolerance=tolerance)
            # Convert dataclasses to dicts for JSON serialization with standard types
            return [
                {
                    "name": p.name,
                    "direction": p.direction,
                    "points": [
                        {
                            "index": int(pt.index), 
                            "price": float(pt.price), 
                            "time": int(pt.time)
                        } 
                        for pt in p.points
                    ]
                }
                for p in patterns
            ]
        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            return []

    async def scan_patterns(self, symbols: List[str] = None, interval: str = "1h", tolerance: float = 0.35) -> List[Dict[str, Any]]:
        """扫描多个币种的最新 K 线形态"""
        if not symbols:
            # Default to top volume if no list provided
            top_vol = await self.get_top_volume(20)
            symbols = [m.symbol for m in top_vol]
        
        results = []
        
        # Limit concurrency
        chunk_size = 5
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i+chunk_size]
            tasks = []
            for sym in chunk:
                tasks.append(self.get_patterns(sym, interval, limit=150, tolerance=tolerance)) # 只看最近的
            
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for sym, patterns in zip(chunk, chunk_results):
                if isinstance(patterns, list) and patterns:
                    # 获取最新的一个形态
                    latest = max(patterns, key=lambda p: p['points'][-1]['time'])
                    
                    now = datetime.now().timestamp() * 1000
                    last_point_time = latest['points'][-1]['time']
                    
                    # 检查是否是最近 5 根 K 线内形成的
                    duration_map = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
                    minutes = duration_map.get(interval, 60)
                    ms_per_candle = minutes * 60 * 1000
                    
                    if now - last_point_time < (5 * ms_per_candle):
                         results.append({
                             "symbol": sym,
                             "pattern": latest
                         })
                         
        return results

    async def get_funding_rate_rankings(self) -> Dict[str, List[FundingRateRanking]]:
        """获取全市场资金费率排行 (优先使用 Binance 合约全量数据作为代表)"""
        cache_key = "funding_rate_rankings"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Binance Premium Index API 返回所有合约的最新资金费率
                response = await client.get(f"{self.BINANCE_FAPI}/premiumIndex")
                data = response.json()
                
                rates = []
                for item in data:
                    symbol = item.get("symbol", "")
                    if not symbol.endswith("USDT"): continue
                    
                    rate = float(item.get("lastFundingRate", 0))
                    rates.append(FundingRateRanking(
                        symbol=symbol,
                        rate=round(rate * 100, 4), # 转换为百分比
                        exchange="Binance"
                    ))
                
                # 排序获取两极
                high_rates = sorted(rates, key=lambda x: x.rate, reverse=True)[:10]
                low_rates = sorted(rates, key=lambda x: x.rate)[:10]
                
                result = {
                    "high": high_rates,
                    "low": low_rates
                }
                self._update_cache(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Error fetching funding rate rankings: {e}")
            return {"high": [], "low": []}

    async def get_dashboard_data(self, watchlist: Optional[List[str]] = None) -> MarketInsightDashboard:
        """获取完整的市场洞察数据看板"""
        try:
            # 并发获取所有数据
            overview_task = self.get_market_overview()
            starters_task = self.get_altcoin_starters(10)
            volume_task = self.get_top_volume(10)
            watchlist_task = self.get_watchlist_metrics(watchlist)
            sentiment_task = self.get_market_sentiment()
            fear_greed_task = self.get_fear_greed_data(30)
            rainbow_task = self.get_rainbow_bands()
            news_task = self.get_market_news(20)
            signals_task = self.generate_trading_signals(watchlist)
            funding_task = self.get_funding_rate_rankings()
            anomalies_task = anomaly_monitor_service.list_active_anomalies(8)
            
            results = await asyncio.gather(
                overview_task,
                starters_task,
                volume_task,
                watchlist_task,
                sentiment_task,
                fear_greed_task,
                rainbow_task,
                news_task,
                signals_task,
                funding_task,
                anomalies_task,
                return_exceptions=True
            )
            
            # 处理结果，如果有异常则使用默认值
            overview = results[0] if not isinstance(results[0], Exception) else MarketOverview(timestamp=datetime.now())
            starters = results[1] if not isinstance(results[1], Exception) else []
            volume = results[2] if not isinstance(results[2], Exception) else []
            watchlist_metrics = results[3] if not isinstance(results[3], Exception) else []
            sentiment = results[4] if not isinstance(results[4], Exception) else []
            fear_greed_data = results[5] if not isinstance(results[5], Exception) else {"current": None, "history": []}
            rainbow_bands = results[6] if not isinstance(results[6], Exception) else []
            news = results[7] if not isinstance(results[7], Exception) else []
            signals = results[8] if not isinstance(results[8], Exception) else []
            funding_rates = results[9] if not isinstance(results[9], Exception) else {"high": [], "low": []}
            active_anomalies = results[10] if not isinstance(results[10], Exception) else []
            last_anomaly_scan_at = anomaly_monitor_service.get_last_scan_at()
            
            # GPT-5.1 深度分析 (如果启用)
            ai_analysis = None
            if os.getenv("ENABLE_GPT_5_1", "True").lower() == "true":
                ai_analysis = self._generate_gpt5_analysis(overview, sentiment, signals, funding_rates)
            
            return MarketInsightDashboard(
                overview=overview,
                altcoin_starters=starters,
                top_volume=volume,
                watchlist=watchlist_metrics,
                funding_rate_high=funding_rates.get("high", []),
                funding_rate_low=funding_rates.get("low", []),
                sentiment=sentiment,
                fear_greed_index=fear_greed_data.get("current"),
                fear_greed_history=fear_greed_data.get("history", []),
                rainbow_bands=rainbow_bands,
                news=news,
                signals=signals,
                active_anomalies=active_anomalies,
                last_anomaly_scan_at=last_anomaly_scan_at,
                ai_analysis=ai_analysis,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            # 返回空数据
            return MarketInsightDashboard(
                overview=MarketOverview(timestamp=datetime.now()),
                timestamp=datetime.now()
            )
    
    # Helper methods
    
    async def _get_top_movers(self, limit: int, ascending: bool) -> List[MarketMetrics]:
        """获取合约涨跌幅排行"""
        cache_key = f"top_{'losers' if ascending else 'gainers'}_{limit}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 使用合约 API
                response = await client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
                tickers = response.json()
                
                # 过滤USDT交易对并排序
                usdt_pairs = [t for t in tickers if t.get("symbol", "").endswith("USDT")]
                sorted_pairs = sorted(
                    usdt_pairs,
                    key=lambda x: float(x.get("priceChangePercent", 0)),
                    reverse=not ascending
                )[:limit]
                
                metrics = [self._ticker_to_metrics(t) for t in sorted_pairs]
                self._update_cache(cache_key, metrics)
                return metrics
                
        except Exception as e:
            logger.error(f"Error fetching top movers: {e}")
            return []
    
    def _ticker_to_metrics(self, ticker: dict) -> MarketMetrics:
        """将币安ticker数据转换为MarketMetrics"""
        return MarketMetrics(
            symbol=ticker.get("symbol", ""),
            last_price=float(ticker.get("lastPrice", 0)),
            price_change_24h=float(ticker.get("priceChange", 0)),
            price_change_percent_24h=float(ticker.get("priceChangePercent", 0)),
            volume_24h=float(ticker.get("volume", 0)),
            quote_volume_24h=float(ticker.get("quoteVolume", 0)),
            high_24h=float(ticker.get("highPrice", 0)),
            low_24h=float(ticker.get("lowPrice", 0)),
            timestamp=datetime.now()
        )
    
    def _calculate_sentiment_score(self, funding_rate: Optional[float], long_short_ratio: Optional[float]) -> str:
        """计算市场情绪评分"""
        if funding_rate is None or long_short_ratio is None:
            return "neutral"
        
        # 综合资金费率和多空比判断情绪
        score = 0
        
        # 资金费率影响（正费率说明多头强势）
        if funding_rate > 0.001:
            score += 2
        elif funding_rate > 0.0005:
            score += 1
        elif funding_rate < -0.001:
            score -= 2
        elif funding_rate < -0.0005:
            score -= 1
        
        # 多空比影响
        if long_short_ratio > 2:
            score += 2
        elif long_short_ratio > 1.5:
            score += 1
        elif long_short_ratio < 0.5:
            score -= 2
        elif long_short_ratio < 0.7:
            score -= 1
        
        if score >= 3:
            return "extreme_greed"
        elif score >= 1:
            return "greed"
        elif score <= -3:
            return "extreme_fear"
        elif score <= -1:
            return "fear"
        else:
            return "neutral"
    
    def _analyze_trading_signal(self, metric: MarketMetrics, sentiment: Optional[MarketSentiment]) -> Optional[TradingSignal]:
        """分析生成交易信号"""
        reasons = []
        signal_type = "neutral"
        strength = 50.0
        
        # 基于价格变化
        if metric.price_change_percent_24h > 5:
            reasons.append(f"24小时涨幅{metric.price_change_percent_24h:.2f}%，动能强劲")
            strength += 15
        elif metric.price_change_percent_24h < -5:
            reasons.append(f"24小时跌幅{abs(metric.price_change_percent_24h):.2f}%，可能超跌")
            strength += 10
        
        # 基于情绪
        if sentiment:
            if sentiment.sentiment_score == "extreme_fear":
                reasons.append("市场极度恐慌，可能是抄底机会")
                signal_type = "long"
                strength += 20
            elif sentiment.sentiment_score == "extreme_greed":
                reasons.append("市场极度贪婪，注意回调风险")
                signal_type = "short"
                strength += 15
            
            if sentiment.funding_rate and abs(sentiment.funding_rate) > 0.001:
                rate_percent = sentiment.funding_rate * 100
                reasons.append(f"资金费率{rate_percent:.4f}%，{'多头' if rate_percent > 0 else '空头'}占优")
        
        # 如果没有明显信号，返回None
        if not reasons or strength < 60:
            return None
        
        # 生成更专业的建议价格 (动态 RR 2.0-3.0)
        suggested_entry = metric.last_price

        # 计算 ATR 估算 (简单使用 24h 波动率的 1/10)
        volatility = (metric.high_24h - metric.low_24h) / metric.last_price if metric.last_price > 0 else 0.05
        sl_pct = max(min(volatility * 0.5, 0.05), 0.015)  # 1.5% - 5.0% 止损
        tp_pct = sl_pct * 2.5  # 盈亏比 2.5
        rr_ratio = round(tp_pct / sl_pct, 2)

        # neutral 信号也提供参考值（前端用于双向显示）
        if signal_type == "long":
            suggested_stop_loss = metric.last_price * (1 - sl_pct)
            suggested_take_profit = metric.last_price * (1 + tp_pct)
        elif signal_type == "short":
            suggested_stop_loss = metric.last_price * (1 + sl_pct)
            suggested_take_profit = metric.last_price * (1 - tp_pct)
        else:
            suggested_stop_loss = metric.last_price * (1 - sl_pct)
            suggested_take_profit = metric.last_price * (1 + tp_pct)

        return TradingSignal(
            symbol=metric.symbol,
            signal_type=signal_type,
            strength=min(strength, 100),
            reasons=reasons,
            suggested_entry=suggested_entry,
            suggested_stop_loss=suggested_stop_loss,
            suggested_take_profit=suggested_take_profit,
            rr_ratio=rr_ratio,
            sl_percent=sl_pct,
            tp_percent=tp_pct,
            timestamp=datetime.now()
        )
    
    def _generate_gpt5_analysis(self, overview: MarketOverview, sentiments: List[MarketSentiment], signals: List[TradingSignal], funding_rates: Dict[str, List[FundingRateRanking]]) -> str:
        """GPT-5.1 模拟分析逻辑 - 提供更详细的操作建议"""
        btc_sentiment = next((s for s in sentiments if s.symbol == "BTCUSDT"), None)
        
        analysis = "### 🤖 GPT-5.1 深度市场操作建议\n\n"
        
        # 1. 宏观环境分析
        analysis += "#### 📊 宏观环境\n"
        if overview.btc_dominance:
            dom = overview.btc_dominance
            if dom > 55:
                analysis += "- **吸血行情：** BTC 市占率高达 {:.1f}%。目前资金正在由山寨币流向 BTC，建议减少山寨币持仓，关注 BTC 突破机会。\n".format(dom)
            elif dom < 45:
                analysis += "- **山寨季活跃：** BTC 市占率处于低位（{:.1f}%）。市场处于高风险偏好阶段，山寨币波动性剧增，适合进行短线捕捉。\n".format(dom)
            else:
                analysis += "- **震荡行情：** BTC 市占率（{:.1f}%）稳定。市场正在寻找方向，建议以区间交易为主。\n".format(dom)
        
        # 2. 资金面分析 (新增加 Coinglass 逻辑)
        analysis += "\n#### 🌊 资金面分析 (Coinglass/Binance)\n"
        high_fr = funding_rates.get("high", [])
        low_fr = funding_rates.get("low", [])
        
        if high_fr:
            top_positive = high_fr[0]
            analysis += "- **过热预警：** **{}** 资金费率高达 **{:.4f}%**。该币种多头极度拥挤，随时可能发生清算导致价格快速回撤。\n".format(top_positive.symbol, top_positive.rate)
        
        if low_fr:
            top_negative = low_fr[0]
            if top_negative.rate < -0.01:
                analysis += "- **扎空潜力：** **{}** 处于负费率状态（{:.4f}%）。空头高度集结，极易引发爆发式反弹。\n".format(top_negative.symbol, top_negative.rate)
        
        # 3. 情绪评级
        analysis += "\n#### 🌪️ 情绪评级\n"
        if btc_sentiment:
            score = btc_sentiment.sentiment_score.upper()
            analysis += "- **当前评级：** **{}**\n".format(score)
        
        # 4. 具体操作策略
        analysis += "\n#### 🚀 核心操作策略\n"
        if signals:
            long_signals = [s for s in signals if s.signal_type == "long"]
            short_signals = [s for s in signals if s.signal_type == "short"]
            
            if long_signals:
                analysis += "**看多布局（推荐）：**\n"
                for s in long_signals[:2]:
                    analysis += "- **{}**：参考入场点 ${:,.2f}。".format(s.symbol, s.suggested_entry or 0)
                    analysis += " 目标 **${:,.2f}**。".format(s.suggested_take_profit or 0)
                    analysis += " 止损 ${:,.2f}。\n".format(s.suggested_stop_loss or 0)
            
            if short_signals:
                analysis += "**看空布局（谨慎）：**\n"
                for s in short_signals[:2]:
                    analysis += "- **{}**：参考压制位 ${:,.2f}。".format(s.symbol, s.suggested_entry or 0)
                    analysis += " 目标 **${:,.2f}**。".format(s.suggested_take_profit or 0)
                    analysis += " 止损 ${:,.2f}。\n".format(s.suggested_stop_loss or 0)
        
        if not signals:
            analysis += "目前全市场未捕捉到高确定性交易信号，建议保持离场观望，重点关注是否有 **锤子线** 或 **吞没形态** 在关键支撑位出现。\n"
        
        analysis += "\n**📢 GPT-5.1 最终提醒：** 当前识别已调整为 **单K线形态捕捉器**。寻找“刺透”、“锤子线”等反转信号结合高低资金费率进行博弈。操作前请确保您的单笔风险敞口。"
        
        return analysis

    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        cache_time = self._cache[key]["timestamp"]
        cache_ttl = self._cache[key].get("ttl", self._cache_ttl)
        return (datetime.now() - cache_time).total_seconds() < cache_ttl
    
    def _update_cache(self, key: str, data: Any):
        """更新缓存"""
        self._cache[key] = {
            "data": data,
            "timestamp": datetime.now()
        }


# 全局实例
market_insight_service = MarketInsightService()
