import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.risk_control import TransactionHistory
from app.services.history_backfill_service import (
    BINANCE_MAX_INTERVAL_MS,
    fetch_income_range,
    fetch_trade_range,
    upsert_trade_rows,
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


def test_upsert_trade_rows_persists_leverage():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    try:
        result = upsert_trade_rows(session, 1, [
            {
                'orderId': '123',
                'symbol': 'TRUMPUSDT',
                'side': 'BUY',
                'positionSide': 'LONG',
                'price': '3.281',
                'qty': '2019.8',
                'quoteQty': '6626.9638',
                'commission': '1.25',
                'commissionAsset': 'USDT',
                'realizedPnl': '-24.2376',
                'leverage': '10',
                'time': 1710000000000,
            }
        ])
        session.commit()

        row = session.query(TransactionHistory).filter(TransactionHistory.transaction_id == 'ORDER_123').first()

        assert result == {'inserted': 1, 'updated': 0}
        assert row is not None
        assert row.qty == 2019.8
        assert row.quote_qty == 6626.9638
        assert row.leverage == 10.0
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()