from sqlalchemy import Boolean, Column, Float, Index, Integer, JSON, String, Text

from .base import Base, BaseMixin


class NotificationChannelConfig(Base, BaseMixin):
    __tablename__ = "notification_channel_configs"

    channel = Column(String(32), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False)
    webhook_url = Column(Text, nullable=True)
    secret = Column(String(255), nullable=True)
    keyword = Column(String(64), nullable=False, default="TradeHelper")
    notify_market_breakout = Column(Boolean, nullable=False, default=True)
    notify_risk_alert = Column(Boolean, nullable=False, default=True)
    market_alert_preset = Column(String(32), nullable=False, default="balanced")
    market_news_analysis_enabled = Column(Boolean, nullable=False, default=True)
    market_min_score = Column(Float, nullable=False, default=60.0)
    market_cooldown_minutes = Column(Integer, nullable=False, default=60)


class NotificationDeliveryLog(Base, BaseMixin):
    """通知发送记录，用于跨进程重启后的冷却去重。"""

    __tablename__ = "notification_delivery_logs"
    __table_args__ = (
        Index(
            "ix_notification_delivery_dedupe",
            "channel",
            "event_type",
            "dedupe_key",
            "created_at",
        ),
    )

    channel = Column(String(32), nullable=False)
    event_type = Column(String(64), nullable=False)
    dedupe_key = Column(String(255), nullable=False)
    context_payload = Column(JSON)
