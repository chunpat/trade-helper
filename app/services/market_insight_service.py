"""市场洞察数据聚合服务"""
import asyncio
import logging
import os
import math
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import httpx

from app.schemas.market_insight import (
    MarketInsightDashboard,
    MarketMetrics,
    MarketSentiment,
    MarketNews,
    TradingSignal,
    MarketOverview,
    FearGreedIndex,
    RainbowBand
)
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
                        funding_response = await client.get(
                            f"{self.BINANCE_FAPI}/fundingRate",
                            params={"symbol": symbol, "limit": 1}
                        )
                        funding_data = funding_response.json()
                        funding_rate = float(funding_data[0].get("fundingRate", 0)) if funding_data else None
                        
                        # 获取多空比
                        ratio_response = await client.get(
                            f"{self.BINANCE_FAPI}/topLongShortAccountRatio",
                            params={"symbol": symbol, "period": "5m", "limit": 1}
                        )
                        ratio_data = ratio_response.json()
                        long_short_ratio = float(ratio_data[0].get("longShortRatio", 0)) if ratio_data else None
                        
                        # 获取未平仓合约
                        oi_response = await client.get(
                            f"{self.BINANCE_FAPI}/openInterest",
                            params={"symbol": symbol}
                        )
                        oi_data = oi_response.json()
                        open_interest = float(oi_data.get("openInterest", 0)) if oi_response.status_code == 200 else None
                        
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
    
    async def get_market_news(self, limit: int = 20) -> List[MarketNews]:
        """获取市场新闻（模拟数据，实际需要接入新闻API）"""
        # 这里返回模拟数据，实际应该接入CryptoPanic、CoinTelegraph等新闻API
        return []
    
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
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BINANCE_FAPI}/klines",
                    params={
                        "symbol": symbol.upper(),
                        "interval": interval,
                        "limit": limit
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

    async def get_harmonic_patterns(self, symbol: str, interval: str = "1h", limit: int = 500, tolerance: float = 0.2) -> List[Dict[str, Any]]:
        """识别谐波形态"""
        try:
            # Need sufficient data for patterns, fetch more history using requested limit
            # limit should be passed
            if limit > 1500: limit = 1500 # Binance Max
            
            klines = await self.get_klines(symbol, interval, limit=limit)
            if not klines:
                return []
            
            # Run analysis (CPU bound, could offload to thread pool if heavy, but ok for now)
            patterns = pattern_recognizer.analyze(klines, tolerance=tolerance)
            # Convert dataclasses to dicts for JSON serialization
            return [
                {
                    "name": p.name,
                    "direction": p.direction,
                    "error": p.error,
                    "points": [
                        {"index": pt.index, "price": pt.price, "time": pt.time} 
                        for pt in p.points
                    ]
                }
                for p in patterns
            ]
        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            return []

    async def scan_harmonic_patterns(self, symbols: List[str] = None, interval: str = "1h") -> List[Dict[str, Any]]:
        """扫描多个币种的最新谐波形态"""
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
                # We only need latest patterns, so limit klines to e.g. 200 is enough for detection 
                # but for big patterns we might need more. 500 is safe.
                tasks.append(self.get_harmonic_patterns(sym, interval, limit=500))
            
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for sym, patterns in zip(chunk, chunk_results):
                if isinstance(patterns, list) and patterns:
                    # Filter for RECENT patterns only
                    # Check if the last point (D) is within recent candles
                    # But pattern points have 'time' (timestamp).
                    # Let's say within last 12 hours for 1h chart? Or just last available pattern?
                    # Let's pick patterns where 'D' point index is close to end.
                    # Since we don't have total length here easily without klines, use timestamp.
                    # Actually, we can just return the latest one found.
                    
                    # Sort by last point time
                    if not patterns: continue
                    
                    # Get latest pattern
                    latest = max(patterns, key=lambda p: p['points'][-1]['time'])
                    
                    # Check if it's "fresh" (e.g. formed in last 5 candles?)
                    # If we don't check freshness, we just show "Latest pattern on this chart"
                    # User wants to find opportunities. So recent is better.
                    # Let's assume Klines end at NOW. 
                    # 1h interval = 3600*1000 ms.
                    # 5 candles = 5 hours.
                    
                    now = datetime.now().timestamp() * 1000
                    last_point_time = latest['points'][-1]['time']
                    
                    # Diff in ms
                    diff = now - last_point_time
                    # Interval in ms parsing: 1h, 4h, 15m
                    duration_map = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
                    minutes = duration_map.get(interval, 60)
                    ms_per_candle = minutes * 60 * 1000
                    
                    # If within last 10 candles
                    if diff < (10 * ms_per_candle):
                         results.append({
                             "symbol": sym,
                             "pattern": latest
                         })
                         
        return results

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
            
            # GPT-5.1 深度分析 (如果启用)
            ai_analysis = None
            if os.getenv("ENABLE_GPT_5_1", "True").lower() == "true":
                ai_analysis = self._generate_gpt5_analysis(overview, sentiment, signals)
            
            return MarketInsightDashboard(
                overview=overview,
                top_gainers=gainers,
                top_losers=losers,
                top_volume=volume,
                watchlist=watchlist_metrics,
                sentiment=sentiment,
                fear_greed_index=fear_greed_data.get("current"),
                fear_greed_history=fear_greed_data.get("history", []),
                rainbow_bands=rainbow_bands,
                news=news,
                signals=signals,
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
        
        # 生成建议价格
        suggested_entry = metric.last_price
        if signal_type == "long":
            suggested_stop_loss = metric.last_price * 0.97  # 3%止损
            suggested_take_profit = metric.last_price * 1.06  # 6%止盈
        elif signal_type == "short":
            suggested_stop_loss = metric.last_price * 1.03
            suggested_take_profit = metric.last_price * 0.94
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
    
    def _generate_gpt5_analysis(self, overview: MarketOverview, sentiments: List[MarketSentiment], signals: List[TradingSignal]) -> str:
        """GPT-5.1 模拟分析逻辑"""
        btc_sentiment = next((s for s in sentiments if s.symbol == "BTCUSDT"), None)
        
        analysis = "### GPT-5.1 深度市场洞察\n\n"
        
        # 宏观视角
        if overview.btc_dominance:
            if overview.btc_dominance > 50:
                analysis += " 目前 BTC 市占率处于高位（{:.2f}%），市场资金主要集中在主流资产。".format(overview.btc_dominance)
            else:
                analysis += " BTC 市占率较低（{:.2f}%），山寨币季节（Altseason）迹象明显。".format(overview.btc_dominance)
        
        # 情绪视角
        if btc_sentiment:
            analysis += " BTC 当前情绪评级为 **{}**。".format(btc_sentiment.sentiment_score.upper())
            if btc_sentiment.funding_rate and btc_sentiment.funding_rate > 0.0001:
                analysis += " 资金费率偏正，显示多头情绪高涨，需警惕多头挤压（Long Squeeze）。"
            elif btc_sentiment.funding_rate and btc_sentiment.funding_rate < 0:
                analysis += " 资金费率转负，空头密集，可能存在空头平仓引发的反弹风险。"
        
        # 交易机会
        if signals:
            long_signals = [s for s in signals if s.signal_type == "long"]
            short_signals = [s for s in signals if s.signal_type == "short"]
            
            analysis += "\n\n**核心监控：**\n"
            if long_signals:
                analysis += "- 看多机会：{}。\n".format(", ".join([s.symbol for s in long_signals[:3]]))
            if short_signals:
                analysis += "- 看空机会：{}。\n".format(", ".join([s.symbol for s in short_signals[:3]]))
        
        analysis += "\n\n**GPT-5.1 风险提示：** 市场处于波动期，建议分批入场，严格执行风控参数。"
        
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
