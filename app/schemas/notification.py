from typing import Optional

from pydantic import BaseModel, Field


class DingTalkConfigUpdate(BaseModel):
    enabled: bool = False
    webhook_url: Optional[str] = Field(None, max_length=2000)
    secret: Optional[str] = Field(None, max_length=255)
    notify_market_breakout: bool = True
    notify_risk_alert: bool = True


class DingTalkConfigRead(BaseModel):
    enabled: bool = False
    webhook_configured: bool = False
    secret_configured: bool = False
    notify_market_breakout: bool = True
    notify_risk_alert: bool = True


class NotificationTestResult(BaseModel):
    success: bool
    message: str
