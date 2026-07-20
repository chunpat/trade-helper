"""市场洞察数据看板相关Schema"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class FearGreedIndex(BaseModel):
    """恐惧贪婪指数"""
    value: int = Field(..., description="指数值 0-100")
    value_classification: str = Field(..., description="分类: Extreme Fear, Fear, Neutral, Greed, Extreme Greed")
    timestamp: str = Field(..., description="时间戳")


class RainbowBand(BaseModel):
    """彩虹图带信息"""
    name: str = Field(..., description="带等级名称")
    color: str = Field(..., description="颜色")
    price: float = Field(..., description="该等级对应价格")


class MarketSentiment(BaseModel):
    """市场情绪指标"""
    symbol: str = Field(..., description="交易对符号")
    fear_greed_index: Optional[float] = Field(None, description="恐惧贪婪指数 0-100")
    funding_rate: Optional[float] = Field(None, description="资金费率")
    long_short_ratio: Optional[float] = Field(None, description="多空比")
    open_interest: Optional[float] = Field(None, description="未平仓合约量")
    sentiment_score: Optional[str] = Field(None, description="情绪评分: extreme_fear, fear, neutral, greed, extreme_greed")
    timestamp: datetime = Field(default_factory=datetime.now)


class MarketNews(BaseModel):
    """市场消息"""
    id: Optional[int] = None
    title: str = Field(..., description="新闻标题")
    source: str = Field(..., description="消息来源")
    source_domain: Optional[str] = Field(None, description="来源域名")
    sentiment: Optional[str] = Field(None, description="情绪倾向: positive, negative, neutral")
    url: Optional[str] = Field(None, description="新闻链接")
    summary: Optional[str] = Field(None, description="摘要")
    published_at: datetime = Field(..., description="发布时间")
    symbols: Optional[List[str]] = Field(default_factory=list, description="相关币种")


class MarketMetrics(BaseModel):
    """市场指标"""
    symbol: str = Field(..., description="交易对符号")
    last_price: float = Field(..., description="最新价格")
    price_change_24h: float = Field(..., description="24小时价格变化")
    price_change_percent_24h: float = Field(..., description="24小时涨跌幅%")
    volume_24h: float = Field(..., description="24小时成交量")
    quote_volume_24h: Optional[float] = Field(None, description="24小时成交额")
    volume_change_percent_24h: Optional[float] = Field(None, description="24小时成交量变化%")
    high_24h: float = Field(..., description="24小时最高价")
    low_24h: float = Field(..., description="24小时最低价")
    market_cap: Optional[float] = Field(None, description="市值")
    startup_score: Optional[float] = Field(None, description="放量启动评分 0-100")
    volume_ratio: Optional[float] = Field(None, description="最近完整15分钟成交量相对前序均量倍数")
    momentum_1h: Optional[float] = Field(None, description="最近1小时涨幅%")
    startup_reason: Optional[str] = Field(None, description="入选启动榜的原因")
    timestamp: datetime = Field(default_factory=datetime.now)


class MomentumSignal(BaseModel):
    """5/15分钟短线量价启动信号。"""
    symbol: str
    last_price: float
    change_5m: float
    change_15m: float
    volume_ratio_5m: float
    volume_ratio_15m: float
    quote_volume_24h: float
    price_change_percent_24h: float
    score: float
    reason: str
    volatility_7d: float = Field(0, description="基于1小时收益率计算的7日实现波动率%")
    resistance: Optional[float] = Field(None, description="前48小时压力位")
    support: Optional[float] = Field(None, description="前48小时支撑位")
    breakout_percent: float = Field(0, description="突破压力位幅度%")
    breakout_threshold: float = Field(0, description="依据币种波动率计算的最小有效突破幅度%")
    breakout_confirmed: bool = Field(False, description="是否完成放量有效突破")


class MomentumRadarResponse(BaseModel):
    five_minute: List[MomentumSignal] = Field(default_factory=list)
    fifteen_minute: List[MomentumSignal] = Field(default_factory=list)
    scanned_count: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


class MarketCapVolatility(BaseModel):
    rank: int
    symbol: str
    name: str
    last_price: float
    market_cap: float
    price_change_percent_24h: float
    volatility_7d: float = Field(..., description="基于7天小时价格计算的实现波动率%")


class BinanceEquityVolatility(BaseModel):
    symbol: str = Field(..., description="币安交易代码")
    underlying_symbol: str = Field(..., description="对应股票或 ETF 代码")
    name: str
    product_type: str = Field(..., description="stock_perpetual、etf_perpetual 或 tokenized_stock")
    product_type_label: str
    last_price: float
    price_change_percent_24h: float
    quote_volume_24h: float
    volatility_7d: float = Field(..., description="基于币安最近7天小时价格计算的实现波动率%")


class MarketCapVolatilityResponse(BaseModel):
    items: List[MarketCapVolatility] = Field(default_factory=list)
    binance_equities: List[BinanceEquityVolatility] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class AnomalyTradingAdvice(BaseModel):
    """异常事件的交易建议"""
    bias: str = Field(..., description="交易偏向: long, short, neutral")
    confidence: float = Field(..., description="建议置信度 0-100")
    recommendation: str = Field(..., description="交易建议")
    suggested_entry: Optional[float] = Field(None, description="建议入场价")
    suggested_stop_loss: Optional[float] = Field(None, description="建议止损价")
    suggested_take_profit: Optional[float] = Field(None, description="建议止盈价")
    risk_note: Optional[str] = Field(None, description="风险说明")


class AnomalyEventSummary(BaseModel):
    """异常事件摘要"""
    id: int
    symbol: str
    event_type: str
    anomaly_score: float
    anomaly_level: str
    trigger_reasons: List[str] = Field(default_factory=list)
    last_price: Optional[float] = None
    price_change_percent_24h: Optional[float] = None
    quote_volume_24h: Optional[float] = None
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    long_short_ratio: Optional[float] = None
    credibility_label: str = Field(..., description="真实性评级")
    credibility_score: Optional[float] = None
    source_summary: Optional[str] = None
    trade_bias: str = Field(..., description="交易偏向")
    trade_confidence: Optional[float] = None
    trade_recommendation: Optional[str] = None
    news_count: int = 0
    first_detected_at: Optional[datetime] = None
    last_detected_at: Optional[datetime] = None


class AnomalyEventDetail(AnomalyEventSummary):
    """异常事件详情"""
    description: Optional[str] = None
    evidence_summary: Optional[str] = None
    raw_metrics: Optional[Dict[str, Any]] = None
    advice: Optional[AnomalyTradingAdvice] = None
    news: List[MarketNews] = Field(default_factory=list)


class NarrativeEventSummary(BaseModel):
    """重大利好叙事事件摘要"""
    id: int
    symbol: str = Field(..., description="交易对符号")
    narrative_type: str = Field(..., description="叙事类型: product_launch/exchange_listing/partnership/regulation/insider_leak/pure_speculation/macro_sentiment/other")
    narrative_type_label: str = Field(..., description="叙事类型中文")
    narrative_title: str = Field(..., description="叙事标题")
    narrative_summary: Optional[str] = Field(None)
    confidence: float = Field(..., description="置信度 0-100")
    is_positive_catalyst: bool = Field(False)
    catalyst_strength: float = Field(0, description="利好强度 0-100")
    suggested_action: Optional[str] = Field(None)
    risk_warning: Optional[str] = Field(None)
    price_change_percent_24h: Optional[float] = Field(None)
    anomaly_score: Optional[float] = Field(None)
    anomaly_event_id: Optional[int] = Field(None)
    news_sources: List[str] = Field(default_factory=list)
    detected_at: Optional[datetime] = None


class TradingSignal(BaseModel):
    """交易信号"""
    symbol: str = Field(..., description="交易对符号")
    signal_type: str = Field(..., description="信号类型: long, short, neutral")
    strength: float = Field(..., description="信号强度 0-100")
    reasons: List[str] = Field(default_factory=list, description="信号原因")
    suggested_entry: Optional[float] = Field(None, description="建议入场价")
    suggested_stop_loss: Optional[float] = Field(None, description="建议止损价")
    suggested_take_profit: Optional[float] = Field(None, description="建议止盈价")
    rr_ratio: Optional[float] = Field(None, description="风险收益比 (止盈距离/止损距离)")
    sl_percent: Optional[float] = Field(None, description="止损百分比（用于前端计算双向价格）")
    tp_percent: Optional[float] = Field(None, description="止盈百分比（用于前端计算双向价格）")
    timestamp: datetime = Field(default_factory=datetime.now)


class FundingRateRanking(BaseModel):
    """资金费率排名"""
    symbol: str = Field(..., description="币种")
    rate: float = Field(..., description="资金费率(百分比)")
    exchange: Optional[str] = Field(None, description="交易所")


class MarketOverview(BaseModel):
    """市场总览"""
    total_market_cap: Optional[float] = Field(None, description="总市值")
    total_volume_24h: Optional[float] = Field(None, description="24小时总成交量")
    btc_dominance: Optional[float] = Field(None, description="BTC市值占比%")
    active_cryptocurrencies: Optional[int] = Field(None, description="活跃加密货币数量")
    timestamp: datetime = Field(default_factory=datetime.now)


class MarketInsightDashboard(BaseModel):
    """市场洞察数据看板完整数据"""
    overview: MarketOverview
    top_gainers: List[MarketMetrics] = Field(default_factory=list, description="涨幅榜前10")
    top_losers: List[MarketMetrics] = Field(default_factory=list, description="跌幅榜前10")
    altcoin_starters: List[MarketMetrics] = Field(default_factory=list, description="山寨币放量启动榜")
    top_volume: List[MarketMetrics] = Field(default_factory=list, description="成交量榜前10")
    watchlist: List[MarketMetrics] = Field(default_factory=list, description="自选币种数据")
    funding_rate_high: List[FundingRateRanking] = Field(default_factory=list, description="正费率最高排名")
    funding_rate_low: List[FundingRateRanking] = Field(default_factory=list, description="负费率最高排名")
    sentiment: List[MarketSentiment] = Field(default_factory=list, description="主要币种情绪")
    fear_greed_index: Optional[FearGreedIndex] = Field(None, description="当前恐惧贪婪指数")
    fear_greed_history: List[FearGreedIndex] = Field(default_factory=list, description="历史恐惧贪婪指数")
    rainbow_bands: List[RainbowBand] = Field(default_factory=list, description="BTC彩虹图带价格")
    news: List[MarketNews] = Field(default_factory=list, description="最新市场消息")
    signals: List[TradingSignal] = Field(default_factory=list, description="交易信号")
    active_anomalies: List[AnomalyEventSummary] = Field(default_factory=list, description="活跃异常事件")
    last_anomaly_scan_at: Optional[datetime] = Field(None, description="最近一次异常扫描时间")
    ai_analysis: Optional[str] = Field(None, description="GPT-5.1 提供的深度市场分析")
    timestamp: datetime = Field(default_factory=datetime.now)


class WatchlistItem(BaseModel):
    """自选列表项"""
    symbol: str = Field(..., description="交易对符号")
    
    class Config:
        from_attributes = True
