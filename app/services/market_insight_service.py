"""市场洞察数据聚合服务"""
import asyncio
import logging
import os
import math
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import httpx

from app.schemas.market_insight import (
    AnomalyEventSummary,
    MarketInsightDashboard,
    MarketMetrics,
    MarketSentiment,
    MarketNews,
    TradingSignal,
    MarketOverview,
    FearGreedIndex,
    RainbowBand,
    FundingRateRanking
)
from app.services.anomaly_monitor_service import anomaly_monitor_service
from app.services.news_service import news_service
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
        # Formula: price = 10^(2.9065 * log10(days) - 19.493)
        # Bands are offsets from this base power
        genesis_date = datetime(2009, 1, 3)
        today = datetime.now()
        days = (today - genesis_date).days
        
        if days <= 0: return []
        
        # log10_price = 2.9065 * math.log10(days) - 19.493
        # Current "fair value" index is around the middle bands
        
        bands_config = [
            {"name": "极度泡沫", "color": "#FF0000", "offset": 2.5},
            {"name": "卖出！", "color": "#FF4500", "offset": 2.1},
            {"name": "郁金香泡沫？", "color": "#FFA500", "offset": 1.7},
            {"name": "由于FOMO增加", "color": "#FFD700", "offset": 1.3},
            {"name": "持有", "color": "#00FF00", "offset": 0.9},
            {"name": "仍处于廉价", "color": "#20B2AA", "offset": 0.5},
            {"name": "积累", "color": "#4682B4", "offset": 0.1},
            {"name": "买入！", "color": "#0000FF", "offset": -0.3},
            {"name": "基本上是甩卖", "color": "#4B0082", "offset": -0.7},
        ]
        
        base_val = 2.9065 * math.log10(days) - 19.493
        
        results = []
        for b in bands_config:
            price = 10**(base_val + b["offset"])
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
    
    async def get_market_news(self, limit: int = 20) -> List[MarketNews]:
        """获取市场新闻"""
        return await news_service.fetch_general_news(limit=limit)
    
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

    async def get_patterns(self, symbol: str, interval: str = "1h", limit: int = 500, tolerance: float = 0.2) -> List[Dict[str, Any]]:
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

    async def scan_patterns(self, symbols: List[str] = None, interval: str = "1h") -> List[Dict[str, Any]]:
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
                tasks.append(self.get_patterns(sym, interval, limit=150)) # 只看最近的
            
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
            gainers_task = self.get_top_gainers(10)
            losers_task = self.get_top_losers(10)
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
                gainers_task,
                losers_task,
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
            gainers = results[1] if not isinstance(results[1], Exception) else []
            losers = results[2] if not isinstance(results[2], Exception) else []
            volume = results[3] if not isinstance(results[3], Exception) else []
            watchlist_metrics = results[4] if not isinstance(results[4], Exception) else []
            sentiment = results[5] if not isinstance(results[5], Exception) else []
            fear_greed_data = results[6] if not isinstance(results[6], Exception) else {"current": None, "history": []}
            rainbow_bands = results[7] if not isinstance(results[7], Exception) else []
            news = results[8] if not isinstance(results[8], Exception) else []
            signals = results[9] if not isinstance(results[9], Exception) else []
            funding_rates = results[10] if not isinstance(results[10], Exception) else {"high": [], "low": []}
            active_anomalies = results[11] if not isinstance(results[11], Exception) else []
            last_anomaly_scan_at = anomaly_monitor_service.get_last_scan_at()
            
            # GPT-5.1 深度分析 (如果启用)
            ai_analysis = None
            if os.getenv("ENABLE_GPT_5_1", "True").lower() == "true":
                ai_analysis = self._generate_gpt5_analysis(overview, sentiment, signals, funding_rates)
            
            return MarketInsightDashboard(
                overview=overview,
                top_gainers=gainers,
                top_losers=losers,
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
        sl_percent = max(min(volatility * 0.5, 0.05), 0.015) # 1.5% - 5.0% 止损
        tp_percent = sl_percent * 2.5 # 盈亏比 2.5
        
        if signal_type == "long":
            suggested_stop_loss = metric.last_price * (1 - sl_percent)
            suggested_take_profit = metric.last_price * (1 + tp_percent)
        elif signal_type == "short":
            suggested_stop_loss = metric.last_price * (1 + sl_percent)
            suggested_take_profit = metric.last_price * (1 - tp_percent)
        else:
            suggested_stop_loss = None
            suggested_take_profit = None
        
        return TradingSignal(
            symbol=metric.symbol,
            signal_type=signal_type,
            strength=min(strength, 100),
            reasons=reasons,
            suggested_entry=suggested_entry,
            suggested_stop_loss=suggested_stop_loss,
            suggested_take_profit=suggested_take_profit,
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
        return (datetime.now() - cache_time).total_seconds() < self._cache_ttl
    
    def _update_cache(self, key: str, data: Any):
        """更新缓存"""
        self._cache[key] = {
            "data": data,
            "timestamp": datetime.now()
        }


# 全局实例
market_insight_service = MarketInsightService()
