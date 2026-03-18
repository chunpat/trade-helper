import asyncio
from types import SimpleNamespace

from app.services.exchange.binance_adapter import BinanceAdapter, create_adapter_for_account
from app.services.exchange.okx_adapter import OkxAdapter


def test_create_adapter_for_account_returns_binance_adapter():
    account = SimpleNamespace(
        exchange='binance',
        api_key='key',
        api_secret='secret',
        api_passphrase=None,
        settings={},
    )

    adapter = create_adapter_for_account(account)

    assert isinstance(adapter, BinanceAdapter)


def test_create_adapter_for_account_returns_okx_adapter_when_passphrase_present():
    account = SimpleNamespace(
        exchange='okx',
        api_key='key',
        api_secret='secret',
        api_passphrase='passphrase',
        settings={},
    )

    adapter = create_adapter_for_account(account)

    assert isinstance(adapter, OkxAdapter)


def test_create_adapter_for_account_rejects_okx_without_passphrase():
    account = SimpleNamespace(
        exchange='okx',
        api_key='key',
        api_secret='secret',
        api_passphrase=None,
        settings={},
    )

    adapter = create_adapter_for_account(account)

    assert adapter is None


class _FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        del url, headers
        return self._responses.pop(0)


def test_okx_request_raw_retries_on_rate_limit(monkeypatch):
    adapter = OkxAdapter('key', 'secret', 'passphrase')
    responses = [
        _FakeResponse(429, {'code': '50011', 'msg': 'Too Many Requests'}),
        _FakeResponse(200, {'code': '0', 'data': []}),
    ]
    retry_delays = []

    monkeypatch.setattr(adapter, '_wait_for_request_slot', lambda: asyncio.sleep(0))

    async def fake_sleep(seconds):
        retry_delays.append(seconds)

    monkeypatch.setattr(adapter, '_sleep_before_retry', fake_sleep)
    monkeypatch.setattr(adapter, '_get_client', lambda timeout=20.0: _FakeClient(responses))

    result = asyncio.run(adapter._request_raw('GET', '/api/v5/account/bills-archive'))

    assert result['status_code'] == 200
    assert retry_delays == [1.0]