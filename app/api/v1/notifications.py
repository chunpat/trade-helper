from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.notification import NotificationChannelConfig
from app.schemas.notification import DingTalkConfigRead, DingTalkConfigUpdate, NotificationTestResult
from app.services.dingtalk_notification_service import dingtalk_notification_service
from app.services.market_alert_presets import get_market_alert_preset


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _get_config(db: Session) -> NotificationChannelConfig | None:
    return db.query(NotificationChannelConfig).filter(
        NotificationChannelConfig.channel == "dingtalk"
    ).first()


def _serialize(config: NotificationChannelConfig | None) -> DingTalkConfigRead:
    preset_key = str(config.market_alert_preset or "balanced") if config else "balanced"
    preset = get_market_alert_preset(preset_key)
    return DingTalkConfigRead(
        enabled=bool(config.enabled) if config else False,
        webhook_configured=bool(config and config.webhook_url),
        secret_configured=bool(config and config.secret),
        keyword=str(config.keyword or "TradeHelper") if config else "TradeHelper",
        notify_market_breakout=bool(config.notify_market_breakout) if config else True,
        notify_risk_alert=bool(config.notify_risk_alert) if config else True,
        market_alert_preset=preset.key,
        market_news_analysis_enabled=(
            bool(config.market_news_analysis_enabled) if config else True
        ),
        market_min_score=preset.min_score,
        market_cooldown_minutes=preset.cooldown_minutes,
    )


@router.get("/dingtalk", response_model=DingTalkConfigRead)
def get_dingtalk_config(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return _serialize(_get_config(db))


@router.put("/dingtalk", response_model=DingTalkConfigRead)
def update_dingtalk_config(
    payload: DingTalkConfigUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    config = _get_config(db)
    if config is None:
        config = NotificationChannelConfig(channel="dingtalk")
        db.add(config)

    webhook_url = str(payload.webhook_url or "").strip()
    secret = str(payload.secret or "").strip()
    if webhook_url:
        try:
            config.webhook_url = dingtalk_notification_service.validate_webhook_url(webhook_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if secret:
        config.secret = secret

    if payload.enabled and not config.webhook_url:
        raise HTTPException(status_code=400, detail="启用钉钉通知前请先配置 Webhook")

    config.enabled = payload.enabled
    config.keyword = " ".join(str(payload.keyword or "").split()) or "TradeHelper"
    config.notify_market_breakout = payload.notify_market_breakout
    config.notify_risk_alert = payload.notify_risk_alert
    preset = get_market_alert_preset(payload.market_alert_preset)
    config.market_alert_preset = preset.key
    config.market_news_analysis_enabled = payload.market_news_analysis_enabled
    # 保留旧字段，便于已有部署和旧接口平滑升级。
    config.market_min_score = preset.min_score
    config.market_cooldown_minutes = preset.cooldown_minutes
    db.commit()
    db.refresh(config)
    return _serialize(config)


@router.post("/dingtalk/test", response_model=NotificationTestResult)
async def test_dingtalk_config(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    config = _get_config(db)
    if config is None or not config.webhook_url:
        raise HTTPException(status_code=400, detail="请先保存钉钉机器人 Webhook")
    try:
        beijing_now = datetime.now(timezone(timedelta(hours=8)))
        keyword = str(config.keyword or "TradeHelper")
        await dingtalk_notification_service.send_text(
            webhook_url=config.webhook_url,
            secret=config.secret,
            content=(
                f"【{keyword}】钉钉监控通知测试成功\n"
                f"时间：{beijing_now:%Y-%m-%d %H:%M:%S} UTC+8"
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"钉钉通知发送失败：{exc}") from exc
    return NotificationTestResult(success=True, message="测试通知发送成功")
