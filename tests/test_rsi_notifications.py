from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import notifications
from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.notification import NotificationChannelConfig, NotificationDeliveryLog
from app.schemas.rsi_divergence import RsiDivergencePoint, RsiDivergenceRadar, RsiDivergenceSignal
from app.services import market_insight_notification_service as module
from app.services.market_insight_notification_service import MarketInsightNotificationService

HOUR = 3_600_000


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    NotificationChannelConfig.__table__.create(engine)
    NotificationDeliveryLog.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(module, "SessionLocal", factory)
    with factory() as db:
        db.add(NotificationChannelConfig(channel="dingtalk", enabled=True,
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test", keyword="行情提醒",
            notify_market_breakout=False, notify_bollinger_breakout=False, notify_rsi_divergence=True,
            rsi_preset="strict", rsi_cooldown_minutes=240,
            rsi_notify_after=datetime.utcnow() - timedelta(hours=2)))
        db.commit()
    yield factory
    engine.dispose()


def signal(symbol="BTCUSDT", direction="bearish", confirmed_at=None):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    confirmed_at = now - 60_000 if confirmed_at is None else confirmed_at
    bullish = direction == "bullish"
    return RsiDivergenceSignal(symbol=symbol, direction=direction, label="底背离" if bullish else "顶背离",
        previous=RsiDivergencePoint(time=confirmed_at - 18 * HOUR, price=100, rsi=20 if bullish else 80),
        current=RsiDivergencePoint(time=confirmed_at - 6 * HOUR, price=95 if bullish else 105, rsi=30 if bullish else 70),
        confirmed_at=confirmed_at, bars_between=12, last_close=100, last_rsi=50)


def mock_scan(monkeypatch, signals):
    calls = []

    async def scan(preset="strict"):
        calls.append(preset)
        return RsiDivergenceRadar(signals=signals, timestamp=datetime.now(timezone.utc))

    monkeypatch.setattr(module.rsi_divergence_service, "scan", scan)
    return calls


@pytest.mark.asyncio
async def test_rsi_only_merges_new_signals_and_dedupes_across_restart(database, monkeypatch):
    signals = [signal(), signal("ETHUSDT")]
    calls = mock_scan(monkeypatch, signals)
    sent = []

    async def send(**kwargs):
        sent.append(kwargs["content"])

    monkeypatch.setattr(module.dingtalk_notification_service, "send_text", send)
    assert set(await MarketInsightNotificationService().scan_once()) == {"BTCUSDT", "ETHUSDT"}
    assert await MarketInsightNotificationService().scan_once() == []
    assert len(sent) == 1 and calls == ["strict", "strict"]
    assert all(text in sent[0] for text in ("行情提醒", "严格", "BTC/USDT", "ETH/USDT", "确认", "240 分钟"))
    with database() as db:
        rows = db.query(NotificationDeliveryLog).all()
        assert len(rows) == 2
        assert all(item.event_type == "rsi_divergence" for item in rows)
        assert rows[0].context_payload["preset"] == "strict"
        # 即使冷却记录变旧，同一对拐点也不能再发。
        for row in rows:
            row.created_at = datetime.utcnow() - timedelta(days=2)
        db.commit()
    assert await MarketInsightNotificationService().scan_once() == []
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_failed_send_retries_without_marking_delivered(database, monkeypatch):
    mock_scan(monkeypatch, [signal()])
    attempts = []

    async def send(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RuntimeError("模拟失败")

    monkeypatch.setattr(module.dingtalk_notification_service, "send_text", send)
    service = MarketInsightNotificationService()
    assert await service.scan_once() == []
    with database() as db:
        assert db.query(NotificationDeliveryLog).count() == 0
    assert await service.scan_once() == ["BTCUSDT"]
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_cooldown_blocks_same_direction_but_allows_opposite(database, monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    old = signal(confirmed_at=now - 2 * HOUR)
    with database() as db:
        db.add(NotificationDeliveryLog(channel="dingtalk", event_type="rsi_divergence",
            dedupe_key=MarketInsightNotificationService._rsi_key(old), created_at=datetime.utcnow() - timedelta(hours=2)))
        db.commit()
    bearish, bullish = signal(), signal(direction="bullish")
    mock_scan(monkeypatch, [bearish, bullish])
    sent = []

    async def send(**kwargs):
        sent.append(kwargs["content"])

    monkeypatch.setattr(module.dingtalk_notification_service, "send_text", send)
    assert await MarketInsightNotificationService().scan_once() == ["BTCUSDT"]
    assert "底背离" in sent[0] and "顶背离" not in sent[0]
    with database() as db:
        db.query(NotificationDeliveryLog).update({"created_at": datetime.utcnow() - timedelta(hours=5)})
        db.commit()
    assert await MarketInsightNotificationService().scan_once() == ["BTCUSDT"]
    assert "顶背离" in sent[-1] and "底背离" not in sent[-1]


@pytest.mark.asyncio
async def test_only_fresh_post_activation_signals_send(database, monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    with database() as db:
        db.query(NotificationChannelConfig).update({"rsi_notify_after": datetime.utcnow() - timedelta(minutes=30)})
        db.commit()
    mock_scan(monkeypatch, [signal("OLDUSDT", confirmed_at=now - 2 * HOUR),
        signal("BEFOREUSDT", confirmed_at=now - 45 * 60_000),
        signal("FUTUREUSDT", confirmed_at=now + HOUR), signal("NEWUSDT")])
    sent = []

    async def send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(module.dingtalk_notification_service, "send_text", send)
    assert await MarketInsightNotificationService().scan_once() == ["NEWUSDT"]
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_disable_during_scan_prevents_send(database, monkeypatch):
    async def scan(preset):
        with database() as db:
            db.query(NotificationChannelConfig).update({"notify_rsi_divergence": False})
            db.commit()
        return RsiDivergenceRadar(signals=[signal()], timestamp=datetime.now(timezone.utc))

    async def send(**kwargs):
        pytest.fail("关闭通知后不应继续发送")

    monkeypatch.setattr(module.rsi_divergence_service, "scan", scan)
    monkeypatch.setattr(module.dingtalk_notification_service, "send_text", send)
    assert await MarketInsightNotificationService().scan_once() == []


def api_client(database, admin=True):
    app = FastAPI()
    app.include_router(notifications.router)

    def db_session():
        with database() as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    if admin:
        app.dependency_overrides[get_current_admin] = lambda: object()
    return TestClient(app)


@pytest.mark.parametrize("event", ["market_breakout", "bollinger_breakout", "rsi_divergence"])
def test_card_switch_changes_only_selected_event(database, event):
    client = api_client(database)
    before = client.get("/notifications/dingtalk").json()
    field = f"notify_{event}"
    response = client.patch(f"/notifications/dingtalk/events/{event}", json={"enabled": not before[field]})
    assert response.status_code == 200
    after = response.json()
    assert after[field] is not before[field]
    assert {key: value for key, value in after.items() if key != field} == {
        key: value for key, value in before.items() if key != field}
    assert "webhook_url" not in after and "secret" not in after


def test_rsi_switch_activation_and_strength_reset_history_cutoff(database):
    client = api_client(database)
    with database() as db:
        original = db.query(NotificationChannelConfig).one().rsi_notify_after
    client.patch("/notifications/dingtalk/events/rsi_divergence", json={"enabled": True})
    with database() as db:
        assert db.query(NotificationChannelConfig).one().rsi_notify_after == original
    client.patch("/notifications/dingtalk/events/rsi_divergence", json={"enabled": False})
    client.patch("/notifications/dingtalk/events/rsi_divergence", json={"enabled": True})
    with database() as db:
        activated = db.query(NotificationChannelConfig).one().rsi_notify_after
        assert activated > original
    result = client.put("/notifications/dingtalk", json={"enabled": True, "rsi_preset": "strong", "rsi_cooldown_minutes": 360})
    assert result.status_code == 200 and result.json()["rsi_preset"] == "strong"
    assert result.json()["notify_rsi_divergence"] is True
    with database() as db:
        changed = db.query(NotificationChannelConfig).one().rsi_notify_after
        assert changed >= activated
    # 旧客户端未携带RSI字段时应保留新设置，也不重置通知起点。
    result = client.put("/notifications/dingtalk", json={"enabled": True})
    assert result.json()["rsi_preset"] == "strong" and result.json()["rsi_cooldown_minutes"] == 360
    with database() as db:
        assert db.query(NotificationChannelConfig).one().rsi_notify_after == changed


def test_card_switch_requires_admin_and_enabled_channel(database):
    assert api_client(database, admin=False).patch(
        "/notifications/dingtalk/events/rsi_divergence", json={"enabled": True}).status_code in (401, 403)
    client = api_client(database)
    with database() as db:
        db.query(NotificationChannelConfig).update({"enabled": False})
        db.commit()
    assert client.patch("/notifications/dingtalk/events/rsi_divergence", json={"enabled": True}).status_code == 400
    assert client.patch("/notifications/dingtalk/events/rsi_divergence", json={"enabled": False}).status_code == 200
    assert client.patch("/notifications/dingtalk/events/unknown", json={"enabled": True}).status_code == 422


@pytest.mark.parametrize("payload", [{"rsi_preset": "unknown"}, {"rsi_cooldown_minutes": 59}, {"rsi_cooldown_minutes": 1441}])
def test_rsi_notification_settings_are_validated(database, payload):
    assert api_client(database).put("/notifications/dingtalk", json=payload).status_code == 422


def test_matching_price_time_does_not_change_existing_notification_identity():
    item = signal()
    original = MarketInsightNotificationService._rsi_key(item)
    item.previous.price_time = item.previous.time + HOUR
    item.current.price_time = item.current.time + HOUR
    item.confirmed_at += HOUR
    assert MarketInsightNotificationService._rsi_key(item) == original
