"""市场洞察API端点"""
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.core.database import SessionLocal
from app.models.market_anomaly import NarrativeEvent
from app.schemas.market_insight import (
    AnomalyEventDetail,
    AnomalyEventSummary,
    MarketInsightDashboard,
    MarketMetrics,
    MarketSentiment,
    MarketNews,
    NarrativeEventSummary,
    TradingSignal,
    MarketOverview
)
from app.services.anomaly_monitor_service import anomaly_monitor_service
from app.services.market_insight_service import market_insight_service
from app.services.news_archive_service import news_archive_service
from app.services.narrative_detector import narrative_detector

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
    tolerance: float = Query(0.35, ge=0.05, le=0.8, description="识别严格度，越大越严格")
):
    """识别 K 线形态（单K线形态如锤子线、吞没等）"""
    return await market_insight_service.get_patterns(symbol, interval, limit, tolerance)

@router.get("/patterns/scan")
async def scan_patterns(
    interval: str = Query("1h", description="时间周期"),
    symbols: Optional[List[str]] = Query(None, description="指定扫描币种列表"),
    tolerance: float = Query(0.35, ge=0.05, le=0.8, description="识别严格度，越大越严格")
):
    """扫描市场寻找最新 K 线形态"""
    return await market_insight_service.scan_patterns(symbols, interval, tolerance)


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


NARRATIVE_TYPE_LABELS = {
    "product_launch": "产品/功能上线",
    "exchange_listing": "交易所上币",
    "partnership": "重大合作/投资",
    "regulation": "监管利好",
    "insider_leak": "内幕/传闻",
    "pure_speculation": "纯市场炒作",
    "macro_sentiment": "宏观情绪驱动",
    "other": "其他",
}


def _to_narrative_summary(event: NarrativeEvent) -> NarrativeEventSummary:
    return NarrativeEventSummary(
        id=event.id,
        symbol=event.symbol,
        narrative_type=event.narrative_type,
        narrative_type_label=NARRATIVE_TYPE_LABELS.get(event.narrative_type, event.narrative_type),
        narrative_title=event.narrative_title,
        narrative_summary=event.narrative_summary,
        confidence=event.confidence,
        is_positive_catalyst=str(getattr(event, "is_positive_catalyst", "false")).lower() == "true",
        catalyst_strength=getattr(event, "catalyst_strength", 0) or 0,
        suggested_action=getattr(event, "suggested_action", None),
        risk_warning=getattr(event, "risk_warning", None),
        price_change_percent_24h=event.price_change_percent_24h,
        anomaly_score=event.anomaly_score,
        anomaly_event_id=event.anomaly_event_id,
        news_sources=event.news_sources or [],
        detected_at=event.detected_at,
    )


@router.get("/narratives", response_model=List[NarrativeEventSummary])
async def list_narratives(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    symbol: Optional[str] = Query(None, description="交易对符号过滤"),
    narrative_type: Optional[str] = Query(None, description="叙事类型过滤"),
    min_confidence: float = Query(0, ge=0, le=100, description="最低置信度"),
    positive_only: bool = Query(False, description="仅返回重大利好"),
    hours: int = Query(72, ge=1, le=720, description="最近N小时内"),
):
    """获取重大利好叙事事件列表"""
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = db.query(NarrativeEvent).filter(NarrativeEvent.detected_at >= cutoff)
        if symbol:
            query = query.filter(NarrativeEvent.symbol == symbol.upper())
        if narrative_type:
            query = query.filter(NarrativeEvent.narrative_type == narrative_type)
        if min_confidence > 0:
            query = query.filter(NarrativeEvent.confidence >= min_confidence)
        if positive_only:
            query = query.filter(NarrativeEvent.is_positive_catalyst == True)
        events = query.order_by(NarrativeEvent.detected_at.desc()).limit(limit).all()
        return [_to_narrative_summary(e) for e in events]
    finally:
        db.close()


@router.get("/narratives/{narrative_id}", response_model=NarrativeEventSummary)
async def get_narrative_detail(narrative_id: int):
    """获取叙事事件详情"""
    db = SessionLocal()
    try:
        event = db.query(NarrativeEvent).filter(NarrativeEvent.id == narrative_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Narrative event not found")
        return _to_narrative_summary(event)
    finally:
        db.close()


@router.post("/narratives/detect", response_model=NarrativeEventSummary)
async def trigger_narrative_detect(
    symbol: str = Query(..., description="交易对符号"),
    limit: int = Query(6, ge=1, le=20, description="关联新闻数量"),
):
    """手动触发叙事检测（用于测试）"""
    from app.services.news_archive_service import news_archive_service

    news_items = await news_archive_service.ensure_symbol_news(symbol.upper(), limit=limit)
    anomaly_data = {
        "symbol": symbol.upper(),
        "anomaly_score": 0.65,
        "price_change_percent_24h": 10.0,
    }
    result = await narrative_detector.detect(anomaly_data, news_items)
    if not result:
        raise HTTPException(status_code=500, detail="Narrative detection failed")
    return NarrativeEventSummary(
        id=0,
        symbol=symbol.upper(),
        narrative_type=result.get("narrative_type", "other"),
        narrative_type_label=NARRATIVE_TYPE_LABELS.get(result.get("narrative_type", "other"), "其他"),
        narrative_title=result.get("narrative_title", ""),
        narrative_summary=result.get("narrative_summary"),
        confidence=result.get("confidence", 0),
        is_positive_catalyst=result.get("is_positive_catalyst", False),
        catalyst_strength=result.get("catalyst_strength", 0),
        suggested_action=result.get("suggested_action"),
        risk_warning=result.get("risk_warning"),
    )


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
