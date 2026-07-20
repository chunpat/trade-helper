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
from app.schemas.market_insight import MarketNews, MomentumRadarResponse, MomentumSignal
from app.services.dingtalk_notification_service import dingtalk_notification_service
from app.services.market_alert_presets import get_market_alert_preset
from app.services.market_insight_service import market_insight_service
from app.services.news_analysis_service import news_analysis_service
from app.services.news_archive_service import news_archive_service

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


class MarketInsightNotificationService:
    EVENT_TYPE = "market_breakout"

    def __init__(self, interval: Optional[int] = None):
        self.interval = interval or int(
            os.getenv("MARKET_INSIGHT_NOTIFY_SCAN_INTERVAL", "60")
        )
        self._task = None
        self._running = False

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
                or not config.notify_market_breakout
                or not config.webhook_url
            ):
                return None
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
        lines = [
            f"【{normalized_keyword} · 市场洞察】",
            f"检测到 {len(candidates)} 个放量有效突破信号｜{preset_label}预设",
            "",
        ]
        for index, item in enumerate(display_candidates, start=1):
            signal: MomentumSignal = item["signal"]
            symbol = signal.symbol.removesuffix("USDT") + "/USDT"
            periods = " + ".join(item["periods"])
            lines.extend(
                [
                    f"{index}. {symbol} · {periods}",
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
        config = self._load_config()
        if config is None:
            return []

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
