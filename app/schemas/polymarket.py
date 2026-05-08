from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PolymarketLeaderboardEntry(BaseModel):
    rank: Optional[int] = Field(None, description="榜单名次")
    pnl: Optional[float] = Field(None, description="榜单收益")
    volume: Optional[float] = Field(None, description="榜单成交额")
    category: Optional[str] = Field(None, description="榜单分类")
    time_period: Optional[str] = Field(None, description="榜单周期")


class PolymarketFollowabilityComponent(BaseModel):
    name: str = Field(..., description="评分组件名称")
    score: float = Field(..., description="组件得分 0-100")
    weight: float = Field(..., description="权重 0-1")
    reason: str = Field(..., description="评分原因")


class PolymarketFollowabilityReport(BaseModel):
    score: float = Field(..., description="跟单可行性总分 0-100")
    verdict: str = Field(..., description="结论: candidate/watchlist/cautious/avoid")
    likely_bot: bool = Field(..., description="是否疑似机器人")
    skip_recommended: bool = Field(..., description="是否建议跳过自动跟单")
    reasons: List[str] = Field(default_factory=list, description="核心判断原因")
    bot_reasons: List[str] = Field(default_factory=list, description="机器人判定原因")
    median_trade_interval_seconds: Optional[float] = Field(None, description="近30天成交中位间隔")
    trades_per_hour_30d: Optional[float] = Field(None, description="近30天平均每小时成交次数")
    avg_trade_size_usdc_30d: Optional[float] = Field(None, description="近30天平均单笔成交额")
    top_market_share_30d: Optional[float] = Field(None, description="近30天最活跃单市场占比")
    components: List[PolymarketFollowabilityComponent] = Field(default_factory=list)


class PolymarketActivityItem(BaseModel):
    proxy_wallet: Optional[str] = Field(None, description="钱包地址")
    timestamp: datetime = Field(..., description="事件时间")
    activity_type: str = Field(..., description="活动类型")
    condition_id: Optional[str] = Field(None, description="市场 condition id")
    side: Optional[str] = Field(None, description="方向 BUY/SELL")
    size: Optional[float] = Field(None, description="份额数量")
    usdc_size: Optional[float] = Field(None, description="名义金额")
    price: Optional[float] = Field(None, description="价格")
    asset: Optional[str] = Field(None, description="资产 token id")
    outcome: Optional[str] = Field(None, description="结果方向")
    title: Optional[str] = Field(None, description="市场标题")
    slug: Optional[str] = Field(None, description="市场 slug")
    event_slug: Optional[str] = Field(None, description="事件 slug")
    transaction_hash: Optional[str] = Field(None, description="链上交易 hash")


class PolymarketPositionItem(BaseModel):
    asset: Optional[str] = Field(None, description="资产 token id")
    condition_id: Optional[str] = Field(None, description="市场 condition id")
    size: Optional[float] = Field(None, description="份额数量")
    avg_price: Optional[float] = Field(None, description="平均成本")
    initial_value: Optional[float] = Field(None, description="初始投入")
    current_value: Optional[float] = Field(None, description="当前价值")
    cash_pnl: Optional[float] = Field(None, description="当前现金收益")
    percent_pnl: Optional[float] = Field(None, description="收益率")
    realized_pnl: Optional[float] = Field(None, description="已实现收益")
    cur_price: Optional[float] = Field(None, description="当前价格")
    redeemable: Optional[bool] = Field(None, description="是否可兑换")
    outcome: Optional[str] = Field(None, description="结果方向")
    title: Optional[str] = Field(None, description="市场标题")
    slug: Optional[str] = Field(None, description="市场 slug")
    event_slug: Optional[str] = Field(None, description="事件 slug")
    end_date: Optional[str] = Field(None, description="到期日期")


class PolymarketClosedPositionItem(BaseModel):
    asset: Optional[str] = Field(None, description="资产 token id")
    condition_id: Optional[str] = Field(None, description="市场 condition id")
    avg_price: Optional[float] = Field(None, description="平均成本")
    total_bought: Optional[float] = Field(None, description="累计买入额")
    realized_pnl: Optional[float] = Field(None, description="已实现收益")
    cur_price: Optional[float] = Field(None, description="平仓时参考价")
    timestamp: Optional[datetime] = Field(None, description="平仓时间")
    outcome: Optional[str] = Field(None, description="结果方向")
    title: Optional[str] = Field(None, description="市场标题")
    slug: Optional[str] = Field(None, description="市场 slug")
    event_slug: Optional[str] = Field(None, description="事件 slug")


class PolymarketTraderSummary(BaseModel):
    wallet_address: str = Field(..., description="交易员钱包地址")
    name: Optional[str] = Field(None, description="显示名称")
    pseudonym: Optional[str] = Field(None, description="平台昵称")
    bio: Optional[str] = Field(None, description="简介")
    profile_image: Optional[str] = Field(None, description="头像")
    x_username: Optional[str] = Field(None, description="X 用户名")
    verified_badge: bool = Field(False, description="是否认证")
    leaderboard: Optional[PolymarketLeaderboardEntry] = Field(None, description="榜单信息")
    trade_count_7d: int = Field(0, description="近7天成交次数")
    trade_count_30d: int = Field(0, description="近30天成交次数")
    trade_count_24h: int = Field(0, description="近24小时成交次数")
    volume_usdc_7d: float = Field(0.0, description="近7天成交额")
    volume_usdc_30d: float = Field(0.0, description="近30天成交额")
    markets_traded_30d: int = Field(0, description="近30天覆盖市场数")
    win_rate_30d: Optional[float] = Field(None, description="近30天平仓胜率 0-1")
    realized_pnl_30d: Optional[float] = Field(None, description="近30天已实现收益")
    avg_realized_pnl_30d: Optional[float] = Field(None, description="近30天单笔平均已实现收益")
    open_positions_count: int = Field(0, description="当前持仓数")
    open_positions_value: float = Field(0.0, description="当前持仓总价值")
    activity_mix: Dict[str, int] = Field(default_factory=dict, description="活动类型统计")
    median_trade_interval_seconds: Optional[float] = Field(None, description="近30天成交中位间隔")
    trades_per_hour_30d: Optional[float] = Field(None, description="近30天平均每小时成交次数")
    avg_trade_size_usdc_30d: Optional[float] = Field(None, description="近30天平均成交额")
    top_market_share_30d: Optional[float] = Field(None, description="近30天最活跃市场占比")
    latest_activity_at: Optional[datetime] = Field(None, description="最近活跃时间")
    trader_style: str = Field(..., description="交易风格标签")
    followability: PolymarketFollowabilityReport = Field(..., description="跟单可行性分析")
    analysis_notes: List[str] = Field(default_factory=list, description="分析说明")


class PolymarketTraderProfile(PolymarketTraderSummary):
    created_at: Optional[datetime] = Field(None, description="资料创建时间")
    recent_markets: List[str] = Field(default_factory=list, description="近期活跃市场")
    recent_activities: List[PolymarketActivityItem] = Field(default_factory=list, description="近期活动")
    current_positions: List[PolymarketPositionItem] = Field(default_factory=list, description="当前持仓")
    recent_closed_positions: List[PolymarketClosedPositionItem] = Field(default_factory=list, description="近期平仓记录")


class PolymarketTraderCachePoolInfo(BaseModel):
    cache_key: str = Field(..., description="缓存键")
    category: str = Field(..., description="榜单分类")
    time_period: str = Field(..., description="榜单周期")
    order_by: str = Field(..., description="排序字段")
    limit: int = Field(..., description="缓存候选数量")
    trader_count: int = Field(..., description="当前缓存内交易员数量")
    last_refresh_at: Optional[datetime] = Field(None, description="最后刷新时间")
    expires_at: Optional[datetime] = Field(None, description="缓存过期时间")
    is_stale: bool = Field(..., description="是否已过期")
    last_error: Optional[str] = Field(None, description="最近一次刷新错误")


class PolymarketTraderCacheStatus(BaseModel):
    running: bool = Field(..., description="后台缓存任务是否运行中")
    interval_seconds: int = Field(..., description="后台刷新间隔")
    ttl_seconds: int = Field(..., description="缓存 TTL")
    default_pools: List[str] = Field(default_factory=list, description="默认刷新的候选池")
    pools: List[PolymarketTraderCachePoolInfo] = Field(default_factory=list, description="缓存池状态列表")
