"""市场洞察API端点"""
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.schemas.market_insight import (
    AnomalyEventDetail,
    AnomalyEventSummary,
    MarketInsightDashboard,
    MarketMetrics,
    MarketSentiment,
    MarketNews,
    TradingSignal,
    MarketOverview
)
from app.services.anomaly_monitor_service import anomaly_monitor_service
from app.services.market_insight_service import market_insight_service
from app.services.news_archive_service import news_archive_service

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
    limit: int = Query(10, ge=1, le=100, description="返回数量")
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


@router.get("/news", response_model=List[MarketNews])
async def get_market_news(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    symbol: Optional[str] = Query(None, description="按币种过滤，如: BTCUSDT"),
    hours: Optional[int] = Query(None, ge=1, le=720, description="仅返回最近 N 小时的归档新闻"),
):
    """获取新闻归档列表"""
    news_items = await market_insight_service.get_market_news(limit=limit, symbol=symbol, hours=hours)
    if hours is None:
        return news_items

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    filtered = [item for item in news_items if item.published_at >= cutoff]
    if filtered:
        return filtered[:limit]

    return news_archive_service.list_news(limit=limit, symbol=symbol, hours=hours)


@router.get("/anomalies", response_model=List[AnomalyEventSummary])
async def get_anomalies(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    status: str = Query("active", description="状态: active, resolved, all")
):
    """获取异常事件列表"""
    normalized_status = None if status == "all" else status
    return await anomaly_monitor_service.list_anomalies(limit=limit, status=normalized_status)


@router.get("/anomalies/{event_id}", response_model=AnomalyEventDetail)
async def get_anomaly_detail(event_id: int):
    """获取异常事件详情"""
    detail = await anomaly_monitor_service.get_anomaly_detail(event_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Anomaly event not found")
    return detail


@router.post("/anomalies/scan", response_model=List[AnomalyEventSummary])
async def trigger_anomaly_scan(
    limit: int = Query(10, ge=1, le=100, description="返回最新活跃异常数量")
):
    """手动触发一次异常扫描"""
    await anomaly_monitor_service.scan_once()
    return await anomaly_monitor_service.list_active_anomalies(limit=limit)



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
    limit: int = Query(
        100,
        ge=1,
        le=market_insight_service.MAX_KLINES_LIMIT,
        description="返回数量，Binance 合约最大 1500",
    )
):
    """获取历史K线数据"""
    return await market_insight_service.get_klines(symbol, interval, limit)
