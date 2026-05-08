from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.polymarket import (
    PolymarketActivityItem,
    PolymarketTraderCachePoolInfo,
    PolymarketTraderCacheStatus,
    PolymarketFollowabilityReport,
    PolymarketTraderProfile,
    PolymarketTraderSummary,
)
from app.services.polymarket_data_client import PolymarketAPIError
from app.services.polymarket_trader_cache_service import polymarket_trader_cache_service
from app.services.polymarket_trader_analytics_service import polymarket_trader_analytics_service


router = APIRouter(prefix="/polymarket", tags=["polymarket"])


@router.get("/traders", response_model=List[PolymarketTraderSummary])
async def list_polymarket_traders(
    wallets: Optional[str] = Query(None, description="候选钱包地址列表，逗号分隔"),
    category: str = Query("OVERALL", description="榜单分类"),
    time_period: str = Query("WEEK", description="榜单周期 DAY/WEEK/MONTH/ALL"),
    order_by: str = Query("PNL", description="排序字段 PNL/VOL"),
    limit: int = Query(10, ge=1, le=20, description="返回数量"),
    use_cache: bool = Query(True, description="未指定 wallets 时是否优先读候选池缓存"),
    force_refresh: bool = Query(False, description="是否强制刷新缓存后再返回"),
):
    try:
        wallet_list = [item.strip() for item in wallets.split(",") if item.strip()] if wallets else None
        if wallet_list:
            return await polymarket_trader_analytics_service.list_traders(
                wallets=wallet_list,
                category=category.upper(),
                time_period=time_period.upper(),
                order_by=order_by.upper(),
                limit=limit,
            )
        if use_cache:
            return await polymarket_trader_cache_service.get_pool(
                category=category.upper(),
                time_period=time_period.upper(),
                order_by=order_by.upper(),
                limit=limit,
                force_refresh=force_refresh,
            )
        return await polymarket_trader_analytics_service.list_traders(
            wallets=None,
            category=category.upper(),
            time_period=time_period.upper(),
            order_by=order_by.upper(),
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PolymarketAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/traders/cache/refresh", response_model=PolymarketTraderCachePoolInfo)
async def refresh_polymarket_trader_cache(
    category: str = Query("OVERALL", description="榜单分类"),
    time_period: str = Query("WEEK", description="榜单周期"),
    order_by: str = Query("PNL", description="排序字段"),
    limit: int = Query(10, ge=1, le=20, description="候选数量"),
):
    try:
        await polymarket_trader_cache_service.refresh_pool(
            category=category.upper(),
            time_period=time_period.upper(),
            order_by=order_by.upper(),
            limit=limit,
        )
        status = polymarket_trader_cache_service.get_status()
        cache_key = f"{category.upper()}:{time_period.upper()}:{order_by.upper()}:{limit}"
        for pool in status.pools:
            if pool.cache_key == cache_key:
                return pool
        raise HTTPException(status_code=500, detail="cache refresh succeeded but snapshot missing")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/traders/cache/status", response_model=PolymarketTraderCacheStatus)
async def get_polymarket_trader_cache_status():
    return polymarket_trader_cache_service.get_status()


@router.get("/traders/{wallet}", response_model=PolymarketTraderProfile)
async def get_polymarket_trader_profile(
    wallet: str,
    use_cache: bool = Query(True, description="是否优先读取交易员详情缓存"),
    force_refresh: bool = Query(False, description="是否强制刷新交易员详情缓存"),
):
    try:
        if use_cache:
            return await polymarket_trader_cache_service.get_trader_profile(
                wallet=wallet,
                force_refresh=force_refresh,
            )
        return await polymarket_trader_analytics_service.analyze_trader(wallet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PolymarketAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/traders/{wallet}/activity", response_model=List[PolymarketActivityItem])
async def get_polymarket_trader_activity(
    wallet: str,
    limit: int = Query(100, ge=1, le=200, description="返回数量"),
    hours: int = Query(72, ge=1, le=720, description="最近 N 小时"),
    use_cache: bool = Query(True, description="是否优先读取交易员活动缓存"),
    force_refresh: bool = Query(False, description="是否强制刷新交易员活动缓存"),
):
    try:
        if use_cache:
            return await polymarket_trader_cache_service.get_trader_activity(
                wallet=wallet,
                limit=limit,
                hours=hours,
                force_refresh=force_refresh,
            )
        return await polymarket_trader_analytics_service.get_activity(wallet, limit=limit, hours=hours)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PolymarketAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/traders/{wallet}/followability", response_model=PolymarketFollowabilityReport)
async def get_polymarket_trader_followability(wallet: str):
    try:
        return await polymarket_trader_analytics_service.get_followability(wallet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PolymarketAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
