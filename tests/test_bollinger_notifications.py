from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import market_insight, notifications
from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.notification import NotificationChannelConfig, NotificationDeliveryLog
from app.schemas.bollinger import BollingerBandSnapshot, BollingerRadarResponse, BollingerSignal
from app.services import market_insight_notification_service as notifier_module
from app.services.market_insight_notification_service import MarketInsightNotificationService


def signal(symbol="BTCUSDT", direction="above_upper"):
    return BollingerSignal(symbol=symbol, direction=direction, quote_volume_24h=100_000_000,
        bands=[BollingerBandSnapshot(interval=interval, close=120 if direction == "above_upper" else 80,
            middle=100, upper=110, lower=90, closed_at=1_790_000_000_000) for interval in ("4h", "1h", "15m")])


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    NotificationChannelConfig.__table__.create(engine)
    NotificationDeliveryLog.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(notifier_module, "SessionLocal", factory)
    with factory() as db:
        db.add(NotificationChannelConfig(channel="dingtalk", enabled=True,
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test",
            keyword="行情提醒", notify_market_breakout=False, notify_bollinger_breakout=True))
        db.commit()
    yield factory
    engine.dispose()


def mock_scan(monkeypatch, signals, failed_count=0):
    calls = []

    async def scan():
        calls.append("scan")
        return BollingerRadarResponse(signals=signals, scanned_count=len(signals), failed_count=failed_count,
                                      timestamp=datetime.now(timezone.utc))

    monkeypatch.setattr(notifier_module.bollinger_service, "scan", scan)
    return calls


@pytest.mark.asyncio
async def test_boll_checks_every_minute_and_dedupes_across_restart(database, monkeypatch):
    clock = [int(datetime.now(timezone.utc).timestamp()) // 900 * 900 + 10]
    monkeypatch.setattr(notifier_module.time, "time", lambda: clock[0])
    calls = mock_scan(monkeypatch, [signal()])
    sent = []

    async def send(**kwargs):
        sent.append(kwargs["content"])

    monkeypatch.setattr(notifier_module.dingtalk_notification_service, "send_text", send)
    service = MarketInsightNotificationService()
    assert await service.scan_once() == ["BTCUSDT"]
    assert await service.scan_once() == []
    assert len(calls) == 1
    clock[0] += 60
    assert await service.scan_once() == []
    assert len(calls) == 2  # 同一根15分钟K线期间也要再次检测。
    assert await MarketInsightNotificationService().scan_once() == []
    assert len(sent) == 1
    assert "行情提醒" in sent[0] and "1.00 亿USDT" in sent[0]
    assert "BOLL(24,2)" in sent[0] and "每分钟检查" in sent[0]
    assert all(f"{interval} 收盘" in sent[0] for interval in ("4h", "1h", "15m"))
    with database() as db:
        row = db.query(NotificationDeliveryLog).one()
        assert row.event_type == "bollinger_breakout"
        assert row.dedupe_key == "BTCUSDT:above_upper"
        assert row.context_payload["period"] == 24
        assert row.context_payload["multiplier"] == 2
        assert len(row.context_payload["signal"]["bands"]) == 3


@pytest.mark.asyncio
async def test_cooldown_is_direction_specific_and_expires(database, monkeypatch):
    mock_scan(monkeypatch, [signal(), signal(direction="below_lower")])
    with database() as db:
        db.add(NotificationDeliveryLog(channel="dingtalk", event_type="bollinger_breakout", dedupe_key="BTCUSDT:above_upper"))
        db.commit()

    async def send(**kwargs):
        pass

    monkeypatch.setattr(notifier_module.dingtalk_notification_service, "send_text", send)
    assert await MarketInsightNotificationService().scan_once() == ["BTCUSDT"]
    with database() as db:
        db.query(NotificationDeliveryLog).update({"created_at": datetime.utcnow() - timedelta(minutes=61)})
        db.commit()
    assert await MarketInsightNotificationService().scan_once() == ["BTCUSDT", "BTCUSDT"]


@pytest.mark.asyncio
async def test_failed_batch_is_retried_without_recording_unsent_signals(database, monkeypatch):
    mock_scan(monkeypatch, [signal(f"COIN{i}USDT") for i in range(5)])
    sent = []
    fail = [True]

    async def send(**kwargs):
        if len(sent) == 1 and fail[0]:
            fail[0] = False
            raise RuntimeError("模拟发送失败")
        sent.append(kwargs["content"])

    monkeypatch.setattr(notifier_module.dingtalk_notification_service, "send_text", send)
    service = MarketInsightNotificationService()
    await service.scan_once()
    with database() as db:
        assert db.query(NotificationDeliveryLog).count() == 4
    assert await service.scan_once() == ["COIN4USDT"]
    with database() as db:
        assert db.query(NotificationDeliveryLog).count() == 5
    assert len(sent) == 2
    assert "COIN4/USDT" in sent[-1] and "COIN0/USDT" not in sent[-1]


@pytest.mark.asyncio
async def test_breakout_error_does_not_block_boll_and_partial_scan_retries(database, monkeypatch):
    calls = mock_scan(monkeypatch, [signal()], failed_count=1)
    with database() as db:
        db.query(NotificationChannelConfig).update({"notify_market_breakout": True})
        db.commit()

    async def fail(**kwargs):
        raise RuntimeError("模拟突破失败")

    async def send(**kwargs):
        pass

    monkeypatch.setattr(notifier_module.market_insight_service, "get_momentum_radar", fail)
    monkeypatch.setattr(notifier_module.dingtalk_notification_service, "send_text", send)
    service = MarketInsightNotificationService()
    assert await service.scan_once() == ["BTCUSDT"]
    assert await service.scan_once() == []
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_disabling_notification_skips_scanning(database, monkeypatch):
    calls = mock_scan(monkeypatch, [signal()])
    with database() as db:
        db.query(NotificationChannelConfig).update({"notify_bollinger_breakout": False})
        db.commit()
    assert await MarketInsightNotificationService().scan_once() == []
    assert calls == []


def test_config_roundtrip_preserves_new_switch_for_old_clients(database):
    app = FastAPI()
    app.include_router(notifications.router)
    app.dependency_overrides[get_current_admin] = lambda: object()

    def get_test_db():
        with database() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    client = TestClient(app)
    assert client.get("/notifications/dingtalk").json()["notify_bollinger_breakout"] is True
    result = client.put("/notifications/dingtalk", json={"enabled": True})
    assert result.status_code == 200
    assert result.json()["notify_bollinger_breakout"] is True
    result = client.put("/notifications/dingtalk", json={"enabled": True, "notify_bollinger_breakout": False})
    assert result.json()["notify_bollinger_breakout"] is False
    assert "webhook_url" not in result.json()


def test_radar_api_serializes_and_reports_failure(monkeypatch):
    app = FastAPI()
    app.include_router(market_insight.router)
    mock_scan(monkeypatch, [signal()])
    client = TestClient(app)
    result = client.get("/market-insight/bollinger-radar")
    assert result.status_code == 200
    assert result.json()["min_quote_volume"] == 100_000_000
    assert result.json()["period"] == 24
    assert result.json()["stddev_multiplier"] == 2
    assert result.json()["signals"][0]["direction"] == "above_upper"

    async def fail():
        raise ValueError("行情失败")

    monkeypatch.setattr(market_insight.bollinger_service, "scan", fail)
    assert client.get("/market-insight/bollinger-radar").status_code == 502
