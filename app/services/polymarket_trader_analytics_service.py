import asyncio
import math
import statistics
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from app.schemas.polymarket import (
    PolymarketActivityItem,
    PolymarketClosedPositionItem,
    PolymarketFollowabilityComponent,
    PolymarketFollowabilityReport,
    PolymarketLeaderboardEntry,
    PolymarketPositionItem,
    PolymarketTraderProfile,
    PolymarketTraderSummary,
)
from app.services.polymarket_data_client import PolymarketDataClient


class PolymarketTraderAnalyticsService:
    def __init__(self, client: Optional[PolymarketDataClient] = None):
        self.client = client or PolymarketDataClient()

    @staticmethod
    def normalize_wallet(wallet: str) -> str:
        normalized = (wallet or "").strip()
        if not normalized.startswith("0x"):
            raise ValueError("钱包地址格式错误，必须是 0x 开头的 42 位地址")
        if len(normalized) != 42:
            raise ValueError("钱包地址长度错误，必须是 42 位")
        try:
            int(normalized[2:], 16)
        except ValueError as exc:
            raise ValueError("钱包地址格式错误，必须是十六进制地址") from exc
        return normalized

    @staticmethod
    def _to_datetime(value: Optional[object]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            if value > 10_000_000_000:
                value = value / 1000
            return datetime.utcfromtimestamp(value)
        if isinstance(value, str):
            try:
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _to_float(value: Optional[object]) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _activity_item(self, row: Dict) -> PolymarketActivityItem:
        return PolymarketActivityItem(
            proxy_wallet=row.get("proxyWallet"),
            timestamp=self._to_datetime(row.get("timestamp")) or datetime.utcnow(),
            activity_type=str(row.get("type") or "UNKNOWN"),
            condition_id=row.get("conditionId"),
            side=row.get("side"),
            size=self._to_float(row.get("size")),
            usdc_size=self._to_float(row.get("usdcSize")),
            price=self._to_float(row.get("price")),
            asset=row.get("asset"),
            outcome=row.get("outcome"),
            title=row.get("title"),
            slug=row.get("slug"),
            event_slug=row.get("eventSlug"),
            transaction_hash=row.get("transactionHash"),
        )

    def _position_item(self, row: Dict) -> PolymarketPositionItem:
        return PolymarketPositionItem(
            asset=row.get("asset"),
            condition_id=row.get("conditionId"),
            size=self._to_float(row.get("size")),
            avg_price=self._to_float(row.get("avgPrice")),
            initial_value=self._to_float(row.get("initialValue")),
            current_value=self._to_float(row.get("currentValue")),
            cash_pnl=self._to_float(row.get("cashPnl")),
            percent_pnl=self._to_float(row.get("percentPnl")),
            realized_pnl=self._to_float(row.get("realizedPnl")),
            cur_price=self._to_float(row.get("curPrice")),
            redeemable=row.get("redeemable"),
            outcome=row.get("outcome"),
            title=row.get("title"),
            slug=row.get("slug"),
            event_slug=row.get("eventSlug"),
            end_date=row.get("endDate"),
        )

    def _closed_position_item(self, row: Dict) -> PolymarketClosedPositionItem:
        return PolymarketClosedPositionItem(
            asset=row.get("asset"),
            condition_id=row.get("conditionId"),
            avg_price=self._to_float(row.get("avgPrice")),
            total_bought=self._to_float(row.get("totalBought")),
            realized_pnl=self._to_float(row.get("realizedPnl")),
            cur_price=self._to_float(row.get("curPrice")),
            timestamp=self._to_datetime(row.get("timestamp")),
            outcome=row.get("outcome"),
            title=row.get("title"),
            slug=row.get("slug"),
            event_slug=row.get("eventSlug"),
        )

    def _build_leaderboard_entry(
        self,
        raw: Optional[Dict],
        *,
        category: Optional[str] = None,
        time_period: Optional[str] = None,
    ) -> Optional[PolymarketLeaderboardEntry]:
        if not raw:
            return None
        rank = raw.get("rank")
        try:
            rank = int(rank) if rank is not None else None
        except (TypeError, ValueError):
            rank = None
        return PolymarketLeaderboardEntry(
            rank=rank,
            pnl=self._to_float(raw.get("pnl")),
            volume=self._to_float(raw.get("vol")),
            category=category,
            time_period=time_period,
        )

    @staticmethod
    def _expanded_leaderboard_specs(
        *,
        category: str,
        time_period: str,
        order_by: str,
        limit: int,
    ) -> List[Tuple[str, str, str, int, int]]:
        page_size = min(max(limit, 20), 25)
        alternate_order = "VOL" if order_by == "PNL" else "PNL"
        specs: List[Tuple[str, str, str, int, int]] = []
        seen = set()

        def append_spec(item_category: str, item_time_period: str, item_order_by: str, item_offset: int) -> None:
            spec = (item_category, item_time_period, item_order_by, page_size, item_offset)
            if spec in seen:
                return
            seen.add(spec)
            specs.append(spec)

        if time_period == "DAY":
            adjacent_periods = ["WEEK"]
        elif time_period == "WEEK":
            adjacent_periods = ["MONTH", "DAY"]
        elif time_period == "MONTH":
            adjacent_periods = ["WEEK"]
        else:
            adjacent_periods = ["MONTH", "WEEK"]

        if category == "OVERALL":
            related_categories = ["CRYPTO", "POLITICS", "FINANCE"]
        else:
            related_categories = ["OVERALL"]

        append_spec(category, time_period, order_by, 0)
        append_spec(category, time_period, order_by, page_size)
        append_spec(category, time_period, alternate_order, 0)

        for adjacent_period in adjacent_periods:
            append_spec(category, adjacent_period, order_by, 0)

        for related_category in related_categories:
            append_spec(related_category, time_period, order_by, 0)

        if adjacent_periods:
            pivot_period = adjacent_periods[0]
            for related_category in related_categories[:2]:
                append_spec(related_category, pivot_period, order_by, 0)

        return specs

    @staticmethod
    def _filter_since(items: Sequence, attr: str, cutoff: datetime) -> List:
        return [item for item in items if getattr(item, attr) and getattr(item, attr) >= cutoff]

    @staticmethod
    def _safe_sum(values: Sequence[Optional[float]]) -> float:
        return round(sum(value for value in values if value is not None), 4)

    @staticmethod
    def _trade_usdc_size(item: PolymarketActivityItem) -> float:
        if item.usdc_size is not None:
            return float(item.usdc_size)
        if item.size is not None and item.price is not None:
            return float(item.size) * float(item.price)
        return 0.0

    @staticmethod
    def _candidate_priority(summary: PolymarketTraderSummary) -> Tuple[int, int, int, float, float, int, float]:
        realized_pnl = float(summary.realized_pnl_30d or 0.0)
        volume_usdc = float(summary.volume_usdc_30d or 0.0)
        trade_count = int(summary.trade_count_30d or 0)
        followability_score = float(summary.followability.score if summary.followability else 0.0)
        profitable = 1 if realized_pnl > 0 else 0
        meaningful_volume = 1 if volume_usdc >= 1000 else 0
        quant_viable = 1 if profitable and trade_count >= 100 else 0
        return (
            profitable,
            meaningful_volume,
            quant_viable,
            realized_pnl,
            volume_usdc,
            trade_count,
            followability_score,
        )

    @staticmethod
    def _summary_from_profile(profile: PolymarketTraderProfile) -> PolymarketTraderSummary:
        return PolymarketTraderSummary(
            **profile.model_dump(
                exclude={"created_at", "recent_markets", "recent_activities", "current_positions", "recent_closed_positions"}
            )
        )

    def _median_trade_interval_seconds(self, trades: Sequence[PolymarketActivityItem]) -> Optional[float]:
        timestamps = sorted({int(item.timestamp.timestamp()) for item in trades if item.timestamp})
        if len(timestamps) < 2:
            return None
        gaps = [right - left for left, right in zip(timestamps, timestamps[1:]) if right - left >= 0]
        if not gaps:
            return None
        return round(float(statistics.median(gaps)), 2)

    def _trades_per_hour(self, trades: Sequence[PolymarketActivityItem]) -> Optional[float]:
        timestamps = [item.timestamp for item in trades if item.timestamp]
        if not timestamps:
            return None
        span_hours = max((max(timestamps) - min(timestamps)).total_seconds() / 3600.0, 24.0)
        return round(len(trades) / span_hours, 4)

    @staticmethod
    def _top_market_share(trades: Sequence[PolymarketActivityItem]) -> Optional[float]:
        condition_ids = [item.condition_id for item in trades if item.condition_id]
        if not condition_ids:
            return None
        counts = Counter(condition_ids)
        return round(max(counts.values()) / len(condition_ids), 4)

    @staticmethod
    def _recent_markets(trades: Sequence[PolymarketActivityItem], limit: int = 8) -> List[str]:
        seen = []
        for item in sorted(trades, key=lambda trade: trade.timestamp, reverse=True):
            title = item.title or item.slug or item.condition_id
            if title and title not in seen:
                seen.append(title)
            if len(seen) >= limit:
                break
        return seen

    def _detect_trader_style(
        self,
        *,
        trade_count_30d: int,
        median_interval_seconds: Optional[float],
        top_market_share: Optional[float],
        open_positions_count: int,
    ) -> str:
        if median_interval_seconds is not None and median_interval_seconds < 60:
            return "high_frequency"
        if trade_count_30d >= 120:
            return "high_frequency"
        if top_market_share is not None and top_market_share >= 0.65:
            return "specialist"
        if open_positions_count >= 8:
            return "broad_portfolio"
        return "discretionary"

    def _build_followability(
        self,
        *,
        trade_count_24h: int,
        trade_count_30d: int,
        median_interval_seconds: Optional[float],
        trades_per_hour_30d: Optional[float],
        avg_trade_size_usdc_30d: Optional[float],
        top_market_share_30d: Optional[float],
        win_rate_30d: Optional[float],
        realized_pnl_30d: Optional[float],
        closed_count_30d: int,
    ) -> PolymarketFollowabilityReport:
        bot_reasons: List[str] = []
        reasons: List[str] = []

        if median_interval_seconds is not None and median_interval_seconds < 45:
            bot_reasons.append("近30天成交中位间隔低于 45 秒，明显偏机器执行")
        if trade_count_24h >= 40:
            bot_reasons.append("近24小时成交次数过高，人工实时跟单难度大")
        if avg_trade_size_usdc_30d is not None and avg_trade_size_usdc_30d < 20 and trade_count_30d >= 80:
            bot_reasons.append("单笔金额偏小但频率偏高，更像程序化切片成交")

        likely_bot = bool(bot_reasons)

        if median_interval_seconds is None:
            latency_score = 45.0
            latency_reason = "可用成交样本不足，延迟可复制性只能给中性分"
        elif median_interval_seconds >= 900:
            latency_score = 95.0
            latency_reason = "成交节奏较慢，人工或低频自动跟单更容易复制"
        elif median_interval_seconds >= 300:
            latency_score = 82.0
            latency_reason = "成交节奏适中，存在较好的信号追踪空间"
        elif median_interval_seconds >= 120:
            latency_score = 62.0
            latency_reason = "成交间隔较短，需要低延迟执行链路"
        elif median_interval_seconds >= 45:
            latency_score = 32.0
            latency_reason = "成交节奏偏快，稍有延迟就容易追价"
        else:
            latency_score = 10.0
            latency_reason = "成交过快，自动跟单大概率追不上"

        if avg_trade_size_usdc_30d is None:
            size_score = 45.0
            size_reason = "缺少成交额样本，暂按中性处理"
        elif avg_trade_size_usdc_30d < 10:
            size_score = 20.0
            size_reason = "平均单笔金额过小，复制后容易被手续费和滑点吞噬"
        elif avg_trade_size_usdc_30d < 50:
            size_score = 55.0
            size_reason = "平均单笔金额偏小，复制价值有限"
        elif avg_trade_size_usdc_30d <= 2000:
            size_score = 88.0
            size_reason = "平均单笔金额处于可复制区间"
        elif avg_trade_size_usdc_30d <= 10000:
            size_score = 68.0
            size_reason = "单笔金额较大，复制时需要关注盘口深度"
        else:
            size_score = 52.0
            size_reason = "单笔金额过大，复制时更容易吃到滑点"

        if closed_count_30d >= 5 and win_rate_30d is not None:
            stability_score = max(20.0, min(95.0, win_rate_30d * 100.0))
            if realized_pnl_30d is not None and realized_pnl_30d <= 0:
                stability_score = max(20.0, stability_score - 15.0)
                stability_reason = "平仓样本不少，但近30天收益未转正，稳定性一般"
            else:
                stability_reason = "有足够平仓样本，可用真实已实现结果评估稳定性"
        else:
            stability_score = 50.0
            stability_reason = "近30天平仓样本不足，收益稳定性只能给中性分"

        if top_market_share_30d is None:
            concentration_score = 55.0
            concentration_reason = "近期市场分布不明确，按中性处理"
        elif top_market_share_30d >= 0.8:
            concentration_score = 58.0
            concentration_reason = "过度集中在单一市场，复制风险取决于该市场流动性"
        elif top_market_share_30d >= 0.45:
            concentration_score = 78.0
            concentration_reason = "市场集中度适中，便于聚焦跟踪"
        elif top_market_share_30d >= 0.2:
            concentration_score = 85.0
            concentration_reason = "市场分散但不过度发散，复制覆盖面较合理"
        else:
            concentration_score = 60.0
            concentration_reason = "市场过于分散，策略跟踪面较宽"

        components = [
            PolymarketFollowabilityComponent(name="latency", score=latency_score, weight=0.35, reason=latency_reason),
            PolymarketFollowabilityComponent(name="size", score=size_score, weight=0.2, reason=size_reason),
            PolymarketFollowabilityComponent(name="stability", score=stability_score, weight=0.25, reason=stability_reason),
            PolymarketFollowabilityComponent(name="concentration", score=concentration_score, weight=0.2, reason=concentration_reason),
        ]

        score = sum(component.score * component.weight for component in components)
        if likely_bot:
            score -= 20.0
            reasons.append("交易行为疑似机器人，自动跟单需要显著折价")
        if median_interval_seconds is not None and median_interval_seconds < 45:
            reasons.append("交易过于高频，复制时更可能出现延迟追价")
        if avg_trade_size_usdc_30d is not None and avg_trade_size_usdc_30d < 20:
            reasons.append("单笔金额过小，跟单收益容易被成本抵消")
        if win_rate_30d is not None and win_rate_30d >= 0.6:
            reasons.append("近30天平仓胜率较高，具备观察价值")
        if realized_pnl_30d is not None and realized_pnl_30d > 0:
            reasons.append("近30天已实现收益为正")

        score = round(max(0.0, min(100.0, score)), 2)
        if likely_bot or score < 40:
            verdict = "avoid"
        elif score < 60:
            verdict = "cautious"
        elif score < 75:
            verdict = "watchlist"
        else:
            verdict = "candidate"

        skip_recommended = verdict in {"avoid", "cautious"}
        if not reasons:
            reasons.append("样本有限，建议先做模拟跟单验证")

        return PolymarketFollowabilityReport(
            score=score,
            verdict=verdict,
            likely_bot=likely_bot,
            skip_recommended=skip_recommended,
            reasons=reasons,
            bot_reasons=bot_reasons,
            median_trade_interval_seconds=median_interval_seconds,
            trades_per_hour_30d=trades_per_hour_30d,
            avg_trade_size_usdc_30d=avg_trade_size_usdc_30d,
            top_market_share_30d=top_market_share_30d,
            components=components,
        )

    async def _fetch_trader_bundle(self, wallet: str) -> Tuple[Optional[Dict], List[Dict], List[Dict], List[Dict]]:
        profile, activities, positions, closed_positions = await asyncio.gather(
            self.client.get_public_profile(wallet),
            self.client.get_activity(wallet, limit=200, offset=0),
            self.client.get_positions(wallet, limit=50, offset=0),
            self.client.get_closed_positions(wallet, limit=50, offset=0),
        )
        return profile, activities, positions, closed_positions

    async def analyze_trader(
        self,
        wallet: str,
        *,
        leaderboard_entry: Optional[Dict] = None,
        leaderboard_category: Optional[str] = None,
        leaderboard_time_period: Optional[str] = None,
    ) -> PolymarketTraderProfile:
        wallet = self.normalize_wallet(wallet)
        profile_raw, activity_rows, position_rows, closed_position_rows = await self._fetch_trader_bundle(wallet)

        activities = [self._activity_item(row) for row in activity_rows]
        trade_activities = [item for item in activities if item.activity_type == "TRADE"]
        positions = [self._position_item(row) for row in position_rows]
        closed_positions = [self._closed_position_item(row) for row in closed_position_rows]

        now = datetime.utcnow()
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)

        trades_24h = self._filter_since(trade_activities, "timestamp", cutoff_24h)
        trades_7d = self._filter_since(trade_activities, "timestamp", cutoff_7d)
        trades_30d = self._filter_since(trade_activities, "timestamp", cutoff_30d)
        closed_positions_30d = [item for item in closed_positions if item.timestamp and item.timestamp >= cutoff_30d]

        activity_mix = dict(Counter(item.activity_type for item in activities))
        volume_usdc_7d = self._safe_sum(self._trade_usdc_size(item) for item in trades_7d)
        volume_usdc_30d = self._safe_sum(self._trade_usdc_size(item) for item in trades_30d)
        avg_trade_size_usdc_30d = round(volume_usdc_30d / len(trades_30d), 4) if trades_30d else None
        markets_traded_30d = len({item.condition_id for item in trades_30d if item.condition_id})
        median_interval_seconds = self._median_trade_interval_seconds(trades_30d)
        trades_per_hour_30d = self._trades_per_hour(trades_30d)
        top_market_share_30d = self._top_market_share(trades_30d)

        realized_pnl_30d = self._safe_sum(item.realized_pnl for item in closed_positions_30d)
        win_samples = [item for item in closed_positions_30d if item.realized_pnl is not None]
        win_rate_30d = None
        avg_realized_pnl_30d = None
        if win_samples:
            win_rate_30d = round(len([item for item in win_samples if (item.realized_pnl or 0.0) > 0]) / len(win_samples), 4)
            avg_realized_pnl_30d = round(realized_pnl_30d / len(win_samples), 4)

        open_positions = [item for item in positions if (item.size or 0.0) > 0]
        open_positions_value = self._safe_sum(item.current_value for item in open_positions)
        latest_activity_at = max((item.timestamp for item in activities if item.timestamp), default=None)
        trader_style = self._detect_trader_style(
            trade_count_30d=len(trades_30d),
            median_interval_seconds=median_interval_seconds,
            top_market_share=top_market_share_30d,
            open_positions_count=len(open_positions),
        )

        followability = self._build_followability(
            trade_count_24h=len(trades_24h),
            trade_count_30d=len(trades_30d),
            median_interval_seconds=median_interval_seconds,
            trades_per_hour_30d=trades_per_hour_30d,
            avg_trade_size_usdc_30d=avg_trade_size_usdc_30d,
            top_market_share_30d=top_market_share_30d,
            win_rate_30d=win_rate_30d,
            realized_pnl_30d=realized_pnl_30d,
            closed_count_30d=len(win_samples),
        )

        notes: List[str] = []
        if leaderboard_entry:
            notes.append("该交易员来自 Polymarket leaderboard 候选池")
        if followability.likely_bot:
            notes.append("当前行为更偏程序化，建议先模拟跟单再考虑实盘")
        if trader_style == "high_frequency" and (realized_pnl_30d or 0) > 0:
            notes.append("该账户偏量化/高频风格，人工复制性一般，但可进一步评估自动化跟单可行性")
        if win_rate_30d is None:
            notes.append("近30天平仓样本不足，胜率仅供参考")
        if len(trades_30d) == 0:
            notes.append("近30天未观察到公开成交，可能不适合作为跟单目标")

        summary = PolymarketTraderSummary(
            wallet_address=wallet,
            name=(profile_raw or {}).get("name"),
            pseudonym=(profile_raw or {}).get("pseudonym"),
            bio=(profile_raw or {}).get("bio"),
            profile_image=(profile_raw or {}).get("profileImage"),
            x_username=(profile_raw or {}).get("xUsername"),
            verified_badge=bool((profile_raw or {}).get("verifiedBadge") or False),
            leaderboard=self._build_leaderboard_entry(
                leaderboard_entry,
                category=leaderboard_category,
                time_period=leaderboard_time_period,
            ),
            trade_count_7d=len(trades_7d),
            trade_count_30d=len(trades_30d),
            trade_count_24h=len(trades_24h),
            volume_usdc_7d=volume_usdc_7d,
            volume_usdc_30d=volume_usdc_30d,
            markets_traded_30d=markets_traded_30d,
            win_rate_30d=win_rate_30d,
            realized_pnl_30d=realized_pnl_30d if win_samples else None,
            avg_realized_pnl_30d=avg_realized_pnl_30d,
            open_positions_count=len(open_positions),
            open_positions_value=open_positions_value,
            activity_mix=activity_mix,
            median_trade_interval_seconds=median_interval_seconds,
            trades_per_hour_30d=trades_per_hour_30d,
            avg_trade_size_usdc_30d=avg_trade_size_usdc_30d,
            top_market_share_30d=top_market_share_30d,
            latest_activity_at=latest_activity_at,
            trader_style=trader_style,
            followability=followability,
            analysis_notes=notes,
        )

        return PolymarketTraderProfile(
            **summary.model_dump(),
            created_at=self._to_datetime((profile_raw or {}).get("createdAt")),
            recent_markets=self._recent_markets(trade_activities),
            recent_activities=sorted(activities, key=lambda item: item.timestamp, reverse=True)[:30],
            current_positions=open_positions[:20],
            recent_closed_positions=closed_positions[:20],
        )

    async def get_followability(self, wallet: str) -> PolymarketFollowabilityReport:
        profile = await self.analyze_trader(wallet)
        return profile.followability

    async def get_activity(self, wallet: str, *, limit: int = 100, hours: int = 72) -> List[PolymarketActivityItem]:
        wallet = self.normalize_wallet(wallet)
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        rows = await self.client.get_activity(wallet, limit=limit, offset=0)
        activities = [self._activity_item(row) for row in rows]
        return [item for item in activities if item.timestamp >= cutoff][:limit]

    async def list_traders(
        self,
        *,
        wallets: Optional[List[str]] = None,
        category: str = "OVERALL",
        time_period: str = "WEEK",
        order_by: str = "PNL",
        limit: int = 10,
    ) -> List[PolymarketTraderSummary]:
        if wallets:
            normalized_wallets = [self.normalize_wallet(wallet) for wallet in wallets[:limit]]
            profiles = await asyncio.gather(*(self.analyze_trader(wallet) for wallet in normalized_wallets))
            summaries = [self._summary_from_profile(profile) for profile in profiles]
            return sorted(summaries, key=self._candidate_priority, reverse=True)[:limit]

        discovery_specs = self._expanded_leaderboard_specs(
            category=category,
            time_period=time_period,
            order_by=order_by,
            limit=limit,
        )
        leaderboard_batches = await asyncio.gather(
            *(
                self.client.get_leaderboard(
                    category=item_category,
                    time_period=item_time_period,
                    order_by=item_order_by,
                    limit=item_limit,
                    offset=item_offset,
                )
                for item_category, item_time_period, item_order_by, item_limit, item_offset in discovery_specs
            )
        )

        candidate_rows: List[Dict] = []
        seen_wallets = set()
        analysis_limit = min(max(limit * 2, limit), 50)
        for rows in leaderboard_batches:
            for row in rows:
                wallet = row.get("proxyWallet")
                if not wallet or wallet in seen_wallets:
                    continue
                seen_wallets.add(wallet)
                candidate_rows.append(row)
                if len(candidate_rows) >= analysis_limit:
                    break
            if len(candidate_rows) >= analysis_limit:
                break

        tasks = []
        for row in candidate_rows:
            wallet = row.get("proxyWallet")
            if wallet:
                tasks.append(
                    self.analyze_trader(
                        wallet,
                        leaderboard_entry=row,
                        leaderboard_category=category,
                        leaderboard_time_period=time_period,
                    )
                )
        profiles = await asyncio.gather(*tasks)
        summaries = [self._summary_from_profile(profile) for profile in profiles]
        return sorted(summaries, key=self._candidate_priority, reverse=True)[:limit]


polymarket_trader_analytics_service = PolymarketTraderAnalyticsService()
