"""市场洞察API端点"""
from fastapi import APIRouter, Query
from typing import List, Optional

from app.schemas.market_insight import (
    MarketInsightDashboard,
    MarketMetrics,
    MarketSentiment,
    MarketNews,
    TradingSignal,
    MarketOverview
)
from app.services.market_insight_service import market_insight_service

router = APIRouter(prefix="/market-insight", tags=["market-insight"])


@router.get("/dashboard", response_model=MarketInsightDashboard)
async def get_market_insight_dashboard(
    watchlist: Optional[str] = Query(None, description="自选币种列表，逗号分隔，如: BTCUSDT,ETHUSDT")
):
    """获取市场洞察数据看板完整数据
    
    包含：
    - 市场总览
    - 涨幅榜Top10
    - 跌幅榜Top10
    - 成交量榜Top10
    - 自选币种数据
    - 市场情绪指标
    - 最新消息
    - 交易信号
    """
    watchlist_symbols = watchlist.split(",") if watchlist else None
    return await market_insight_service.get_dashboard_data(watchlist_symbols)


@router.get("/overview", response_model=MarketOverview)
async def get_market_overview():
    """获取市场总览数据"""
    return await market_insight_service.get_market_overview()


@router.get("/top-gainers", response_model=List[MarketMetrics])
async def get_top_gainers(
    limit: int = Query(10, ge=1, le=50, description="返回数量")
):
    """获取涨幅榜"""
    return await market_insight_service.get_top_gainers(limit)


@router.get("/top-losers", response_model=List[MarketMetrics])
async def get_top_losers(
    limit: int = Query(10, ge=1, le=50, description="返回数量")
):
    """获取跌幅榜"""
    return await market_insight_service.get_top_losers(limit)


@router.get("/top-volume", response_model=List[MarketMetrics])
async def get_top_volume(
    limit: int = Query(10, ge=1, le=50, description="返回数量")
):
    """获取成交量排行"""
    return await market_insight_service.get_top_volume(limit)


@router.get("/watchlist", response_model=List[MarketMetrics])
async def get_watchlist_metrics(
    symbols: str = Query(..., description="币种列表，逗号分隔，如: BTCUSDT,ETHUSDT")
):
    """获取指定币种的实时数据"""
    symbol_list = symbols.split(",")
    return await market_insight_service.get_watchlist_metrics(symbol_list)


@router.get("/sentiment", response_model=List[MarketSentiment])
async def get_market_sentiment(
    symbols: Optional[str] = Query(None, description="币种列表，逗号分隔。不指定则返回主要币种")
):
    """获取市场情绪数据
    
    包含：
    - 恐惧贪婪指数
    - 资金费率
    - 多空比
    - 未平仓合约量
    - 情绪评分
    """
    symbol_list = symbols.split(",") if symbols else None
    return await market_insight_service.get_market_sentiment(symbol_list)


@router.get("/klines")
async def get_klines(
    symbol: str = Query(..., description="交易对"),
    interval: str = Query("1h", description="时间周期"),
    limit: int = Query(100, description="数据条数")
):
    """获取K线数据"""
    return await market_insight_service.get_klines(symbol, interval, limit)


@router.get("/patterns")
async def get_patterns(
    symbol: str = Query(..., description="交易对"),
    interval: str = Query("1h", description="时间周期"),
    limit: int = Query(500, description="数据条数"),
    tolerance: float = Query(0.2, description="容错率")
):
    """识别 K 线形态（单K线形态如锤子线、吞没等）"""
    return await market_insight_service.get_patterns(symbol, interval, limit, tolerance)

@router.get("/patterns/scan")
async def scan_patterns(
    interval: str = Query("1h", description="时间周期"),
    symbols: Optional[List[str]] = Query(None, description="指定扫描币种列表")
):
    """扫描市场寻找最新 K 线形态"""
    return await market_insight_service.scan_patterns(symbols, interval)



@router.get("/signals", response_model=List[TradingSignal])
async def get_trading_signals(
    symbols: Optional[str] = Query(None, description="币种列表，逗号分隔")
):
    """获取交易信号
    
    基于多个维度分析生成交易信号：
    - 价格变化趋势
    - 市场情绪
    - 资金费率
    - 多空比
    """
    symbol_list = symbols.split(",") if symbols else None
    return await market_insight_service.generate_trading_signals(symbol_list)


@router.get("/klines")
async def get_klines(
    symbol: str = Query(..., description="交易对符号，如: BTCUSDT"),
    interval: str = Query("1h", description="时间间隔: 1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量")
):
    """获取历史K线数据"""
    return await market_insight_service.get_klines(symbol, interval, limit)
