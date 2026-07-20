from types import SimpleNamespace

import pytest

from app.schemas.market_insight import MomentumRadarResponse, MomentumSignal
from app.services.market_insight_notification_service import (
    MarketInsightNotificationService,
    MarketNotificationConfig,
)


def _signal(symbol: str, score: float = 80) -> MomentumSignal:
    return MomentumSignal(
        symbol=symbol,
        last_price=1.2345,
        change_5m=0.8,
        change_15m=1.5,
        volume_ratio_5m=2.1,
        volume_ratio_15m=1.8,
        quote_volume_24h=10_000_000,
        price_change_percent_24h=3.2,
        score=score,
        reason="放量突破48H压力位",
        breakout_percent=0.35,
        breakout_threshold=0.12,
        breakout_confirmed=True,
    )


def test_collect_candidates_merges_periods_and_applies_min_score():
    shared = _signal("AAAUSDT", 82)
    radar = MomentumRadarResponse(
        five_minute=[shared, _signal("LOWUSDT", 50)],
        fifteen_minute=[shared],
        scanned_count=2,
    )

    candidates = MarketInsightNotificationService._collect_candidates(radar, 60)

    assert len(candidates) == 1
    assert candidates[0]["signal"].symbol == "AAAUSDT"
    assert candidates[0]["periods"] == ["5分钟", "15分钟"]


def test_build_message_contains_signal_details():
    message = MarketInsightNotificationService._build_message(
        [{"signal": _signal("AAAUSDT"), "periods": ["5分钟", "15分钟"]}]
    )

    assert "AAA/USDT" in message
    assert "评分 80.0" in message
    assert "突破压力位 +0.35%" in message
    assert "UTC+8" in message


@pytest.mark.asyncio
async def test_scan_once_sends_only_non_cooled_symbols(monkeypatch):
    service = MarketInsightNotificationService(interval=60)
    config = MarketNotificationConfig(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test",
        secret=None,
        min_score=60,
        cooldown_minutes=60,
    )
    radar = MomentumRadarResponse(
        five_minute=[_signal("AAAUSDT"), _signal("BBBUSDT")],
        scanned_count=2,
    )
    sent = {}
    recorded = []

    monkeypatch.setattr(service, "_load_config", lambda: config)
    monkeypatch.setattr(service, "_recent_keys", lambda keys, cooldown: {"AAAUSDT"})
    monkeypatch.setattr(service, "_record_deliveries", lambda keys: recorded.extend(keys))

    async def fake_radar():
        return radar

    async def fake_send_text(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(
        "app.services.market_insight_notification_service.market_insight_service.get_momentum_radar",
        fake_radar,
    )
    monkeypatch.setattr(
        "app.services.market_insight_notification_service.dingtalk_notification_service.send_text",
        fake_send_text,
    )

    result = await service.scan_once()

    assert result == ["BBBUSDT"]
    assert recorded == ["BBBUSDT"]
    assert "BBB/USDT" in sent["content"]
    assert "AAA/USDT" not in sent["content"]


@pytest.mark.asyncio
async def test_scan_once_skips_radar_when_notification_disabled(monkeypatch):
    service = MarketInsightNotificationService(interval=60)
    called = False
    monkeypatch.setattr(service, "_load_config", lambda: None)

    async def fake_radar():
        nonlocal called
        called = True
        return SimpleNamespace(five_minute=[], fifteen_minute=[])

    monkeypatch.setattr(
        "app.services.market_insight_notification_service.market_insight_service.get_momentum_radar",
        fake_radar,
    )

    assert await service.scan_once() == []
    assert called is False
