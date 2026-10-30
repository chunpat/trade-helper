"""市场洞察钉钉通知后台任务。"""
import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from app.core.database import SessionLocal
from app.models.notification import NotificationChannelConfig, NotificationDeliveryLog
from app.schemas.bollinger import BollingerSignal
from app.schemas.market_insight import MarketNews, MomentumRadarResponse, MomentumSignal
from app.schemas.rsi_divergence import RsiDivergenceSignal, get_rsi_rules
from app.services.bollinger_service import (
    BOLL_MULTIPLIER,
    BOLL_PERIOD,
    BOLL_SCAN_INTERVAL_MS,
    bollinger_service,
)
from app.services.dingtalk_notification_service import dingtalk_notification_service
from app.services.market_alert_presets import get_market_alert_preset
from app.services.market_insight_service import market_insight_service
from app.services.news_analysis_service import news_analysis_service
from app.services.news_archive_service import news_archive_service
from app.services.rsi_divergence_service import HOUR_MS, rsi_divergence_service

logger = logging.getLogger(__name__)


@dataclass
class MarketNotificationConfig:
    webhook_url: str
    secret: Optional[str]
    keyword: str
    preset_key: str
    preset_label: str
    radar_params: Dict[str, Any]
    min_score: float
    cooldown_minutes: int
    news_analysis_enabled: bool
    notify_market_breakout: bool = True
    notify_bollinger_breakout: bool = False
    notify_rsi_divergence: bool = False
    rsi_preset: str = "strict"
    rsi_cooldown_minutes: int = 240
    rsi_notify_after: Optional[datetime] = None


class MarketInsightNotificationService:
    EVENT_TYPE = "market_breakout"
    BOLLINGER_EVENT_TYPE = "bollinger_breakout"
    BOLLINGER_COOLDOWN_MINUTES = 60
    RSI_EVENT_TYPE = "rsi_divergence"
    REINFORCEMENT_LOOKBACK_HOURS = 24
    REINFORCEMENT_SCORE_DELTA = 10.0
    REINFORCEMENT_BREAKOUT_DELTA = 0.2
    REINFORCEMENT_VOLUME_MULTIPLIER = 1.25

    def __init__(self, interval: Optional[int] = None):
        self.interval = interval or int(
            os.getenv("MARKET_INSIGHT_NOTIFY_SCAN_INTERVAL", "60")
        )
        self._task = None
        self._running = False
        self._last_bollinger_slot = None
        self._scan_lock = asyncio.Lock()

    def _load_config(self) -> Optional[MarketNotificationConfig]:
        db = SessionLocal()
        try:
            config = (
                db.query(NotificationChannelConfig)
                .filter(NotificationChannelConfig.channel == "dingtalk")
                .first()
            )
            if (
                config is None
                or not config.enabled
                or not (config.notify_market_breakout or config.notify_bollinger_breakout or config.notify_rsi_divergence)
                or not config.webhook_url
            ):
                return None
            if config.notify_rsi_divergence and config.rsi_notify_after is None:
                config.rsi_notify_after = datetime.utcnow()
                db.commit()
            preset = get_market_alert_preset(
                str(config.market_alert_preset or "balanced")
            )
            return MarketNotificationConfig(
                webhook_url=config.webhook_url,
                secret=config.secret,
                keyword=str(config.keyword or "TradeHelper"),
                preset_key=preset.key,
                preset_label=preset.label,
                radar_params=dict(preset.radar_params),
                min_score=preset.min_score,
                cooldown_minutes=preset.cooldown_minutes,
                news_analysis_enabled=bool(config.market_news_analysis_enabled),
                notify_market_breakout=bool(config.notify_market_breakout),
                notify_bollinger_breakout=bool(config.notify_bollinger_breakout),
                notify_rsi_divergence=bool(config.notify_rsi_divergence),
                rsi_preset=config.rsi_preset or "strict",
                rsi_cooldown_minutes=config.rsi_cooldown_minutes or 240,
                rsi_notify_after=config.rsi_notify_after,
            )
        finally:
            db.close()

    @staticmethod
    def _collect_candidates(
        radar: MomentumRadarResponse,
        min_score: float,
    ) -> List[Dict[str, Any]]:
        candidates: Dict[str, Dict[str, Any]] = {}
        period_groups = (
            ("5分钟", radar.five_minute),
            ("15分钟", radar.fifteen_minute),
        )
        for period, signals in period_groups:
            for signal in signals:
                if not signal.breakout_confirmed or float(signal.score) < min_score:
                    continue
                existing = candidates.get(signal.symbol)
                if existing is None:
                    candidates[signal.symbol] = {
                        "signal": signal,
                        "periods": [period],
                    }
                    continue
                if period not in existing["periods"]:
                    existing["periods"].append(period)
                if float(signal.score) > float(existing["signal"].score):
                    existing["signal"] = signal

        return sorted(
            candidates.values(),
            key=lambda item: float(item["signal"].score),
            reverse=True,
        )

    def _recent_keys(self, keys: List[str], cooldown_minutes: int) -> Set[str]:
        if not keys:
            return set()
        cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
        db = SessionLocal()
        try:
            rows = (
                db.query(NotificationDeliveryLog.dedupe_key)
                .filter(NotificationDeliveryLog.channel == "dingtalk")
                .filter(NotificationDeliveryLog.event_type == self.EVENT_TYPE)
                .filter(NotificationDeliveryLog.dedupe_key.in_(keys))
                .filter(NotificationDeliveryLog.created_at >= cutoff)
                .distinct()
                .all()
            )
            return {row[0] for row in rows}
        finally:
            db.close()

    def _latest_delivery_contexts(
        self,
        keys: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """读取观察窗口内各标的最近一次成功通知，用于判断是否属于强化信号。"""
        if not keys:
            return {}
        cutoff = datetime.utcnow() - timedelta(
            hours=self.REINFORCEMENT_LOOKBACK_HOURS
        )
        db = SessionLocal()
        try:
            rows = (
                db.query(NotificationDeliveryLog)
                .filter(NotificationDeliveryLog.channel == "dingtalk")
                .filter(NotificationDeliveryLog.event_type == self.EVENT_TYPE)
                .filter(NotificationDeliveryLog.dedupe_key.in_(keys))
                .filter(NotificationDeliveryLog.created_at >= cutoff)
                .order_by(NotificationDeliveryLog.created_at.desc())
                .all()
            )
            latest: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                if row.dedupe_key in latest:
                    continue
                latest[row.dedupe_key] = {
                    "created_at": row.created_at,
                    "context_payload": dict(row.context_payload or {}),
                }
            return latest
        finally:
            db.close()

    @classmethod
    def _is_reinforced_signal(
        cls,
        signal: MomentumSignal,
        previous_signal: Dict[str, Any],
    ) -> bool:
        if not previous_signal:
            return False
        score_delta = float(signal.score) - float(previous_signal.get("score") or 0)
        breakout_delta = (
            float(signal.breakout_percent)
            - float(previous_signal.get("breakout_percent") or 0)
        )
        volume_5m_reinforced = float(signal.volume_ratio_5m) >= (
            float(previous_signal.get("volume_ratio_5m") or 0)
            * cls.REINFORCEMENT_VOLUME_MULTIPLIER
        )
        volume_15m_reinforced = float(signal.volume_ratio_15m) >= (
            float(previous_signal.get("volume_ratio_15m") or 0)
            * cls.REINFORCEMENT_VOLUME_MULTIPLIER
        )
        return (
            score_delta >= cls.REINFORCEMENT_SCORE_DELTA
            or breakout_delta >= cls.REINFORCEMENT_BREAKOUT_DELTA
            or volume_5m_reinforced
            or volume_15m_reinforced
        )

    @classmethod
    def _prepare_delivery_candidates(
        cls,
        candidates: List[Dict[str, Any]],
        previous_deliveries: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """标记首次/强化信号，并抑制冷却后但没有继续增强的重复信号。"""
        prepared = []
        now = datetime.utcnow()
        for candidate in candidates:
            signal: MomentumSignal = candidate["signal"]
            previous = previous_deliveries.get(signal.symbol)
            if previous is None:
                candidate["notification_kind"] = "initial"
                prepared.append(candidate)
                continue

            previous_context = previous.get("context_payload") or {}
            previous_signal = dict(previous_context.get("signal") or {})
            if not cls._is_reinforced_signal(signal, previous_signal):
                continue

            previous_created_at = previous.get("created_at")
            elapsed_minutes = None
            if isinstance(previous_created_at, datetime):
                elapsed_minutes = max(
                    0,
                    int((now - previous_created_at).total_seconds() // 60),
                )
            candidate["notification_kind"] = "reinforced"
            candidate["previous_signal"] = previous_signal
            candidate["elapsed_minutes"] = elapsed_minutes
            prepared.append(candidate)
        return prepared

    def _record_deliveries(
        self,
        candidates: List[Dict[str, Any]],
        preset_key: str,
    ) -> None:
        if not candidates:
            return
        db = SessionLocal()
        try:
            db.add_all(
                [
                    NotificationDeliveryLog(
                        channel="dingtalk",
                        event_type=self.EVENT_TYPE,
                        dedupe_key=item["signal"].symbol,
                        context_payload=self._build_delivery_context(
                            item,
                            preset_key,
                        ),
                    )
                    for item in candidates
                ]
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _build_delivery_context(
        candidate: Dict[str, Any],
        preset_key: str,
    ) -> Dict[str, Any]:
        signal: MomentumSignal = candidate["signal"]
        news_items: List[MarketNews] = candidate.get("news_items") or []
        analysis = dict(candidate.get("analysis") or {})
        llm_used = analysis.get("llm_payload") is not None
        analysis.pop("llm_payload", None)
        return {
            "preset": preset_key,
            "notification_kind": candidate.get("notification_kind", "initial"),
            "periods": candidate.get("periods") or [],
            "signal": signal.model_dump(mode="json"),
            "news_archive_ids": [
                item.id for item in news_items if item.id is not None
            ],
            "news": [
                {
                    "id": item.id,
                    "title": item.title,
                    "source": item.source,
                    "url": item.url,
                    "published_at": item.published_at.isoformat(),
                }
                for item in news_items[:6]
            ],
            "analysis": analysis,
            "llm_used": llm_used,
        }

    @staticmethod
    def _to_anomaly_payload(candidate: Dict[str, Any]) -> Dict[str, Any]:
        signal: MomentumSignal = candidate["signal"]
        return {
            "symbol": signal.symbol,
            "event_type": "momentum_breakout",
            "anomaly_score": float(signal.score) / 100,
            "anomaly_level": "high" if signal.score >= 75 else "medium",
            "last_price": signal.last_price,
            "price_change_percent_24h": signal.price_change_percent_24h,
            "quote_volume_24h": signal.quote_volume_24h,
            "trigger_reasons": [
                signal.reason,
                f"周期：{' + '.join(candidate.get('periods') or [])}",
                (
                    f"5m量比 {signal.volume_ratio_5m:.2f}x，"
                    f"15m量比 {signal.volume_ratio_15m:.2f}x"
                ),
            ],
        }

    async def _enrich_with_news(
        self,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        concurrency = max(
            1,
            int(os.getenv("MARKET_INSIGHT_NEWS_ANALYSIS_CONCURRENCY", "2")),
        )
        semaphore = asyncio.Semaphore(concurrency)

        async def enrich(candidate: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                signal: MomentumSignal = candidate["signal"]
                try:
                    news_items = await news_archive_service.ensure_symbol_news(
                        signal.symbol,
                        limit=6,
                        hours=72,
                    )
                    analysis = await news_analysis_service.analyze_anomaly(
                        self._to_anomaly_payload(candidate),
                        news_items,
                    )
                    candidate["news_items"] = news_items
                    candidate["analysis"] = analysis
                except Exception:
                    logger.exception(
                        "market-insight-notifier: news analysis failed symbol=%s",
                        signal.symbol,
                    )
                    candidate["news_items"] = []
                    candidate["analysis"] = None
                return candidate

        return list(await asyncio.gather(*(enrich(item) for item in candidates)))

    @staticmethod
    def _format_price(value: float) -> str:
        if value >= 1000:
            return f"{value:,.2f}"
        if value >= 1:
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return f"{value:.8f}".rstrip("0").rstrip(".")

    @staticmethod
    def _short_text(value: Any, limit: int = 90) -> str:
        normalized = " ".join(str(value or "").split())
        return normalized if len(normalized) <= limit else normalized[:limit] + "…"

    @classmethod
    def _build_message(
        cls,
        candidates: List[Dict[str, Any]],
        keyword: str = "TradeHelper",
        preset_label: str = "均衡",
    ) -> str:
        display_candidates = candidates[:4]
        normalized_keyword = " ".join(str(keyword or "").split()) or "TradeHelper"
        reinforced_count = sum(
            item.get("notification_kind") == "reinforced"
            for item in candidates
        )
        initial_count = len(candidates) - reinforced_count
        if reinforced_count == len(candidates):
            title = "强化信号触发"
            summary = f"检测到 {reinforced_count} 个放量突破强化信号"
        elif initial_count == len(candidates):
            title = "首次突破信号"
            summary = f"检测到 {initial_count} 个首次放量有效突破信号"
        else:
            title = "市场洞察"
            summary = f"首次突破 {initial_count} 个｜强化信号 {reinforced_count} 个"
        lines = [
            f"【{normalized_keyword} · {title}】",
            f"{summary}｜{preset_label}预设",
            "",
        ]
        for index, item in enumerate(display_candidates, start=1):
            signal: MomentumSignal = item["signal"]
            symbol = signal.symbol.removesuffix("USDT") + "/USDT"
            periods = " + ".join(item["periods"])
            notification_kind = item.get("notification_kind", "initial")
            signal_marker = "🔁 强化" if notification_kind == "reinforced" else "🆕 首次"
            elapsed_minutes = item.get("elapsed_minutes")
            elapsed_text = (
                f"（距上次 {elapsed_minutes} 分钟）"
                if notification_kind == "reinforced" and elapsed_minutes is not None
                else ""
            )
            lines.extend(
                [
                    f"{index}. {signal_marker}{elapsed_text}｜{symbol} · {periods}",
                    (
                        f"现价 {cls._format_price(signal.last_price)}｜"
                        f"评分 {signal.score:.1f}"
                    ),
                    (
                        f"5m {signal.change_5m:+.2f}% / {signal.volume_ratio_5m:.2f}x｜"
                        f"15m {signal.change_15m:+.2f}% / {signal.volume_ratio_15m:.2f}x"
                    ),
                    (
                        f"突破压力位 {signal.breakout_percent:+.2f}%"
                        f"（有效阈值 {signal.breakout_threshold:.2f}%）"
                    ),
                ]
            )
            previous_signal = item.get("previous_signal") or {}
            if notification_kind == "reinforced" and previous_signal:
                lines.extend(
                    [
                        (
                            "强化变化："
                            f"评分 {float(previous_signal.get('score') or 0):.1f} → {signal.score:.1f}｜"
                            f"突破 {float(previous_signal.get('breakout_percent') or 0):+.2f}% → "
                            f"{signal.breakout_percent:+.2f}%"
                        ),
                        (
                            "量比变化："
                            f"5m {float(previous_signal.get('volume_ratio_5m') or 0):.2f}x → "
                            f"{signal.volume_ratio_5m:.2f}x｜"
                            f"15m {float(previous_signal.get('volume_ratio_15m') or 0):.2f}x → "
                            f"{signal.volume_ratio_15m:.2f}x"
                        ),
                        "风险提示：信号已进入加速阶段，谨慎追价，优先观察回踩承接。",
                    ]
                )
            analysis = item.get("analysis") or {}
            news_items: List[MarketNews] = item.get("news_items") or []
            if analysis:
                analysis_mode = (
                    "LLM分析"
                    if analysis.get("llm_payload") is not None
                    else "规则分析"
                )
                lines.append(
                    (
                        f"信息面 {analysis.get('credibility_label', '待核实')} "
                        f"{float(analysis.get('credibility_score') or 0):.0f}分｜"
                        f"{analysis_mode}｜"
                        f"{cls._short_text(analysis.get('source_summary'), 55)}"
                    )
                )
                lines.append(
                    f"关联摘要：{cls._short_text(analysis.get('evidence_summary'))}"
                )
                lines.append(
                    f"建议：{cls._short_text(analysis.get('trade_recommendation'))}"
                )
            if news_items:
                first_news = news_items[0]
                lines.append(
                    f"相关新闻：{cls._short_text(first_news.title, 70)}（{first_news.source}）"
                )
                if first_news.url:
                    lines.append(first_news.url)
            elif analysis:
                lines.append("相关新闻：新闻库及补抓来源暂未命中")
            lines.append("")
        if len(candidates) > len(display_candidates):
            lines.append(f"另有 {len(candidates) - len(display_candidates)} 个信号，请打开市场洞察查看。")
        beijing_now = datetime.now(timezone(timedelta(hours=8)))
        lines.extend(
            [
                f"扫描时间：{beijing_now:%Y-%m-%d %H:%M:%S} UTC+8",
                "提示：仅作监控与决策参考，不构成交易建议。",
            ]
        )
        return "\n".join(lines)

    async def scan_once(self) -> List[str]:
        async with self._scan_lock:
            config = self._load_config()
            if config is None:
                self._last_bollinger_slot = None
                return []
            jobs = []
            if config.notify_market_breakout:
                jobs.append(self._scan_breakout(config))
            if config.notify_bollinger_breakout:
                jobs.append(self._scan_bollinger(config))
            else:
                self._last_bollinger_slot = None
            if config.notify_rsi_divergence:
                jobs.append(self._scan_rsi(config))
            # 各类提醒独立执行，某一行情源或通知失败不阻断其他类型。
            results = await asyncio.gather(*jobs, return_exceptions=True)
            sent = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error("市场提醒扫描失败", exc_info=(type(result), result, result.__traceback__))
                else:
                    sent.extend(result)
            return sent

    async def _scan_breakout(self, config: MarketNotificationConfig) -> List[str]:
        radar = await market_insight_service.get_momentum_radar(
            **config.radar_params
        )
        candidates = self._collect_candidates(radar, config.min_score)
        recent_keys = self._recent_keys(
            [item["signal"].symbol for item in candidates],
            config.cooldown_minutes,
        )
        pending = [
            item for item in candidates if item["signal"].symbol not in recent_keys
        ]
        if not pending:
            return []

        previous_deliveries = self._latest_delivery_contexts(
            [item["signal"].symbol for item in pending]
        )
        pending = self._prepare_delivery_candidates(
            pending,
            previous_deliveries,
        )
        if not pending:
            return []

        if config.news_analysis_enabled:
            pending = await self._enrich_with_news(pending)

        await dingtalk_notification_service.send_text(
            webhook_url=config.webhook_url,
            secret=config.secret,
            content=self._build_message(
                pending,
                config.keyword,
                config.preset_label,
            ),
        )
        sent_keys = [item["signal"].symbol for item in pending]
        self._record_deliveries(pending, config.preset_key)
        logger.info(
            "market-insight-notifier: sent DingTalk notification symbols=%s",
            ",".join(sent_keys),
        )
        return sent_keys

    @staticmethod
    def _bollinger_key(signal: BollingerSignal) -> str:
        return f"{signal.symbol}:{signal.direction}"

    def _recent_bollinger_keys(self, signals: List[BollingerSignal]) -> Set[str]:
        if not signals:
            return set()
        db = SessionLocal()
        try:
            rows = (
                db.query(NotificationDeliveryLog.dedupe_key)
                .filter(NotificationDeliveryLog.channel == "dingtalk")
                .filter(NotificationDeliveryLog.event_type == self.BOLLINGER_EVENT_TYPE)
                .filter(NotificationDeliveryLog.dedupe_key.in_([self._bollinger_key(item) for item in signals]))
                .filter(NotificationDeliveryLog.created_at >= datetime.utcnow() - timedelta(minutes=self.BOLLINGER_COOLDOWN_MINUTES))
                .distinct().all()
            )
            return {row[0] for row in rows}
        finally:
            db.close()

    def _record_bollinger_deliveries(self, signals: List[BollingerSignal]) -> None:
        db = SessionLocal()
        try:
            db.add_all([
                NotificationDeliveryLog(
                    channel="dingtalk", event_type=self.BOLLINGER_EVENT_TYPE,
                    dedupe_key=self._bollinger_key(signal),
                    context_payload={"signal": signal.model_dump(mode="json"), "period": BOLL_PERIOD, "multiplier": BOLL_MULTIPLIER},
                ) for signal in signals
            ])
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @classmethod
    def _build_bollinger_message(cls, signals: List[BollingerSignal], keyword: str) -> str:
        keyword = " ".join(str(keyword or "").split()) or "TradeHelper"
        beijing = timezone(timedelta(hours=8))
        lines = [
            f"【{keyword} · BOLL三周期轨外提醒】",
            f"24H成交额 ≥ 1亿USDT｜BOLL({BOLL_PERIOD},{BOLL_MULTIPLIER})｜每分钟检查",
            "",
        ]
        for signal in signals:
            direction = "全部高于上轨" if signal.direction == "above_upper" else "全部低于下轨"
            lines.extend([
                f"{signal.symbol.removesuffix('USDT')}/USDT · {direction}",
                f"24H成交额：{signal.quote_volume_24h / 100_000_000:.2f} 亿USDT",
            ])
            for band in signal.bands:
                closed_at = datetime.fromtimestamp(band.closed_at / 1000, beijing)
                lines.append(
                    f"{band.interval} 收盘 {cls._format_price(band.close)}｜"
                    f"上轨 {cls._format_price(band.upper)}｜下轨 {cls._format_price(band.lower)}"
                    f"（{closed_at:%m-%d %H:%M} UTC+8）"
                )
            lines.append("")
        lines.append("按各周期最新已收盘K线判断；同币同方向冷却60分钟。")
        return "\n".join(lines)

    async def _scan_bollinger(self, config: MarketNotificationConfig) -> List[str]:
        slot = int(time.time() * 1000) // BOLL_SCAN_INTERVAL_MS
        if slot == self._last_bollinger_slot:
            return []
        radar = await bollinger_service.scan()
        recent = self._recent_bollinger_keys(radar.signals)
        pending = [signal for signal in radar.signals if self._bollinger_key(signal) not in recent]
        sent = []
        # 分批发送并只记录已送达批次，避免未展示的信号被标记成已提醒。
        for offset in range(0, len(pending), 4):
            batch = pending[offset:offset + 4]
            await dingtalk_notification_service.send_text(
                webhook_url=config.webhook_url, secret=config.secret,
                content=self._build_bollinger_message(batch, config.keyword),
            )
            self._record_bollinger_deliveries(batch)
            sent.extend(signal.symbol for signal in batch)
        # 行情失败时保留重试机会；成功后同一分钟只检查一次。
        if radar.failed_count == 0:
            self._last_bollinger_slot = slot
        return sent

    @staticmethod
    def _rsi_key(signal: RsiDivergenceSignal) -> str:
        # 不包含筛选档位：切换档位不能再次发送同一对拐点。
        return f"{signal.symbol}:{signal.direction}:{signal.previous.time}:{signal.current.time}"

    def _pending_rsi_signals(
        self, signals: List[RsiDivergenceSignal], config: MarketNotificationConfig, now_ms: int,
    ) -> List[RsiDivergenceSignal]:
        if config.rsi_notify_after is None:
            return []
        activated = config.rsi_notify_after.replace(tzinfo=timezone.utc).timestamp() * 1000
        fresh = [item for item in signals if max(activated, now_ms - HOUR_MS) < item.confirmed_at <= now_ms]
        if not fresh:
            return []
        db = SessionLocal()
        try:
            query = db.query(NotificationDeliveryLog).filter(
                NotificationDeliveryLog.channel == "dingtalk",
                NotificationDeliveryLog.event_type == self.RSI_EVENT_TYPE,
            )
            delivered = {row.dedupe_key for row in query.filter(
                NotificationDeliveryLog.dedupe_key.in_([self._rsi_key(item) for item in fresh])
            ).all()}
            cutoff = datetime.fromtimestamp(now_ms / 1000, timezone.utc).replace(tzinfo=None) - timedelta(
                minutes=config.rsi_cooldown_minutes,
            )
            cooling = {tuple(row.dedupe_key.split(":")[:2]) for row in query.filter(
                NotificationDeliveryLog.created_at > cutoff,
            ).all()}
        finally:
            db.close()
        pending = []
        for item in sorted(fresh, key=lambda item: item.confirmed_at, reverse=True):
            pair = (item.symbol, item.direction)
            if self._rsi_key(item) in delivered or pair in cooling:
                continue
            pending.append(item)
            cooling.add(pair)
        return pending

    def _record_rsi_deliveries(
        self, signals: List[RsiDivergenceSignal], config: MarketNotificationConfig,
    ) -> None:
        db = SessionLocal()
        try:
            db.add_all([NotificationDeliveryLog(
                channel="dingtalk", event_type=self.RSI_EVENT_TYPE, dedupe_key=self._rsi_key(item),
                context_payload={"signal": item.model_dump(mode="json"), "preset": config.rsi_preset},
            ) for item in signals])
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _build_rsi_message(signals: List[RsiDivergenceSignal], config: MarketNotificationConfig) -> str:
        keyword = " ".join(str(config.keyword or "TradeHelper").split())
        label = get_rsi_rules(config.rsi_preset).preset_label
        lines = [f"【{keyword} · 1小时RSI背离 · {label}】", f"新确认 {len(signals)} 个信号（UTC+8）", ""]
        for item in signals:
            changed = abs(item.current.price - item.previous.price) / item.previous.price * 100
            confirmed = datetime.fromtimestamp(item.confirmed_at / 1000, timezone(timedelta(hours=8)))
            lines.append(
                f"{item.symbol.removesuffix('USDT')}/USDT {item.label}｜价格{'新低' if item.direction == 'bullish' else '新高'} {changed:.2f}%｜"
                f"RSI {item.previous.rsi:.2f}→{item.current.rsi:.2f}｜确认 {confirmed:%m-%d %H:%M}"
            )
        lines.extend(["", "价格与RSI拐点允许错开1根，均已完成右侧5根小时K线收盘确认；同一背离只通知一次。",
                      f"同币同方向新背离冷却 {config.rsi_cooldown_minutes} 分钟；详情见市场洞察。"])
        return "\n".join(lines)

    async def _scan_rsi(self, config: MarketNotificationConfig) -> List[str]:
        radar = await rsi_divergence_service.scan(preset=config.rsi_preset)
        # 扫描期间可能被用户关闭或调整强度，发送前重新核对持久化设置。
        current = self._load_config()
        if not current or not current.notify_rsi_divergence or (
            current.rsi_preset != config.rsi_preset or current.rsi_notify_after != config.rsi_notify_after
        ):
            return []
        pending = self._pending_rsi_signals(radar.signals, current, int(time.time() * 1000))
        if not pending:
            return []
        # 同轮合并发送，失败不写发送记录，下次扫描可重试。
        await dingtalk_notification_service.send_text(
            webhook_url=current.webhook_url, secret=current.secret,
            content=self._build_rsi_message(pending, current),
        )
        self._record_rsi_deliveries(pending, current)
        return [item.symbol for item in pending]

    async def poller(self) -> None:
        self._running = True
        logger.info(
            "market-insight-notifier: poller started interval=%s",
            self.interval,
        )
        try:
            while self._running:
                started_at = time.monotonic()
                try:
                    await self.scan_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("market-insight-notifier: scan failed")
                elapsed = time.monotonic() - started_at
                await asyncio.sleep(max(1, self.interval - elapsed))
        finally:
            self._running = False

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._running = True
        self._task = asyncio.get_running_loop().create_task(self.poller())

    def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()


market_insight_notification_service = MarketInsightNotificationService()
