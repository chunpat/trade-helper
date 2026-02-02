"""市场洞察数据看板相关Schema"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


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
    sentiment: Optional[str] = Field(None, description="情绪倾向: positive, negative, neutral")
    url: Optional[str] = Field(None, description="新闻链接")
    published_at: datetime = Field(..., description="发布时间")
    symbols: Optional[List[str]] = Field(default_factory=list, description="相关币种")


class MarketMetrics(BaseModel):
    """市场指标"""
    symbol: str = Field(..., description="交易对符号")
    last_price: float = Field(..., description="最新价格")
    price_change_24h: float = Field(..., description="24小时价格变化")
    price_change_percent_24h: float = Field(..., description="24小时涨跌幅%")
    volume_24h: float = Field(..., description="24小时成交量")
    volume_change_percent_24h: Optional[float] = Field(None, description="24小时成交量变化%")
    high_24h: float = Field(..., description="24小时最高价")
    low_24h: float = Field(..., description="24小时最低价")
    market_cap: Optional[float] = Field(None, description="市值")
    timestamp: datetime = Field(default_factory=datetime.now)


class TradingSignal(BaseModel):
    """交易信号"""
    symbol: str = Field(..., description="交易对符号")
    signal_type: str = Field(..., description="信号类型: long, short, neutral")
    strength: float = Field(..., description="信号强度 0-100")
    reasons: List[str] = Field(default_factory=list, description="信号原因")
    suggested_entry: Optional[float] = Field(None, description="建议入场价")
    suggested_stop_loss: Optional[float] = Field(None, description="建议止损价")
    suggested_take_profit: Optional[float] = Field(None, description="建议止盈价")
    timestamp: datetime = Field(default_factory=datetime.now)


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
    top_volume: List[MarketMetrics] = Field(default_factory=list, description="成交量榜前10")
    watchlist: List[MarketMetrics] = Field(default_factory=list, description="自选币种数据")
    sentiment: List[MarketSentiment] = Field(default_factory=list, description="主要币种情绪")
    news: List[MarketNews] = Field(default_factory=list, description="最新市场消息")
    signals: List[TradingSignal] = Field(default_factory=list, description="交易信号")
    ai_analysis: Optional[str] = Field(None, description="GPT-5.1 提供的深度市场分析")
    timestamp: datetime = Field(default_factory=datetime.now)


class WatchlistItem(BaseModel):
    """自选列表项"""
    symbol: str = Field(..., description="交易对符号")
    
    class Config:
        from_attributes = True
