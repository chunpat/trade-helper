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


def test_okx_fetch_positions_normalizes_contract_quantity(monkeypatch):
    adapter = OkxAdapter('key', 'secret', 'passphrase')

    async def fake_request_raw(method, path, **kwargs):
        del method, path, kwargs
        return {
            'status_code': 200,
            'body': '{}',
            'payload': {
                'code': '0',
                'data': [
                    {
                        'instId': 'TRUMP-USDT-SWAP',
                        'posSide': 'long',
                        'pos': '20198',
                        'avgPx': '3.281',
                        'markPx': '3.269',
                        'upl': '-24.2376',
                        'lever': '10',
                        'liqPx': '2.98',
                    }
                ],
            },
        }

    async def fake_contract_values():
        return {'TRUMP-USDT-SWAP': 0.1}

    monkeypatch.setattr(adapter, '_request_raw', fake_request_raw)
    monkeypatch.setattr(adapter, '_get_swap_contract_values', fake_contract_values)

    rows = asyncio.run(adapter.fetch_positions())

    assert rows == [
        {
            'symbol': 'TRUMPUSDT',
            'positionSide': 'LONG',
            'positionAmt': '2019.8000000000002',
            'entryPrice': '3.281',
            'markPrice': '3.269',
            'unRealizedProfit': '-24.2376',
            'leverage': '10',
            'liquidationPrice': '2.98',
            'contractValue': '0.1',
        }
    ]


def test_okx_normalize_order_history_rows_uses_contract_value(monkeypatch):
    adapter = OkxAdapter('key', 'secret', 'passphrase')

    async def fake_contract_values():
        return {'TRUMP-USDT-SWAP': 0.1}

    monkeypatch.setattr(adapter, '_get_swap_contract_values', fake_contract_values)

    rows = asyncio.run(adapter._normalize_order_history_rows([
        {
            'instId': 'TRUMP-USDT-SWAP',
            'ordId': '12345',
            'tradeId': '98765',
            'side': 'buy',
            'posSide': 'long',
            'fillSz': '20198',
            'avgPx': '3.281',
            'fee': '-1.25',
            'pnl': '-24.2376',
            'fillTime': '1710000000000',
            'feeCcy': 'USDT',
            'lever': '10',
        }
    ]))

    assert rows == [
        {
            'id': '98765',
            'tradeId': '98765',
            'orderId': '12345',
            'symbol': 'TRUMPUSDT',
            'side': 'BUY',
            'positionSide': 'LONG',
            'price': '3.281',
            'qty': '2019.8000000000002',
            'quoteQty': '6626.9638',
            'commission': '1.25',
            'commissionAsset': 'USDT',
            'realizedPnl': '-24.2376',
            'leverage': '10',
            'contractValue': '0.1',
            'time': 1710000000000,
        }
    ]