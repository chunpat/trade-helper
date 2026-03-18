import asyncio

import pytest

from app.services.history_backfill_service import (
    BINANCE_MAX_INTERVAL_MS,
    fetch_income_range,
    fetch_trade_range,
)


class StubTradeAdapter:
    def __init__(self):
        self.calls = []

    async def fetch_user_trades(self, symbol=None, limit=1000, start_time=None, end_time=None):
        self.calls.append((symbol, start_time, end_time, limit))
        return [
            {
                'id': f'{symbol}-{start_time}',
                'orderId': f'{symbol}-{start_time}',
                'time': start_time,
                'qty': '1',
            }
        ]


class StubIncomeAdapter:
    def __init__(self):
        self.calls = []

    async def fetch_income_history(self, limit=1000, start_time=None, end_time=None, symbol=None, income_type=None):
        self.calls.append((start_time, end_time, limit, symbol, income_type))
        return [
            {
                'tranId': f'{start_time}',
                'time': start_time,
            }
        ]


class FailingTradeAdapter:
    async def fetch_user_trades(self, symbol=None, limit=1000, start_time=None, end_time=None):
        return None


def test_fetch_trade_range_splits_over_seven_days():
    adapter = StubTradeAdapter()
    start_ms = 0
    end_ms = 30 * 24 * 60 * 60 * 1000

    rows = asyncio.run(fetch_trade_range(adapter, 'BTCUSDT', start_ms, end_ms))

    assert len(adapter.calls) > 1
    assert rows
    assert all((end - start) <= BINANCE_MAX_INTERVAL_MS for _, start, end, _ in adapter.calls)


def test_fetch_income_range_splits_over_seven_days():
    adapter = StubIncomeAdapter()
    start_ms = 0
    end_ms = 30 * 24 * 60 * 60 * 1000

    rows = asyncio.run(fetch_income_range(adapter, start_ms, end_ms))

    assert len(adapter.calls) > 1
    assert rows
    assert all((end - start) <= BINANCE_MAX_INTERVAL_MS for start, end, _, _, _ in adapter.calls)


def test_fetch_trade_range_raises_on_failed_request():
    with pytest.raises(RuntimeError):
        asyncio.run(fetch_trade_range(FailingTradeAdapter(), 'BTCUSDT', 0, BINANCE_MAX_INTERVAL_MS))