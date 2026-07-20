from typing import Literal, Optional

from pydantic import BaseModel, Field


class DingTalkConfigUpdate(BaseModel):
    enabled: bool = False
    webhook_url: Optional[str] = Field(None, max_length=2000)
    secret: Optional[str] = Field(None, max_length=255)
    keyword: str = Field("TradeHelper", max_length=64)
    notify_market_breakout: bool = True
    notify_risk_alert: bool = True
    market_alert_preset: Literal["high_frequency", "balanced", "strict"] = "balanced"
    market_news_analysis_enabled: bool = True
    market_min_score: float = Field(60.0, ge=0, le=100)
    market_cooldown_minutes: int = Field(60, ge=5, le=1440)


class DingTalkConfigRead(BaseModel):
    enabled: bool = False
    webhook_configured: bool = False
    secret_configured: bool = False
    keyword: str = "TradeHelper"
    notify_market_breakout: bool = True
    notify_risk_alert: bool = True
    market_alert_preset: Literal["high_frequency", "balanced", "strict"] = "balanced"
    market_news_analysis_enabled: bool = True
    market_min_score: float = 60.0
    market_cooldown_minutes: int = 60


class NotificationTestResult(BaseModel):
    success: bool
    message: str
