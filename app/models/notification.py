from sqlalchemy import Boolean, Column, String, Text

from .base import Base, BaseMixin


class NotificationChannelConfig(Base, BaseMixin):
    __tablename__ = "notification_channel_configs"

    channel = Column(String(32), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False)
    webhook_url = Column(Text, nullable=True)
    secret = Column(String(255), nullable=True)
    notify_market_breakout = Column(Boolean, nullable=False, default=True)
    notify_risk_alert = Column(Boolean, nullable=False, default=True)
