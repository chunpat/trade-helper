from datetime import datetime
from types import SimpleNamespace

import pytest

from app.schemas.market_insight import MarketNews, MomentumRadarResponse, MomentumSignal
from app.services.market_alert_presets import MARKET_ALERT_PRESETS
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


def test_market_alert_presets_increase_confirmation_thresholds():
    high_frequency = MARKET_ALERT_PRESETS["high_frequency"]
    balanced = MARKET_ALERT_PRESETS["balanced"]
    strict = MARKET_ALERT_PRESETS["strict"]

    assert (
        high_frequency.radar_params["volume_ratio_min"]
        < balanced.radar_params["volume_ratio_min"]
        < strict.radar_params["volume_ratio_min"]
    )
    assert high_frequency.min_score < balanced.min_score < strict.min_score
    assert (
        high_frequency.cooldown_minutes
        < balanced.cooldown_minutes
        < strict.cooldown_minutes
    )


def test_build_message_contains_signal_details():
    message = MarketInsightNotificationService._build_message(
        [{"signal": _signal("AAAUSDT"), "periods": ["5分钟", "15分钟"]}]
    )

    assert "AAA/USDT" in message
    assert "评分 80.0" in message
    assert "突破压力位 +0.35%" in message
    assert "UTC+8" in message


def test_build_message_contains_custom_dingtalk_keyword():
    message = MarketInsightNotificationService._build_message(
        [{"signal": _signal("AAAUSDT"), "periods": ["5分钟"]}],
        "行情提醒",
    )

    assert "行情提醒" in message


@pytest.mark.asyncio
async def test_scan_once_sends_only_non_cooled_symbols(monkeypatch):
    service = MarketInsightNotificationService(interval=60)
    config = MarketNotificationConfig(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test",
        secret=None,
        keyword="行情提醒",
        preset_key="high_frequency",
        preset_label="高频灵敏",
        radar_params=dict(MARKET_ALERT_PRESETS["high_frequency"].radar_params),
        min_score=60,
        cooldown_minutes=60,
        news_analysis_enabled=False,
    )
    radar = MomentumRadarResponse(
        five_minute=[_signal("AAAUSDT"), _signal("BBBUSDT")],
        scanned_count=2,
    )
    sent = {}
    recorded = []

    monkeypatch.setattr(service, "_load_config", lambda: config)
    monkeypatch.setattr(service, "_recent_keys", lambda keys, cooldown: {"AAAUSDT"})
    monkeypatch.setattr(
        service,
        "_record_deliveries",
        lambda candidates, preset: recorded.extend(
            item["signal"].symbol for item in candidates
        ),
    )

    async def fake_radar(**kwargs):
        assert kwargs["volume_ratio_min"] == 1.2
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
    assert "行情提醒" in sent["content"]
    assert "BBB/USDT" in sent["content"]
    assert "AAA/USDT" not in sent["content"]


@pytest.mark.asyncio
async def test_news_enrichment_uses_archive_and_llm_analysis(monkeypatch):
    service = MarketInsightNotificationService(interval=60)
    candidate = {"signal": _signal("AAAUSDT"), "periods": ["5分钟"]}
    news = MarketNews(
        id=12,
        title="AAA announces ecosystem update",
        source="Example News",
        source_domain="example.com",
        url="https://example.com/aaa",
        published_at=datetime.utcnow(),
        symbols=["AAA"],
    )

    async def fake_ensure_symbol_news(symbol, limit, hours):
        assert symbol == "AAAUSDT"
        assert hours == 72
        return [news]

    async def fake_analyze(anomaly, news_items):
        assert anomaly["event_type"] == "momentum_breakout"
        assert news_items == [news]
        return {
            "credibility_label": "可信",
            "credibility_score": 88,
            "evidence_summary": "新闻与放量时间接近。",
            "source_summary": "example.com",
            "trade_recommendation": "等待回踩确认。",
            "llm_payload": {"id": "llm-result"},
        }

    monkeypatch.setattr(
        "app.services.market_insight_notification_service.news_archive_service.ensure_symbol_news",
        fake_ensure_symbol_news,
    )
    monkeypatch.setattr(
        "app.services.market_insight_notification_service.news_analysis_service.analyze_anomaly",
        fake_analyze,
    )

    enriched = await service._enrich_with_news([candidate])
    context = service._build_delivery_context(enriched[0], "balanced")
    message = service._build_message(enriched, "行情提醒", "均衡")

    assert enriched[0]["news_items"] == [news]
    assert context["news_archive_ids"] == [12]
    assert context["llm_used"] is True
    assert "LLM分析" in message
    assert "AAA announces ecosystem update" in message


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
