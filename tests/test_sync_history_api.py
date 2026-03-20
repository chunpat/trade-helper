import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[1] / 'app' / 'api' / 'v1' / 'risk_control.py'
SPEC = importlib.util.spec_from_file_location('risk_control_api_module_sync_history', MODULE_PATH)
risk_control_api = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(risk_control_api)
router = risk_control_api.router


class FakeQuery:
    def __init__(self, account):
        self.account = account

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.account


class FakeDB:
    def __init__(self, account):
        self.account = account
        self.commit_calls = 0

    def query(self, model):
        return FakeQuery(self.account)

    def add(self, obj):
        self.account = obj

    def commit(self):
        self.commit_calls += 1

    def refresh(self, obj):
        self.account = obj


def create_test_app(fake_db):
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[risk_control_api.get_current_user] = lambda: {'id': 1}
    app.dependency_overrides[risk_control_api.get_db] = lambda: fake_db
    return app


def reset_sync_history_state():
    risk_control_api.SYNC_HISTORY_JOBS.clear()
    risk_control_api.SYNC_HISTORY_TASKS.clear()


def test_sync_history_rejects_repeated_ninety_day_backfill(monkeypatch):
    reset_sync_history_state()
    account = SimpleNamespace(
        id=1,
        name='okx-main',
        exchange='okx',
        history_90d_backfilled_at=datetime(2026, 3, 17, 9, 0, 0),
    )
    fake_db = FakeDB(account)
    called = {'value': False}

    async def fake_backfill(*args, **kwargs):
        called['value'] = True
        return {'message': 'should not execute'}

    monkeypatch.setattr('app.services.history_backfill_service.backfill_account_history', fake_backfill)

    client = TestClient(create_test_app(fake_db))
    response = client.post('/api/v1/risk-control/accounts/1/sync-history', params={'days': 90})

    assert response.status_code == 409
    assert called['value'] is False
    assert '不能重复执行' in response.json()['detail']


def test_sync_history_marks_ninety_day_backfill_complete(monkeypatch):
    reset_sync_history_state()
    account = SimpleNamespace(
        id=1,
        name='okx-main',
        exchange='okx',
        history_90d_backfilled_at=None,
    )
    fake_db = FakeDB(account)

    async def fake_backfill(db, account_arg, days, include_snapshots):
        assert db is fake_db
        assert account_arg is account
        assert days == 90
        assert include_snapshots is True
        return {'account_id': 1, 'message': 'ok'}

    monkeypatch.setattr('app.services.history_backfill_service.backfill_account_history', fake_backfill)

    client = TestClient(create_test_app(fake_db))
    response = client.post('/api/v1/risk-control/accounts/1/sync-history', params={'days': 90})

    assert response.status_code == 200
    payload = response.json()
    assert payload['message'] == 'ok'
    assert payload['history_90d_backfill_locked'] is True
    assert payload['history_90d_backfilled_at'] is not None
    assert fake_db.commit_calls == 1
    assert account.history_90d_backfilled_at is not None


def test_start_sync_history_returns_queued_status(monkeypatch):
    reset_sync_history_state()
    account = SimpleNamespace(
        id=1,
        name='okx-main',
        exchange='okx',
        history_90d_backfilled_at=None,
    )
    fake_db = FakeDB(account)

    class DummyTask:
        def done(self):
            return False

    def fake_create_task(coro):
        coro.close()
        return DummyTask()

    monkeypatch.setattr(risk_control_api.asyncio, 'create_task', fake_create_task)

    client = TestClient(create_test_app(fake_db))
    response = client.post('/api/v1/risk-control/accounts/1/sync-history/start', params={'days': 90})

    assert response.status_code == 202
    payload = response.json()
    assert payload['status'] == 'queued'
    assert payload['account_id'] == 1
    assert payload['history_90d_backfill_locked'] is False


def test_get_sync_history_status_returns_running_job():
    reset_sync_history_state()
    account = SimpleNamespace(
        id=1,
        name='okx-main',
        exchange='okx',
        history_90d_backfilled_at=None,
    )
    fake_db = FakeDB(account)
    risk_control_api.SYNC_HISTORY_JOBS[1] = {
        'account_id': 1,
        'account_name': 'okx-main',
        'days': 90,
        'status': 'running',
        'message': '90天历史回补正在后台执行',
        'error': None,
        'started_at': '2026-03-20T10:00:00',
        'finished_at': None,
        'result': None,
        'history_90d_backfilled_at': None,
        'history_90d_backfill_locked': False,
    }

    client = TestClient(create_test_app(fake_db))
    response = client.get('/api/v1/risk-control/accounts/1/sync-history/status')

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'running'
    assert payload['account_id'] == 1
    assert payload['history_90d_backfill_locked'] is False