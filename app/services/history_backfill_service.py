from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from app.models.risk_control import Account, AccountSnapshot, Position, TransactionHistory
from app.services.exchange.binance_adapter import create_adapter_for_account


MAX_PAGE_LIMIT = 1000
MIN_WINDOW_MS = 5 * 60 * 1000
BINANCE_MAX_INTERVAL_MS = (7 * 24 * 60 * 60 * 1000) - 1
DEFAULT_SNAPSHOT_INTERVAL_MINUTES = 60
CASHFLOW_TRANSACTION_TYPES = {
    'REALIZED_PNL',
    'FUNDING_FEE',
    'COMMISSION',
    'TRANSFER',
    'INTERNAL_TRANSFER',
}


def normalize_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def utc_to_ms(value: datetime) -> int:
    normalized = normalize_utc_naive(value).replace(tzinfo=timezone.utc)
    return int(normalized.timestamp() * 1000)


def unique_by_key(rows: Iterable[Dict], key_builder) -> List[Dict]:
    deduped: Dict[str, Dict] = {}
    for row in rows:
        key = key_builder(row)
        if not key:
            continue
        deduped[str(key)] = row
    return list(deduped.values())


async def _fetch_windowed_rows(
    fetch_page,
    start_ms: int,
    end_ms: int,
    *,
    request_name: str,
) -> List[Dict]:
    async def _fetch_window(window_start: int, window_end: int) -> List[Dict]:
        if window_end < window_start:
            return []

        # Binance /income and /userTrades both reject ranges larger than 7 days.
        if (window_end - window_start) > BINANCE_MAX_INTERVAL_MS:
            rows: List[Dict] = []
            current_start = window_start
            while current_start <= window_end:
                current_end = min(current_start + BINANCE_MAX_INTERVAL_MS, window_end)
                rows.extend(await _fetch_window(current_start, current_end))
                current_start = current_end + 1
            return rows

        page_rows = await fetch_page(window_start, window_end)
        if page_rows is None:
            raise RuntimeError(
                f'{request_name} request failed for window {window_start}-{window_end}'
            )

        if len(page_rows) < MAX_PAGE_LIMIT or (window_end - window_start) <= MIN_WINDOW_MS:
            return page_rows

        middle = (window_start + window_end) // 2
        left_rows = await _fetch_window(window_start, middle)
        right_rows = await _fetch_window(middle + 1, window_end)
        return left_rows + right_rows

    return await _fetch_window(start_ms, end_ms)


async def fetch_income_range(adapter, start_ms: int, end_ms: int) -> List[Dict]:
    rows = await _fetch_windowed_rows(
        lambda window_start, window_end: adapter.fetch_income_history(
            limit=MAX_PAGE_LIMIT,
            start_time=window_start,
            end_time=window_end,
        ),
        start_ms,
        end_ms,
        request_name='fetch_income_history',
    )
    return unique_by_key(rows, lambda item: item.get('tranId'))


async def fetch_trade_range(adapter, symbol: Optional[str], start_ms: int, end_ms: int) -> List[Dict]:
    rows = await _fetch_windowed_rows(
        lambda window_start, window_end: adapter.fetch_user_trades(
            symbol=symbol,
            limit=MAX_PAGE_LIMIT,
            start_time=window_start,
            end_time=window_end,
        ),
        start_ms,
        end_ms,
        request_name=f'fetch_user_trades[{symbol or "ALL"}]',
    )
    return unique_by_key(
        rows,
        lambda item: item.get('id') or item.get('tradeId') or f"{item.get('orderId')}:{item.get('time')}:{item.get('qty')}",
    )


def collect_trade_symbols(
    db: Session,
    account_id: int,
    income_rows: Sequence[Dict],
    start_time: datetime,
    extra_symbols: Optional[Sequence[str]] = None,
) -> List[str]:
    normalized_start = normalize_utc_naive(start_time)
    symbols: Set[str] = {
        str(item.get('symbol')).upper()
        for item in income_rows
        if item.get('symbol')
    }

    if extra_symbols:
        symbols.update(symbol.strip().upper() for symbol in extra_symbols if symbol and symbol.strip())

    existing_history_symbols = [
        row[0] for row in db.query(TransactionHistory.symbol)
        .filter(TransactionHistory.account_id == account_id)
        .filter(TransactionHistory.time >= normalized_start)
        .filter(TransactionHistory.symbol.isnot(None))
        .distinct()
        .all()
        if row[0]
    ]
    active_position_symbols = [
        row[0] for row in db.query(Position.symbol)
        .filter(Position.account_id == account_id)
        .filter(Position.symbol.isnot(None))
        .distinct()
        .all()
        if row[0]
    ]

    symbols.update(str(symbol).upper() for symbol in existing_history_symbols)
    symbols.update(str(symbol).upper() for symbol in active_position_symbols)
    return sorted(symbols)


def upsert_income_rows(db: Session, account_id: int, income_rows: Sequence[Dict]) -> Dict[str, int]:
    inserted = 0
    updated = 0

    for item in income_rows:
        tran_id = item.get('tranId')
        if not tran_id:
            continue

        transaction_id = str(tran_id)
        existing = db.query(TransactionHistory).filter(TransactionHistory.transaction_id == transaction_id).first()
        timestamp = datetime.fromtimestamp(item.get('time', 0) / 1000, tz=timezone.utc).replace(tzinfo=None)

        if not existing:
            existing = TransactionHistory(
                account_id=account_id,
                symbol=item.get('symbol'),
                type=item.get('incomeType'),
                side=None,
                position_side=None,
                price=None,
                qty=None,
                quote_qty=None,
                commission=None,
                commission_asset=item.get('asset'),
                realized_pnl=float(item.get('income', 0) or 0.0),
                time=timestamp,
                transaction_id=transaction_id,
            )
            db.add(existing)
            inserted += 1
            continue

        existing.account_id = account_id
        existing.symbol = item.get('symbol')
        existing.type = item.get('incomeType')
        existing.commission_asset = item.get('asset')
        existing.realized_pnl = float(item.get('income', 0) or 0.0)
        existing.time = timestamp
        db.add(existing)
        updated += 1

    return {'inserted': inserted, 'updated': updated}


def upsert_trade_rows(db: Session, account_id: int, trade_rows: Sequence[Dict]) -> Dict[str, int]:
    aggregated_trades: Dict[str, Dict] = {}
    for trade in trade_rows:
        order_id = trade.get('orderId')
        if order_id is None:
            continue

        order_id = str(order_id)
        qty = float(trade.get('qty', 0) or 0.0)
        price = float(trade.get('price', 0) or 0.0)

        if order_id not in aggregated_trades:
            aggregated_trades[order_id] = {
                'symbol': trade.get('symbol'),
                'side': trade.get('side'),
                'position_side': trade.get('positionSide'),
                'price_sum': price * qty,
                'qty': qty,
                'quote_qty': float(trade.get('quoteQty', 0) or 0.0),
                'commission': float(trade.get('commission', 0) or 0.0),
                'commission_asset': trade.get('commissionAsset'),
                'realized_pnl': float(trade.get('realizedPnl', 0) or 0.0),
                'time': int(trade.get('time', 0) or 0),
            }
            continue

        item = aggregated_trades[order_id]
        item['price_sum'] += price * qty
        item['qty'] += qty
        item['quote_qty'] += float(trade.get('quoteQty', 0) or 0.0)
        item['commission'] += float(trade.get('commission', 0) or 0.0)
        item['realized_pnl'] += float(trade.get('realizedPnl', 0) or 0.0)
        item['time'] = max(item['time'], int(trade.get('time', 0) or 0))

    inserted = 0
    updated = 0
    for order_id, item in aggregated_trades.items():
        transaction_id = f'ORDER_{order_id}'
        existing = db.query(TransactionHistory).filter(TransactionHistory.transaction_id == transaction_id).first()
        avg_price = item['price_sum'] / item['qty'] if item['qty'] > 0 else 0.0
        timestamp = datetime.fromtimestamp(item['time'] / 1000, tz=timezone.utc).replace(tzinfo=None)

        if not existing:
            existing = TransactionHistory(
                account_id=account_id,
                symbol=item['symbol'],
                type='TRADE',
                side=item['side'],
                position_side=item.get('position_side'),
                price=avg_price,
                qty=item['qty'],
                quote_qty=item['quote_qty'],
                commission=item['commission'],
                commission_asset=item['commission_asset'],
                realized_pnl=item['realized_pnl'],
                time=timestamp,
                order_id=order_id,
                transaction_id=transaction_id,
            )
            db.add(existing)
            inserted += 1
            continue

        existing.account_id = account_id
        existing.symbol = item['symbol']
        existing.type = 'TRADE'
        existing.side = item['side']
        existing.position_side = item.get('position_side')
        existing.price = avg_price
        existing.qty = item['qty']
        existing.quote_qty = item['quote_qty']
        existing.commission = item['commission']
        existing.commission_asset = item['commission_asset']
        existing.realized_pnl = item['realized_pnl']
        existing.time = timestamp
        existing.order_id = order_id
        db.add(existing)
        updated += 1

    return {'inserted': inserted, 'updated': updated}


def build_snapshot_candidate_times(
    db: Session,
    account_id: int,
    start_time: datetime,
    end_time: datetime,
    interval_minutes: int,
) -> List[datetime]:
    normalized_start = normalize_utc_naive(start_time)
    normalized_end = normalize_utc_naive(end_time)
    times: Set[datetime] = {normalized_start, normalized_end}

    current = normalized_start.replace(minute=0, second=0, microsecond=0)
    while current <= normalized_end:
        if current >= normalized_start:
            times.add(current)
        current += timedelta(minutes=interval_minutes)

    transaction_rows = (
        db.query(TransactionHistory.time)
        .filter(TransactionHistory.account_id == account_id)
        .filter(TransactionHistory.time >= normalized_start)
        .filter(TransactionHistory.time <= normalized_end)
        .filter(
            TransactionHistory.type.in_(CASHFLOW_TRANSACTION_TYPES.union({'TRADE'}))
        )
        .order_by(TransactionHistory.time.asc())
        .all()
    )
    for row in transaction_rows:
        if row[0]:
            times.add(row[0])

    return sorted(times)


def backfill_account_snapshots(
    db: Session,
    account: Account,
    start_time: datetime,
    end_time: datetime,
    interval_minutes: int = DEFAULT_SNAPSHOT_INTERVAL_MINUTES,
) -> Dict[str, int]:
    normalized_start = normalize_utc_naive(start_time)
    normalized_end = normalize_utc_naive(end_time)
    candidate_times = build_snapshot_candidate_times(
        db,
        account.id,
        normalized_start,
        normalized_end,
        interval_minutes=interval_minutes,
    )
    if not candidate_times:
        return {'inserted': 0, 'skipped': 0, 'candidate_count': 0}

    start_anchor = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.account_id == account.id)
        .filter(AccountSnapshot.timestamp <= normalized_start)
        .order_by(AccountSnapshot.timestamp.desc(), AccountSnapshot.id.desc())
        .first()
    )
    end_anchor = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.account_id == account.id)
        .filter(AccountSnapshot.timestamp >= normalized_end)
        .order_by(AccountSnapshot.timestamp.asc(), AccountSnapshot.id.asc())
        .first()
    )

    if start_anchor:
        anchor_direction = 'forward'
        anchor_time = start_anchor.timestamp
        anchor_balance = float(start_anchor.total_balance or 0.0)
        anchor_equity = float(start_anchor.total_equity or 0.0)
    else:
        anchor_direction = 'backward'
        anchor_time = end_anchor.timestamp if end_anchor else normalized_end
        anchor_balance = float(
            (end_anchor.total_balance if end_anchor else getattr(account, 'total_balance', 0.0)) or 0.0
        )
        anchor_equity = float(
            (end_anchor.total_equity if end_anchor else getattr(account, 'total_equity', 0.0)) or anchor_balance
        )

    equity_offset = anchor_equity - anchor_balance
    cashflow_rows = (
        db.query(TransactionHistory)
        .filter(TransactionHistory.account_id == account.id)
        .filter(TransactionHistory.type.in_(CASHFLOW_TRANSACTION_TYPES))
        .filter(TransactionHistory.time >= min(anchor_time, normalized_start))
        .filter(TransactionHistory.time <= max(anchor_time, normalized_end))
        .order_by(TransactionHistory.time.asc(), TransactionHistory.id.asc())
        .all()
    )

    balances_by_time: Dict[datetime, tuple[float, float]] = {}
    if anchor_direction == 'forward':
        cumulative_cashflow = 0.0
        row_index = 0
        for timestamp in candidate_times:
            while row_index < len(cashflow_rows) and cashflow_rows[row_index].time <= timestamp:
                cumulative_cashflow += float(cashflow_rows[row_index].realized_pnl or 0.0)
                row_index += 1
            total_balance = anchor_balance + cumulative_cashflow
            total_equity = total_balance + equity_offset
            balances_by_time[timestamp] = (round(total_balance, 8), round(total_equity, 8))
    else:
        total_cashflow = sum(float(row.realized_pnl or 0.0) for row in cashflow_rows)
        cumulative_before = 0.0
        row_index = 0
        for timestamp in candidate_times:
            while row_index < len(cashflow_rows) and cashflow_rows[row_index].time <= timestamp:
                cumulative_before += float(cashflow_rows[row_index].realized_pnl or 0.0)
                row_index += 1
            cashflow_after_timestamp = total_cashflow - cumulative_before
            total_balance = anchor_balance - cashflow_after_timestamp
            total_equity = total_balance + equity_offset
            balances_by_time[timestamp] = (round(total_balance, 8), round(total_equity, 8))

    existing_timestamps = {
        row[0] for row in db.query(AccountSnapshot.timestamp)
        .filter(AccountSnapshot.account_id == account.id)
        .filter(AccountSnapshot.timestamp >= normalized_start)
        .filter(AccountSnapshot.timestamp <= normalized_end)
        .all()
        if row[0]
    }

    inserted = 0
    skipped = 0
    for timestamp in candidate_times:
        if timestamp in existing_timestamps:
            skipped += 1
            continue

        total_balance, total_equity = balances_by_time[timestamp]
        db.add(
            AccountSnapshot(
                account_id=account.id,
                total_balance=total_balance,
                total_equity=total_equity,
                timestamp=timestamp,
            )
        )
        inserted += 1

    return {
        'inserted': inserted,
        'skipped': skipped,
        'candidate_count': len(candidate_times),
    }


async def backfill_account_history(
    db: Session,
    account: Account,
    days: int = 7,
    extra_symbols: Optional[Sequence[str]] = None,
    include_snapshots: bool = True,
    snapshot_interval_minutes: int = DEFAULT_SNAPSHOT_INTERVAL_MINUTES,
) -> Dict[str, object]:
    adapter = create_adapter_for_account(account)
    if not adapter:
        raise ValueError(f'account {account.id} adapter unavailable')

    end_time = datetime.utcnow().replace(tzinfo=timezone.utc)
    start_time = end_time - timedelta(days=days)
    start_ms = utc_to_ms(start_time)
    end_ms = utc_to_ms(end_time)

    db.query(TransactionHistory).filter(
        TransactionHistory.account_id == account.id,
        TransactionHistory.transaction_id.like('T_%'),
    ).delete(synchronize_session=False)
    db.commit()

    income_rows = await fetch_income_range(adapter, start_ms, end_ms)
    symbols = collect_trade_symbols(
        db,
        account.id,
        income_rows,
        start_time=start_time,
        extra_symbols=extra_symbols,
    )

    all_trade_rows: List[Dict] = []
    if getattr(adapter, 'supports_all_symbol_trades', False):
        all_trade_rows = await fetch_trade_range(adapter, None, start_ms, end_ms)
    elif symbols:
        for symbol in symbols:
            symbol_rows = await fetch_trade_range(adapter, symbol, start_ms, end_ms)
            all_trade_rows.extend(symbol_rows)

    income_result = upsert_income_rows(db, account.id, income_rows)
    trade_result = upsert_trade_rows(db, account.id, all_trade_rows)
    db.commit()

    snapshot_result = {'inserted': 0, 'skipped': 0, 'candidate_count': 0}
    if include_snapshots:
        snapshot_result = backfill_account_snapshots(
            db,
            account,
            start_time=start_time,
            end_time=end_time,
            interval_minutes=snapshot_interval_minutes,
        )
        db.commit()

    return {
        'account_id': account.id,
        'account_name': account.name,
        'days': days,
        'range_start': normalize_utc_naive(start_time).isoformat(),
        'range_end': normalize_utc_naive(end_time).isoformat(),
        'income_rows_fetched': len(income_rows),
        'trade_rows_fetched': len(all_trade_rows),
        'symbols_scanned': symbols,
        'income': income_result,
        'trades': trade_result,
        'snapshots': snapshot_result,
        'message': (
            f'Backfilled {days} days for account {account.id}: '
            f"income +{income_result['inserted']}/{income_result['updated']}, "
            f"trades +{trade_result['inserted']}/{trade_result['updated']}, "
            f"snapshots +{snapshot_result['inserted']}"
        ),
    }


def load_active_accounts(db: Session, account_ids: Optional[Sequence[int]] = None) -> List[Account]:
    query = db.query(Account).filter(Account.is_active == True)
    if account_ids:
        query = query.filter(Account.id.in_(list(account_ids)))
    return query.order_by(Account.id.asc()).all()