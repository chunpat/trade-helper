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
from app.schemas.market_insight import MomentumRadarResponse, MomentumSignal
from app.services.dingtalk_notification_service import dingtalk_notification_service
from app.services.market_insight_service import market_insight_service

logger = logging.getLogger(__name__)


@dataclass
class MarketNotificationConfig:
    webhook_url: str
    secret: Optional[str]
    min_score: float
    cooldown_minutes: int


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
            return MarketNotificationConfig(
                webhook_url=config.webhook_url,
                secret=config.secret,
                min_score=float(config.market_min_score or 0),
                cooldown_minutes=max(int(config.market_cooldown_minutes or 60), 5),
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

    def _record_deliveries(self, keys: List[str]) -> None:
        if not keys:
            return
        db = SessionLocal()
        try:
            db.add_all(
                [
                    NotificationDeliveryLog(
                        channel="dingtalk",
                        event_type=self.EVENT_TYPE,
                        dedupe_key=key,
                    )
                    for key in keys
                ]
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _format_price(value: float) -> str:
        if value >= 1000:
            return f"{value:,.2f}"
        if value >= 1:
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return f"{value:.8f}".rstrip("0").rstrip(".")

    @classmethod
    def _build_message(cls, candidates: List[Dict[str, Any]]) -> str:
        display_candidates = candidates[:6]
        lines = [
            "【TradeHelper 市场洞察】",
            f"检测到 {len(candidates)} 个放量有效突破信号",
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
                    "",
                ]
            )
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

        radar = await market_insight_service.get_momentum_radar()
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

        await dingtalk_notification_service.send_text(
            webhook_url=config.webhook_url,
            secret=config.secret,
            content=self._build_message(pending),
        )
        sent_keys = [item["signal"].symbol for item in pending]
        self._record_deliveries(sent_keys)
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
