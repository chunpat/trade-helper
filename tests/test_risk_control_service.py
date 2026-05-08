import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.risk_control import Account, Position, RiskLevelEnum, TransactionHistory
from app.services.position_sync import PositionSyncService
from app.services.risk_control_service import RiskControlService


def test_calculate_unrealized_pnl_amount_for_long_position():
    amount = RiskControlService.calculate_unrealized_pnl_amount(
        entry_price=100.0,
        current_price=110.0,
        size=2.0,
        position_side='LONG',
    )

    assert amount == 20.0


def test_calculate_unrealized_pnl_amount_for_short_position():
    loss_amount = RiskControlService.calculate_unrealized_pnl_amount(
        entry_price=100.0,
        current_price=110.0,
        size=2.0,
        position_side='SHORT',
    )
    profit_amount = RiskControlService.calculate_unrealized_pnl_amount(
        entry_price=100.0,
        current_price=90.0,
        size=2.0,
        position_side='SHORT',
    )

    assert loss_amount == -20.0
    assert profit_amount == 20.0


def test_calculate_risk_level_respects_short_position_direction():
    service = RiskControlService(db=None)
    risk_config = SimpleNamespace(risk_ratio_threshold=0.05, max_position_value=1000.0)
    position = SimpleNamespace(
        current_price=110.0,
        entry_price=100.0,
        size=2.0,
        position_side='SHORT',
    )

    level = service.calculate_risk_level(position, risk_config)

    assert level == RiskLevelEnum.CRITICAL


def test_position_sync_normalizes_binance_both_side_using_position_amount():
    assert PositionSyncService.normalize_position_side('BOTH', 3.0) == 'LONG'
    assert PositionSyncService.normalize_position_side('BOTH', -3.0) == 'SHORT'
    assert PositionSyncService.normalize_position_side('BOTH', 0.0) == 'NET'


class StubRecentHistoryAdapter:
    def __init__(self):
        self.trade_calls = []

    async def fetch_income_history(self, limit=1000):
        return [
            {
                'tranId': 'income-1',
                'symbol': 'LABUSDT',
                'incomeType': 'REALIZED_PNL',
                'income': '-28.818',
                'asset': 'USDT',
                'time': 1778085667000,
            }
        ]

    async def fetch_user_trades(self, symbol=None, limit=1000, start_time=None, end_time=None):
        self.trade_calls.append((symbol, limit, start_time, end_time))
        if symbol != 'LABUSDT':
            return []
        return [
            {
                'id': '247293658',
                'orderId': '1975317213',
                'symbol': 'LABUSDT',
                'side': 'BUY',
                'positionSide': 'BOTH',
                'price': '4.2780',
                'qty': '15',
                'quoteQty': '64.17',
                'commission': '0.032085',
                'commissionAsset': 'USDT',
                'realizedPnl': '-28.818',
                'time': 1778085667375,
            },
            {
                'id': '247293659',
                'orderId': '1975317213',
                'symbol': 'LABUSDT',
                'side': 'BUY',
                'positionSide': 'BOTH',
                'price': '4.2781',
                'qty': '27',
                'quoteQty': '115.5087',
                'commission': '0.05775435',
                'commissionAsset': 'USDT',
                'realizedPnl': '-51.8751',
                'time': 1778085667375,
            },
        ]


def test_position_sync_history_updates_existing_trade_with_symbol_scoped_fetch():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    session = session_local()

    try:
        account = Account(
            exchange='binance',
            name='test',
            api_key='k',
            api_secret='s',
            is_active=True,
        )
        session.add(account)
        session.commit()
        session.refresh(account)

        session.add(Position(
            account_id=account.id,
            symbol='LABUSDT',
            size=1.0,
            entry_price=4.5,
            current_price=4.2,
            unrealized_pnl=-0.3,
            leverage=5.0,
            risk_level=RiskLevelEnum.LOW,
            position_side='SHORT',
            is_active=True,
        ))
        session.add(TransactionHistory(
            account_id=account.id,
            symbol='LABUSDT',
            type='TRADE',
            side='BUY',
            position_side='BOTH',
            price=4.2791,
            qty=77.0,
            quote_qty=329.4368,
            commission=0.16471839,
            commission_asset='USDT',
            realized_pnl=-147.9632,
            leverage=5.0,
            time=datetime.utcfromtimestamp(1778085667),
            order_id='1975317213',
            transaction_id='ORDER_1975317213',
        ))
        session.commit()

        service = PositionSyncService()
        adapter = StubRecentHistoryAdapter()

        asyncio.run(service._sync_history(account, adapter, session))

        row = session.query(TransactionHistory).filter(
            TransactionHistory.transaction_id == 'ORDER_1975317213'
        ).first()

        assert row is not None
        assert row.qty == 42.0
        assert row.quote_qty == 179.6787
        assert row.realized_pnl == -80.6931
        assert row.commission == pytest.approx(0.08983935)
        assert adapter.trade_calls and adapter.trade_calls[0][0] == 'LABUSDT'
        assert adapter.trade_calls[0][1] == 1000
        assert adapter.trade_calls[0][2] == 1778085607000
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()