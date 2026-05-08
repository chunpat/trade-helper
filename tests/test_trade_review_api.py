from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import risk_control as risk_control_api
from app.models.base import Base
from app.models.risk_control import Account, AccountSnapshot, Position, RiskLevelEnum, TickerHistory, TransactionHistory


@pytest.fixture()
def review_client():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(risk_control_api.router, prefix='/api/v1')
    app.dependency_overrides[risk_control_api.get_current_user] = lambda: {'id': 1}
    app.dependency_overrides[risk_control_api.get_db] = override_get_db

    yield TestClient(app), TestingSessionLocal

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def seed_trade_review_history(session_factory):
    session = session_factory()
    account = Account(
        exchange='binance',
        name='Review Account',
        api_key='test-key',
        api_secret='test-secret',
        initial_balance=10000,
    )
    session.add(account)
    session.flush()

    session.add_all([
        TransactionHistory(
            account_id=account.id,
            symbol='',
            type='EVENT_CONTRACTS_ORDER',
            realized_pnl=-69,
            commission_asset='USDT',
            time=datetime(2026, 1, 1, 8, 0, 0),
            transaction_id='EVT_9001',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            type='TRADE',
            side='SELL',
            leverage=10,
            price=43000,
            qty=0.2,
            quote_qty=8600,
            commission=5,
            commission_asset='USDT',
            realized_pnl=120,
            time=datetime(2026, 1, 1, 10, 30, 0),
            order_id='1001',
            transaction_id='ORDER_1001',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            type='REALIZED_PNL',
            realized_pnl=120,
            time=datetime(2026, 1, 1, 10, 31, 0),
            transaction_id='PNL_1001',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            type='COMMISSION',
            realized_pnl=-5,
            commission_asset='USDT',
            time=datetime(2026, 1, 1, 10, 32, 0),
            transaction_id='COMM_1001',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            type='FUNDING_FEE',
            realized_pnl=8,
            commission_asset='USDT',
            time=datetime(2026, 1, 1, 12, 0, 0),
            transaction_id='FUND_1001',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            type='TRADE',
            side='BUY',
            leverage=5,
            price=2500,
            qty=1.2,
            quote_qty=3000,
            commission=4,
            commission_asset='USDT',
            realized_pnl=-40,
            time=datetime(2026, 1, 2, 9, 15, 0),
            order_id='1002',
            transaction_id='ORDER_1002',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            type='REALIZED_PNL',
            realized_pnl=-40,
            time=datetime(2026, 1, 2, 9, 16, 0),
            transaction_id='PNL_1002',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            type='COMMISSION',
            realized_pnl=-4,
            commission_asset='USDT',
            time=datetime(2026, 1, 2, 9, 17, 0),
            transaction_id='COMM_1002',
        ),
        TransactionHistory(
            account_id=account.id,
            type='TRANSFER',
            realized_pnl=200,
            time=datetime(2026, 1, 3, 8, 0, 0),
            transaction_id='T_2001',
        ),
    ])
    session.commit()
    session.close()
    return account.id


def test_transaction_history_supports_time_filters(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/transactions',
        params={
            'account_id': account_id,
            'start_time': '2026-01-02T00:00:00',
            'end_time': '2026-01-02T23:59:59',
            'limit': 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert all(item['time'].startswith('2026-01-02') for item in payload)


def test_transaction_review_summary_avoids_double_counting(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.get('/api/v1/risk-control/history/transactions/summary', params={'account_id': account_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total_count'] == 8
    assert payload['trade_count'] == 2
    assert payload['win_count'] == 1
    assert payload['loss_count'] == 1
    assert payload['win_rate'] == 50.0
    assert payload['gross_realized_pnl'] == 80.0
    assert payload['commission_cost'] == 9.0
    assert payload['funding_pnl'] == 8.0
    assert payload['transfer_amount'] == 200.0
    assert payload['net_trading_pnl'] == 79.0
    assert payload['average_trade_pnl'] == 40.0
    assert payload['profit_factor'] == 3.0


def test_transaction_review_summary_ignores_noise_events_by_default(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    raw_response = client.get(
        '/api/v1/risk-control/history/transactions',
        params={'account_id': account_id, 'limit': 20, 'record_scope': 'all'},
    )
    summary_response = client.get('/api/v1/risk-control/history/transactions/summary', params={'account_id': account_id})

    assert raw_response.status_code == 200
    assert summary_response.status_code == 200
    assert any(item['type'] == 'EVENT_CONTRACTS_ORDER' for item in raw_response.json())
    assert summary_response.json()['total_count'] == 8


def test_transaction_review_summary_for_trade_filter_uses_trade_records(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/transactions/summary',
        params={'account_id': account_id, 'type': 'TRADE'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['total_count'] == 2
    assert payload['trade_count'] == 2
    assert payload['gross_realized_pnl'] == 80.0
    assert payload['commission_cost'] == 9.0
    assert payload['funding_pnl'] == 0.0
    assert payload['net_trading_pnl'] == 71.0


def test_transaction_review_timeline_returns_bucketed_series(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/transactions/timeline',
        params={
            'account_id': account_id,
            'start_time': '2026-01-01T00:00:00',
            'end_time': '2026-01-03T23:59:59',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['xAxis'] == ['01-01', '01-02', '01-03']
    assert payload['series'][0]['name'] == '区间净值'
    assert payload['series'][1]['name'] == '累计净值'
    assert payload['series'][2]['name'] == '成交笔数'
    assert payload['series'][0]['data'] == [123.0, -44.0, 0.0]
    assert payload['series'][1]['data'] == [123.0, 79.0, 79.0]
    assert payload['series'][2]['data'] == [1.0, 1.0, 0.0]


def test_transaction_history_supports_trade_scope(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/transactions',
        params={
            'account_id': account_id,
            'record_scope': 'trades',
            'limit': 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert all(item['type'] == 'TRADE' for item in payload)
    assert payload[0]['leverage'] in {5.0, 10.0}
    assert payload[1]['leverage'] in {5.0, 10.0}


def test_transaction_history_supports_cashflow_scope(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/transactions',
        params={
            'account_id': account_id,
            'record_scope': 'cashflow',
            'limit': 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 6
    assert all(item['type'] != 'TRADE' for item in payload)
    assert all(item['type'] != 'EVENT_CONTRACTS_ORDER' for item in payload)


def test_daily_trade_review_returns_empty_state_when_missing(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/daily-reviews',
        params={
            'account_id': account_id,
            'review_date': '2026-01-02',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['account_id'] == account_id
    assert payload['review_date'] == '2026-01-02'
    assert payload['trade_tags'] == []
    assert payload['execution_score'] is None
    assert payload['error_analysis'] is None
    assert payload['daily_summary'] is None
    assert payload['exists'] is False


def test_daily_trade_review_upsert_normalizes_tags_and_text(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    save_response = client.put(
        '/api/v1/risk-control/history/daily-reviews',
        json={
            'account_id': account_id,
            'review_date': '2026-01-02',
            'trade_tags': [' 按计划执行 ', '', '冲动交易', '按计划执行', '冲动交易 '],
            'linked_orders': [
                {
                    'trade_id': 'review-trade-1',
                    'symbol': 'btcusdt',
                    'direction': 'long',
                    'trade_status': 'completed',
                    'position_side': 'LONG',
                    'open_time': '2026-01-02T08:00:00',
                    'close_time': '2026-01-02T09:00:00',
                    'net_pnl': 88.12,
                    'order_ids': ['ORDER_1', 'ORDER_2', 'ORDER_2'],
                },
                {
                    'trade_id': 'review-trade-1',
                    'symbol': 'BTCUSDT',
                    'direction': 'LONG',
                    'trade_status': 'completed',
                    'position_side': 'LONG',
                    'open_time': '2026-01-02T08:00:00',
                    'close_time': '2026-01-02T09:00:00',
                    'net_pnl': 88.12,
                    'order_ids': ['ORDER_1'],
                },
            ],
            'execution_score': 4,
            'error_analysis': ' 追单导致入场过早  ',
            'daily_summary': ' 方向判断没错，但出手还是太快。 '
        },
    )

    assert save_response.status_code == 200
    payload = save_response.json()
    assert payload['exists'] is True
    assert payload['trade_tags'] == ['按计划执行', '冲动交易']
    assert len(payload['linked_orders']) == 1
    assert payload['linked_orders'][0]['trade_id'] == 'review-trade-1'
    assert payload['linked_orders'][0]['symbol'] == 'BTCUSDT'
    assert payload['linked_orders'][0]['direction'] == 'LONG'
    assert payload['linked_orders'][0]['trade_status'] == 'completed'
    assert payload['linked_orders'][0]['order_ids'] == ['ORDER_1', 'ORDER_2']
    assert payload['execution_score'] == 4
    assert payload['error_analysis'] == '追单导致入场过早'
    assert payload['daily_summary'] == '方向判断没错，但出手还是太快。'
    assert payload['created_at'] is not None
    assert payload['updated_at'] is not None

    fetch_response = client.get(
        '/api/v1/risk-control/history/daily-reviews',
        params={
            'account_id': account_id,
            'review_date': '2026-01-02',
        },
    )

    assert fetch_response.status_code == 200
    fetched = fetch_response.json()
    assert fetched['id'] == payload['id']
    assert fetched['trade_tags'] == ['按计划执行', '冲动交易']
    assert fetched['linked_orders'][0]['order_ids'] == ['ORDER_1', 'ORDER_2']
    assert fetched['exists'] is True


def test_daily_trade_review_supports_open_trade_links(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    response = client.put(
        '/api/v1/risk-control/history/daily-reviews',
        json={
            'account_id': account_id,
            'review_date': '2026-01-03',
            'trade_tags': ['跟踪中'],
            'linked_orders': [
                {
                    'trade_id': 'open-trade-1',
                    'symbol': 'ETHUSDT',
                    'direction': 'LONG',
                    'trade_status': 'open',
                    'position_side': 'LONG',
                    'open_time': '2026-01-03T08:00:00',
                    'last_activity_time': '2026-01-03T11:30:00',
                    'net_pnl': 15.5,
                    'order_ids': ['OPEN_1'],
                }
            ],
            'execution_score': 3,
            'error_analysis': None,
            'daily_summary': '盘中跟踪未平仓单',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['linked_orders'][0]['trade_status'] == 'open'
    assert payload['linked_orders'][0]['close_time'] is None
    assert payload['linked_orders'][0]['last_activity_time'].startswith('2026-01-03T11:30:00')


def test_recent_daily_trade_reviews_return_latest_dates_first(review_client):
    client, session_factory = review_client
    account_id = seed_trade_review_history(session_factory)

    for review_date, score in [
        ('2026-01-01', 3),
        ('2026-01-03', 5),
        ('2026-01-02', 4),
    ]:
        response = client.put(
            '/api/v1/risk-control/history/daily-reviews',
            json={
                'account_id': account_id,
                'review_date': review_date,
                'trade_tags': ['按计划执行'],
                'execution_score': score,
                'error_analysis': None,
                'daily_summary': f'{review_date} summary',
            },
        )
        assert response.status_code == 200

    recent_response = client.get(
        '/api/v1/risk-control/history/daily-reviews/recent',
        params={
            'account_id': account_id,
            'limit': 2,
        },
    )

    assert recent_response.status_code == 200
    payload = recent_response.json()
    assert [item['review_date'] for item in payload] == ['2026-01-03', '2026-01-02']
    assert [item['execution_score'] for item in payload] == [5, 4]
    assert all('linked_orders' in item for item in payload)


def seed_completed_round_trip_history(session_factory):
    session = session_factory()
    account = Account(
        exchange='binance',
        name='Round Trip Account',
        api_key='round-trip-key',
        api_secret='round-trip-secret',
        initial_balance=20000,
    )
    session.add(account)
    session.flush()

    session.add_all([
        TransactionHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            type='TRADE',
            side='BUY',
            position_side='LONG',
            price=40000,
            qty=1.0,
            quote_qty=40000,
            commission=8,
            commission_asset='USDT',
            realized_pnl=0,
            time=datetime(2026, 1, 1, 9, 0, 0),
            order_id='LONG_OPEN_1',
            transaction_id='ORDER_LONG_OPEN_1',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            type='FUNDING_FEE',
            realized_pnl=-3,
            commission_asset='USDT',
            time=datetime(2026, 1, 1, 12, 0, 0),
            transaction_id='FUND_LONG_1',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            type='TRADE',
            side='SELL',
            position_side='LONG',
            price=42000,
            qty=1.0,
            quote_qty=42000,
            commission=8,
            commission_asset='USDT',
            realized_pnl=2000,
            time=datetime(2026, 1, 1, 18, 0, 0),
            order_id='LONG_CLOSE_1',
            transaction_id='ORDER_LONG_CLOSE_1',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            type='TRADE',
            side='SELL',
            position_side='SHORT',
            price=3000,
            qty=2.0,
            quote_qty=6000,
            commission=3,
            commission_asset='USDT',
            realized_pnl=0,
            time=datetime(2026, 1, 2, 10, 0, 0),
            order_id='SHORT_OPEN_1',
            transaction_id='ORDER_SHORT_OPEN_1',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            type='FUNDING_FEE',
            realized_pnl=1,
            commission_asset='USDT',
            time=datetime(2026, 1, 2, 16, 0, 0),
            transaction_id='FUND_SHORT_1',
        ),
        TransactionHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            type='TRADE',
            side='BUY',
            position_side='SHORT',
            price=2800,
            qty=2.0,
            quote_qty=5600,
            commission=3,
            commission_asset='USDT',
            realized_pnl=400,
            time=datetime(2026, 1, 2, 20, 0, 0),
            order_id='SHORT_CLOSE_1',
            transaction_id='ORDER_SHORT_CLOSE_1',
        ),
        TickerHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            price=41000,
            timestamp=datetime(2026, 1, 1, 10, 0, 0),
            source='test',
        ),
        TickerHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            price=42500,
            timestamp=datetime(2026, 1, 1, 11, 0, 0),
            source='test',
        ),
        TickerHistory(
            account_id=account.id,
            symbol='BTCUSDT',
            price=40500,
            timestamp=datetime(2026, 1, 1, 14, 0, 0),
            source='test',
        ),
        TickerHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            price=2950,
            timestamp=datetime(2026, 1, 2, 12, 0, 0),
            source='test',
        ),
        TickerHistory(
            account_id=account.id,
            symbol='ETHUSDT',
            price=2750,
            timestamp=datetime(2026, 1, 2, 18, 0, 0),
            source='test',
        ),
        AccountSnapshot(
            account_id=account.id,
            total_equity=20000,
            total_balance=18000,
            timestamp=datetime(2026, 1, 1, 8, 55, 0),
        ),
        AccountSnapshot(
            account_id=account.id,
            total_equity=20500,
            total_balance=18400,
            timestamp=datetime(2026, 1, 1, 10, 30, 0),
        ),
        AccountSnapshot(
            account_id=account.id,
            total_equity=22300,
            total_balance=20150,
            timestamp=datetime(2026, 1, 1, 13, 30, 0),
        ),
        AccountSnapshot(
            account_id=account.id,
            total_equity=21900,
            total_balance=19800,
            timestamp=datetime(2026, 1, 1, 17, 30, 0),
        ),
        AccountSnapshot(
            account_id=account.id,
            total_equity=22150,
            total_balance=20000,
            timestamp=datetime(2026, 1, 2, 9, 45, 0),
        ),
        AccountSnapshot(
            account_id=account.id,
            total_equity=22420,
            total_balance=20250,
            timestamp=datetime(2026, 1, 2, 12, 30, 0),
        ),
        AccountSnapshot(
            account_id=account.id,
            total_equity=22680,
            total_balance=20520,
            timestamp=datetime(2026, 1, 2, 19, 0, 0),
        ),
    ])
    session.commit()
    session.close()
    return account.id


def test_completed_trades_endpoint_returns_round_trips(review_client):
    client, session_factory = review_client
    account_id = seed_completed_round_trip_history(session_factory)

    response = client.get('/api/v1/risk-control/history/completed-trades', params={'account_id': account_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 2
    assert payload['items'][0]['symbol'] == 'ETHUSDT'
    assert payload['items'][0]['direction'] == 'SHORT'
    assert payload['items'][0]['position_side'] == 'SHORT'
    assert payload['items'][1]['symbol'] == 'BTCUSDT'
    assert payload['items'][1]['direction'] == 'LONG'
    assert payload['items'][1]['position_side'] == 'LONG'


def test_completed_trade_summary_includes_commission_and_funding(review_client):
    client, session_factory = review_client
    account_id = seed_completed_round_trip_history(session_factory)

    response = client.get('/api/v1/risk-control/history/completed-trades/summary', params={'account_id': account_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total_count'] == 2
    assert payload['win_count'] == 2
    assert payload['loss_count'] == 0
    assert payload['win_rate'] == 100.0
    assert payload['gross_realized_pnl'] == 2400.0
    assert payload['commission_cost'] == 22.0
    assert payload['funding_pnl'] == -2.0
    assert payload['net_pnl'] == 2376.0
    assert payload['average_net_pnl'] == 1188.0


def test_completed_trade_review_bundle_returns_summary_timeline_and_paginated_items(review_client):
    client, session_factory = review_client
    account_id = seed_completed_round_trip_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/completed-trades/review',
        params={
            'account_id': account_id,
            'skip': 0,
            'limit': 1,
            'start_time': '2026-01-01T00:00:00',
            'end_time': '2026-01-02T23:59:59',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 2
    assert len(payload['items']) == 1
    assert payload['items'][0]['symbol'] == 'ETHUSDT'
    assert payload['summary']['total_count'] == 2
    assert payload['summary']['net_pnl'] == 2376.0
    assert payload['timeline']['xAxis'][0] == '01-01 00:00'
    assert payload['timeline']['xAxis'][-1] == '01-02 23:00'
    assert payload['timeline']['series'][0]['data'][18] == 1981.0
    assert payload['timeline']['series'][0]['data'][44] == 395.0
    assert payload['timeline']['series'][1]['data'][-1] == 2376.0
    assert sum(payload['timeline']['series'][2]['data']) == 2.0


def test_completed_trade_detail_contains_legs_and_funding_items(review_client):
    client, session_factory = review_client
    account_id = seed_completed_round_trip_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/completed-trades',
        params={
            'account_id': account_id,
            'symbol': 'BTCUSDT',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 1
    item = payload['items'][0]
    assert item['entry_order_count'] == 1
    assert item['exit_order_count'] == 1
    assert item['funding_event_count'] == 1
    assert item['entry_orders'][0]['order_id'] == 'LONG_OPEN_1'
    assert item['exit_orders'][0]['order_id'] == 'LONG_CLOSE_1'
    assert item['funding_items'][0]['transaction_id'] == 'FUND_LONG_1'
    assert item['net_pnl'] == 1981.0


def test_completed_trade_detail_includes_holding_curve_metrics(review_client):
    client, session_factory = review_client
    account_id = seed_completed_round_trip_history(session_factory)

    response = client.get(
        '/api/v1/risk-control/history/completed-trades',
        params={
            'account_id': account_id,
            'symbol': 'BTCUSDT',
        },
    )

    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['price_sample_count'] == 3
    assert item['holding_curve_point_count'] == 6
    assert item['max_floating_profit'] == 2492.0
    assert item['max_drawdown'] == 2003.0
    assert item['holding_curve'][0]['event_type'] == 'entry'
    assert item['holding_curve'][-1]['event_type'] == 'exit'
    assert item['holding_curve'][-1]['net_pnl'] == 1981.0
    assert item['account_equity_point_count'] == 5
    assert item['account_equity_curve'][0]['total_equity'] == 20000.0
    assert item['account_equity_curve'][-1]['time'].startswith('2026-01-01T18:00:00')
    assert item['account_equity_curve'][-1]['total_equity'] == 21900.0


def test_open_trades_endpoint_returns_active_positions(review_client):
    client, session_factory = review_client
    account_id = seed_completed_round_trip_history(session_factory)

    session = session_factory()
    session.add_all([
        TransactionHistory(
            account_id=account_id,
            symbol='SOLUSDT',
            type='TRADE',
            side='BUY',
            position_side='LONG',
            price=120,
            qty=5,
            quote_qty=600,
            commission=1,
            commission_asset='USDT',
            realized_pnl=0,
            time=datetime(2026, 1, 3, 9, 0, 0),
            order_id='SOL_OPEN_1',
            transaction_id='ORDER_SOL_OPEN_1',
        ),
        TransactionHistory(
            account_id=account_id,
            symbol='SOLUSDT',
            type='FUNDING_FEE',
            realized_pnl=0.5,
            commission_asset='USDT',
            time=datetime(2026, 1, 3, 12, 0, 0),
            transaction_id='FUND_SOL_1',
        ),
        TickerHistory(
            account_id=account_id,
            symbol='SOLUSDT',
            price=126,
            timestamp=datetime(2026, 1, 3, 13, 0, 0),
            source='test',
        ),
        Position(
            account_id=account_id,
            symbol='SOLUSDT',
            size=5,
            entry_price=120,
            current_price=127,
            unrealized_pnl=35,
            leverage=10,
            risk_level=RiskLevelEnum.LOW,
            is_active=True,
            position_side='LONG',
        ),
    ])
    session.commit()
    session.close()

    response = client.get(
        '/api/v1/risk-control/history/open-trades',
        params={
            'account_id': account_id,
            'end_time': '2026-01-03T13:30:00',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 1
    item = payload['items'][0]
    assert item['symbol'] == 'SOLUSDT'
    assert item['direction'] == 'LONG'
    assert item['open_qty'] == 5.0
    assert item['leverage'] == 10.0
    assert item['latest_mark_price'] == 127.0
    assert item['unrealized_pnl'] == 35.0
    assert item['net_pnl'] == 34.5
    assert item['order_ids'] == ['SOL_OPEN_1']


def test_open_trades_exclude_campaigns_without_active_position(review_client):
    client, session_factory = review_client
    session = session_factory()

    account = Account(
        exchange='okx',
        name='Open Trade Filter Account',
        api_key='test-key',
        api_secret='test-secret',
        initial_balance=10000,
    )
    session.add(account)
    session.flush()
    account_id = account.id

    session.add_all([
        TransactionHistory(
            account_id=account_id,
            symbol='BTCUSDT',
            type='TRADE',
            side='BUY',
            position_side='LONG',
            price=100000,
            qty=1,
            quote_qty=100000,
            commission=1,
            commission_asset='USDT',
            realized_pnl=0,
            time=datetime(2026, 1, 3, 9, 0, 0),
            order_id='BTC_OPEN_1',
            transaction_id='ORDER_BTC_OPEN_1',
        ),
        TransactionHistory(
            account_id=account_id,
            symbol='SOLUSDT',
            type='TRADE',
            side='BUY',
            position_side='LONG',
            price=120,
            qty=5,
            quote_qty=600,
            commission=1,
            commission_asset='USDT',
            realized_pnl=0,
            time=datetime(2026, 1, 3, 10, 0, 0),
            order_id='SOL_OPEN_2',
            transaction_id='ORDER_SOL_OPEN_2',
        ),
        Position(
            account_id=account_id,
            symbol='SOLUSDT',
            size=5,
            entry_price=120,
            current_price=127,
            unrealized_pnl=35,
            leverage=10,
            risk_level=RiskLevelEnum.LOW,
            is_active=True,
            position_side='LONG',
        ),
    ])
    session.commit()
    session.close()

    response = client.get(
        '/api/v1/risk-control/history/open-trades',
        params={
            'account_id': account_id,
            'end_time': '2026-01-03T13:30:00',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 1
    assert [item['symbol'] for item in payload['items']] == ['SOLUSDT']


def test_open_trades_match_active_position_when_history_position_side_is_both(review_client):
    client, session_factory = review_client
    session = session_factory()

    account = Account(
        exchange='binance',
        name='One Way Mode Account',
        api_key='test-key',
        api_secret='test-secret',
        initial_balance=10000,
    )
    session.add(account)
    session.flush()
    account_id = account.id

    session.add_all([
        TransactionHistory(
            account_id=account_id,
            symbol='SIRENUSDT',
            type='TRADE',
            side='SELL',
            position_side='BOTH',
            price=1.5952,
            qty=466,
            quote_qty=743.3632,
            commission=0.8,
            commission_asset='USDT',
            realized_pnl=0,
            time=datetime(2026, 3, 25, 17, 37, 9),
            order_id='SIREN_OPEN_1',
            transaction_id='ORDER_SIREN_OPEN_1',
        ),
        Position(
            account_id=account_id,
            symbol='SIRENUSDT',
            size=466,
            entry_price=1.5952,
            current_price=1.73077,
            unrealized_pnl=-63.17562,
            leverage=2,
            risk_level=RiskLevelEnum.MEDIUM,
            is_active=True,
            position_side='SHORT',
        ),
    ])
    session.commit()
    session.close()

    response = client.get(
        '/api/v1/risk-control/history/open-trades',
        params={
            'account_id': account_id,
            'end_time': '2026-03-30T12:00:00',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 1
    item = payload['items'][0]
    assert item['symbol'] == 'SIRENUSDT'
    assert item['direction'] == 'SHORT'
    assert item['position_side'] == 'SHORT'
    assert item['open_qty'] == 466.0
    assert item['unrealized_pnl'] == -63.17562


def test_completed_trades_ignore_orphan_close_rows(review_client):
    client, session_factory = review_client
    session = session_factory()

    account = Account(
        exchange='okx',
        name='Completed Trade Filter Account',
        api_key='test-key',
        api_secret='test-secret',
        initial_balance=10000,
    )
    session.add(account)
    session.flush()
    account_id = account.id

    session.add_all([
        TransactionHistory(
            account_id=account_id,
            symbol='BTCUSDT',
            type='TRADE',
            side='SELL',
            position_side='LONG',
            price=101000,
            qty=1,
            quote_qty=101000,
            commission=1,
            commission_asset='USDT',
            realized_pnl=50,
            time=datetime(2026, 1, 3, 8, 0, 0),
            order_id='BTC_ORPHAN_CLOSE',
            transaction_id='ORDER_BTC_ORPHAN_CLOSE',
        ),
        TransactionHistory(
            account_id=account_id,
            symbol='BTCUSDT',
            type='TRADE',
            side='BUY',
            position_side='LONG',
            price=100000,
            qty=1,
            quote_qty=100000,
            commission=1,
            commission_asset='USDT',
            realized_pnl=0,
            time=datetime(2026, 1, 3, 9, 0, 0),
            order_id='BTC_REAL_OPEN',
            transaction_id='ORDER_BTC_REAL_OPEN',
        ),
        TransactionHistory(
            account_id=account_id,
            symbol='BTCUSDT',
            type='TRADE',
            side='SELL',
            position_side='LONG',
            price=102000,
            qty=1,
            quote_qty=102000,
            commission=1,
            commission_asset='USDT',
            realized_pnl=80,
            time=datetime(2026, 1, 3, 10, 0, 0),
            order_id='BTC_REAL_CLOSE',
            transaction_id='ORDER_BTC_REAL_CLOSE',
        ),
    ])
    session.commit()
    session.close()

    response = client.get(
        '/api/v1/risk-control/history/completed-trades',
        params={
            'account_id': account_id,
            'start_time': '2026-01-03T00:00:00',
            'end_time': '2026-01-04T00:00:00',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 1
    item = payload['items'][0]
    assert item['symbol'] == 'BTCUSDT'
    assert item['open_time'] == '2026-01-03T09:00:00'
    assert item['close_time'] == '2026-01-03T10:00:00'
    assert item['entry_order_count'] == 1
    assert item['exit_order_count'] == 1