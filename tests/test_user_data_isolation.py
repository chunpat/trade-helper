from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import auth, dashboard, market, notifications, polymarket, risk_control
from app.core import deps, ownership
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.base import Base
from app.models.polymarket_copy import PolymarketCopyStrategy
from app.models.risk_control import (
    Account,
    AccountSnapshot,
    DailyTradeReview,
    Position,
    RiskAlert,
    RiskConfig,
    RiskLevelEnum,
    TickerHistory,
    TransactionHistory,
    User,
)
from app.services import ws_broadcast


@pytest.fixture()
def isolated_app(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(ownership, "SessionLocal", factory)
    monkeypatch.setattr(polymarket, "SessionLocal", factory)
    monkeypatch.setattr(ws_broadcast, "SessionLocal", factory)

    def database():
        with factory() as db:
            yield db

    app = FastAPI()
    for module in (auth, risk_control, dashboard, market, notifications, polymarket):
        app.include_router(module.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[deps.get_db] = database
    with factory() as db:
        users = [
            User(
                username=name,
                password_hash=hash_password("secret123"),
                is_admin=(name == "admin"),
                is_active=True,
            )
            for name in ("admin", "alice", "bob")
        ]
        db.add_all(users)
        db.flush()
        for user in users[:2]:
            account = Account(
                user_id=user.id,
                exchange="binance",
                name=user.username,
                api_key=user.username + "-key",
                api_secret="private",
                total_equity=user.id * 100,
            )
            db.add(account)
            db.flush()
            db.add_all(
                [
                    Position(
                        account_id=account.id,
                        symbol="BTCUSDT",
                        size=1,
                        entry_price=10,
                        current_price=12,
                        leverage=1,
                        risk_level=RiskLevelEnum.LOW,
                    ),
                    RiskAlert(
                        account_id=account.id,
                        alert_type="test",
                        risk_level=RiskLevelEnum.LOW,
                        message=user.username,
                    ),
                    AccountSnapshot(
                        account_id=account.id,
                        total_equity=user.id * 100,
                        total_balance=50,
                        timestamp=datetime.utcnow(),
                    ),
                    TransactionHistory(
                        account_id=account.id,
                        symbol="BTCUSDT",
                        type="REALIZED_PNL",
                        realized_pnl=user.id * 10,
                        time=datetime.utcnow(),
                        transaction_id=user.username,
                    ),
                    TickerHistory(
                        account_id=account.id,
                        symbol="BTCUSDT",
                        price=12,
                        timestamp=datetime.utcnow(),
                        source="test",
                    ),
                    DailyTradeReview(
                        account_id=account.id,
                        review_date=datetime.utcnow().date(),
                        daily_summary=user.username,
                    ),
                    PolymarketCopyStrategy(
                        user_id=user.id,
                        strategy_name=user.username,
                        source_wallet="0x" + "1" * 40,
                    ),
                ]
            )
        db.commit()
    yield TestClient(app), factory, users, engine
    engine.dispose()


def headers(name):
    return {"Authorization": "Bearer " + create_access_token({"sub": name})[0]}


@pytest.mark.parametrize(
    "path",
    [
        "/risk-control/accounts/",
        "/risk-control/positions/",
        "/risk-control/alerts/",
        "/risk-control/history/transactions",
        "/market/ticker-history",
        "/polymarket/strategies",
    ],
)
def test_lists_only_return_owned_data(isolated_app, path):
    client, _, _, _ = isolated_app
    assert client.get("/api/v1" + path).status_code == 401
    for name, expected in [("admin", 1), ("alice", 2), ("bob", None)]:
        response = client.get("/api/v1" + path, headers=headers(name))
        assert response.status_code == 200, response.text
        rows = response.json()
        assert len(rows) == (1 if expected else 0)
        if rows:
            assert rows[0].get("account_id", rows[0]["id"]) == expected


def test_registration_and_dashboard_are_isolated(isolated_app):
    client, _, _, _ = isolated_app
    response = client.post(
        "/api/v1/auth/register", json={"username": "new-user", "password": "secret123"}
    )
    assert response.status_code == 200
    assert response.json()["is_admin"] is False
    login = client.post(
        "/api/v1/auth/token", json={"username": "new-user", "password": "secret123"}
    ).json()
    new_headers = {"Authorization": "Bearer " + login["access_token"]}
    assert (
        client.get("/api/v1/risk-control/accounts/", headers=new_headers).json() == []
    )
    assert (
        client.get("/api/v1/risk-control/positions/", headers=new_headers).json() == []
    )
    for name, equity, pnl, count in [
        ("admin", "$100.00", 10, 1),
        ("alice", "$200.00", 20, 1),
        ("bob", "$0.00", 0, 0),
    ]:
        response = client.get("/api/v1/dashboard/summary", headers=headers(name))
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total_position_value"] == equity
        assert data["daily_pnl"] == pnl
        assert data["active_alerts"] == count
        assert data["active_accounts"] == count
    assert client.get("/api/v1/dashboard/summary").status_code == 401


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("put", "/risk-control/accounts/1", {"name": "stolen"}),
        ("delete", "/risk-control/accounts/1", None),
        ("patch", "/risk-control/positions/1", {"current_price": 99}),
        ("put", "/risk-control/alerts/1/resolve", {"is_resolved": True}),
        ("get", "/risk-control/accounts/1/connectivity", None),
        ("get", "/risk-control/accounts/1/positions/test", None),
        ("get", "/risk-control/accounts/1/risk-summary", None),
        ("post", "/risk-control/accounts/1/positions/sync", None),
        ("post", "/risk-control/accounts/1/sync-history/start", None),
        ("get", "/risk-control/accounts/1/sync-history/status", None),
        ("get", "/polymarket/strategies/1", None),
        ("post", "/polymarket/strategies/1/start", None),
        ("post", "/polymarket/strategies/1/stop", None),
        ("get", "/polymarket/strategies/1/runs", None),
    ],
)
def test_foreign_ids_cannot_read_modify_or_trigger_jobs(
    isolated_app, method, path, payload
):
    client, _, _, _ = isolated_app
    response = client.request(
        method, "/api/v1" + path, json=payload, headers=headers("alice")
    )
    assert response.status_code == 404, response.text


def test_new_accounts_are_owned_and_cannot_be_reassigned(isolated_app):
    client, factory, users, _ = isolated_app
    response = client.post(
        "/api/v1/risk-control/accounts/",
        headers=headers("bob"),
        json={
            "exchange": "binance",
            "name": "bob account",
            "api_key": "bob-key",
            "api_secret": "secret",
            "user_id": users[0].id,
        },
    )
    assert response.status_code == 200, response.text
    account_id = response.json()["id"]
    with factory() as db:
        assert db.get(Account, account_id).user_id == users[2].id
    for name in ("admin", "alice"):
        assert account_id not in [
            r["id"]
            for r in client.get(
                "/api/v1/risk-control/accounts/", headers=headers(name)
            ).json()
        ]


def test_foreign_account_write_and_aggregate_filters(isolated_app):
    _, factory, users, _ = isolated_app
    with ownership.scope_session(factory(), users[1]) as db:
        assert db.query(func.sum(Account.total_equity)).scalar() == 200
        assert db.query(func.sum(TransactionHistory.realized_pnl)).scalar() == 20
        db.add(
            RiskAlert(
                account_id=1,
                alert_type="bad",
                risk_level=RiskLevelEnum.LOW,
                message="bad",
            )
        )
        with pytest.raises(HTTPException) as exc:
            db.commit()
        assert exc.value.status_code == 404
        db.rollback()


def test_system_settings_are_admin_only(isolated_app):
    client, _, _, _ = isolated_app
    for path in ["/notifications/dingtalk"]:
        assert client.get("/api/v1" + path, headers=headers("alice")).status_code == 403


def test_migration_preserves_existing_owners_and_assigns_legacy_data(isolated_app):
    _, factory, users, engine = isolated_app
    with factory() as db:
        db.add(
            Account(name="legacy", exchange="binance", api_key="old", api_secret="old")
        )
        db.commit()
    ownership.migrate_ownership(engine)
    ownership.migrate_ownership(engine)
    with factory() as db:
        assert db.query(Account).filter_by(name="legacy").one().user_id == users[0].id
        assert db.query(Account).filter_by(name="alice").one().user_id == users[1].id


@pytest.mark.asyncio
async def test_websocket_broadcast_only_reaches_owner(isolated_app):
    class Socket:
        def __init__(self, name):
            self.token = create_access_token({"sub": name})[0]
            self.messages = []

        async def accept(self):
            pass

        async def receive_json(self):
            return {"type": "auth", "token": self.token}

        async def send_text(self, message):
            self.messages.append(message)

        async def close(self, code):
            pass

    manager = ws_broadcast.WebSocketManager()
    admin, alice, bob = [Socket(name) for name in ("admin", "alice", "bob")]
    for socket in (admin, alice, bob):
        assert await manager.connect(socket)
    await manager.broadcast(
        {"type": "position_update", "data": {"id": 1, "account_id": 1}}
    )
    assert len(admin.messages) == 1
    assert not alice.messages and not bob.messages
    await manager.broadcast(
        {"type": "position_update", "data": {"id": 2, "account_id": 2}}
    )
    assert len(alice.messages) == 1
    assert not bob.messages
    invalid = Socket("alice")
    invalid.token = "invalid"
    assert not await manager.connect(invalid)
    assert invalid not in manager.active_connections


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/alerts",
        "/dashboard/charts/position",
        "/dashboard/charts/equity",
        "/dashboard/charts/risk",
        "/risk-control/history/completed-trades",
        "/risk-control/history/completed-trades/review",
        "/risk-control/history/completed-trades/summary",
        "/risk-control/history/completed-trades/timeline",
        "/risk-control/history/open-trades",
        "/risk-control/history/transactions/summary",
        "/risk-control/history/transactions/timeline",
        "/risk-control/positions/analysis",
    ],
)
def test_empty_user_does_not_receive_aggregated_private_data(isolated_app, path):
    client, _, _, _ = isolated_app
    response = client.get("/api/v1" + path, headers=headers("bob"))
    assert response.status_code == 200, response.text
    assert "admin" not in response.text and "alice" not in response.text
    assert "BTCUSDT" not in response.text
    assert "private" not in response.text


def test_dashboard_related_alerts_and_user_strategy_creation(isolated_app):
    client, factory, users, _ = isolated_app
    response = client.get("/api/v1/dashboard/alerts", headers=headers("alice"))
    assert response.status_code == 200, response.text
    assert [alert["account"] for alert in response.json()] == ["alice"]
    response = client.post(
        "/api/v1/polymarket/strategies",
        headers=headers("bob"),
        json={
            "strategy_name": "bob strategy",
            "source_wallet": "0x" + "2" * 40,
        },
    )
    assert response.status_code == 200, response.text
    with factory() as db:
        assert (
            db.get(PolymarketCopyStrategy, response.json()["id"]).user_id == users[2].id
        )
    assert (
        len(client.get("/api/v1/polymarket/strategies", headers=headers("bob")).json())
        == 1
    )


def test_migration_upgrades_old_tables_without_granting_first_registrant_ownership():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, is_admin BOOLEAN, is_active BOOLEAN)"
            )
        )
        conn.execute(text("INSERT INTO users VALUES (1, 'ordinary', false, true)"))
        conn.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO accounts VALUES (1)"))
        conn.execute(
            text(
                "CREATE TABLE polymarket_copy_strategies (id INTEGER PRIMARY KEY, execution_account_id INTEGER)"
            )
        )
        conn.execute(text("INSERT INTO polymarket_copy_strategies VALUES (1, 1)"))
    ownership.migrate_ownership(engine)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT user_id FROM accounts")).scalar() is None
        conn.execute(text("INSERT INTO users VALUES (2, 'admin', true, true)"))
    ownership.migrate_ownership(engine)
    ownership.migrate_ownership(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT user_id FROM accounts")).scalar() == 2
        assert (
            conn.execute(
                text("SELECT user_id FROM polymarket_copy_strategies")
            ).scalar()
            == 2
        )
    engine.dispose()


def test_manual_sync_only_schedules_owned_accounts(isolated_app, monkeypatch):
    client, _, _, _ = isolated_app
    scheduled = []

    async def sync_account(account):
        scheduled.append(account.id)

    monkeypatch.setattr(
        risk_control,
        "get_position_sync_from_env",
        lambda: SimpleNamespace(_sync_account=sync_account),
    )
    assert (
        client.post(
            "/api/v1/risk-control/positions/sync", headers=headers("alice")
        ).status_code
        == 202
    )
    assert scheduled == [2]


def test_daily_review_and_risk_checks_reject_foreign_account(isolated_app):
    client, _, _, _ = isolated_app
    paths = [
        "/risk-control/history/daily-reviews?account_id=1&review_date=2026-01-01",
        "/risk-control/history/daily-reviews/recent?account_id=1",
    ]
    for path in paths:
        assert client.get("/api/v1" + path, headers=headers("alice")).status_code == 404
    response = client.post(
        "/api/v1/risk-control/check-position-risk",
        headers=headers("alice"),
        params={
            "account_id": 1,
            "symbol": "BTCUSDT",
            "size": 1,
            "leverage": 2,
        },
    )
    assert response.status_code == 404
