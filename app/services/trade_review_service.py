from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.risk_control import AccountSnapshot, Position, TickerHistory, TransactionHistory


EPSILON = 1e-8
CURVE_POINT_LIMIT = 240


class TradeReviewService:
    def __init__(self, db: Session):
        self.db = db

    def list_open_trades(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict:
        reference_time = end_time or datetime.utcnow()
        _, active_campaigns = self._scan_trade_campaigns(
            account_id=account_id,
            symbol=symbol,
            end_time=end_time,
        )

        open_trades: List[Dict] = []
        for campaign in active_campaigns:
            last_activity_time = campaign['close_time']
            if start_time is not None and last_activity_time < start_time:
                continue
            campaign['last_activity_time'] = last_activity_time
            campaign['close_time'] = max(reference_time, campaign['open_time'])
            open_trades.append(campaign)

        self._attach_funding(open_trades, account_id=account_id, symbol=symbol)
        self._attach_open_trade_market_data(open_trades, reference_time=reference_time)
        open_trades.sort(key=lambda item: item['last_activity_time'], reverse=True)

        total = len(open_trades)
        items = open_trades[skip:skip + limit]
        return {
            'total': total,
            'items': [self._serialize_open_trade(item) for item in items],
        }

    def list_completed_trades(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict:
        completed_trades = self._build_completed_trades(
            account_id=account_id,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )
        total = len(completed_trades)
        items = completed_trades[skip:skip + limit]
        self._attach_trade_analytics(items)
        return {
            'total': total,
            'items': items,
        }

    def summarize_completed_trades(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict:
        completed_trades = self._build_completed_trades(
            account_id=account_id,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )

        total_count = len(completed_trades)
        net_values = [float(item['net_pnl']) for item in completed_trades]
        gross_values = [float(item['gross_realized_pnl']) for item in completed_trades]
        commission_values = [float(item['commission_cost']) for item in completed_trades]
        funding_values = [float(item['funding_pnl']) for item in completed_trades]
        holding_minutes = [float(item['holding_minutes']) for item in completed_trades]

        win_count = sum(1 for value in net_values if value > 0)
        loss_count = sum(1 for value in net_values if value < 0)
        win_rate = round((win_count / total_count) * 100, 2) if total_count else 0.0

        positive_sum = sum(value for value in net_values if value > 0)
        negative_sum = sum(value for value in net_values if value < 0)
        profit_factor = round(positive_sum / abs(negative_sum), 2) if negative_sum < 0 else None

        return {
            'total_count': total_count,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': win_rate,
            'gross_realized_pnl': round(sum(gross_values), 4),
            'commission_cost': round(sum(commission_values), 4),
            'funding_pnl': round(sum(funding_values), 4),
            'net_pnl': round(sum(net_values), 4),
            'average_net_pnl': round(sum(net_values) / total_count, 4) if total_count else 0.0,
            'average_holding_minutes': round(sum(holding_minutes) / total_count, 2) if total_count else 0.0,
            'profit_factor': profit_factor,
        }

    def completed_trade_timeline(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict:
        completed_trades = self._build_completed_trades(
            account_id=account_id,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )

        if not completed_trades:
            return {
                'xAxis': [],
                'series': [
                    {'name': '单笔净盈亏', 'type': 'bar', 'data': []},
                    {'name': '累计净盈亏', 'type': 'line', 'data': []},
                    {'name': '平仓笔数', 'type': 'line', 'data': []},
                ],
            }

        bucket_mode = self._get_bucket_mode(start_time, end_time, completed_trades)
        bucket_start = self._truncate_bucket(start_time or completed_trades[-1]['close_time'], bucket_mode)
        bucket_end = self._truncate_bucket(end_time or completed_trades[0]['close_time'], bucket_mode)
        step = timedelta(hours=1) if bucket_mode == 'hour' else timedelta(days=1)

        bucket_values: Dict[datetime, float] = {}
        bucket_counts: Dict[datetime, int] = {}
        for item in completed_trades:
            bucket = self._truncate_bucket(item['close_time'], bucket_mode)
            bucket_values[bucket] = round(bucket_values.get(bucket, 0.0) + float(item['net_pnl']), 4)
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

        buckets = []
        current = bucket_start
        while current <= bucket_end:
            buckets.append(current)
            current += step

        period_values = [round(bucket_values.get(bucket, 0.0), 4) for bucket in buckets]
        close_counts = [float(bucket_counts.get(bucket, 0)) for bucket in buckets]
        cumulative_values = []
        running_total = 0.0
        for value in period_values:
            running_total = round(running_total + value, 4)
            cumulative_values.append(running_total)

        return {
            'xAxis': [self._format_bucket_label(bucket, bucket_mode) for bucket in buckets],
            'series': [
                {'name': '单笔净盈亏', 'type': 'bar', 'data': period_values},
                {'name': '累计净盈亏', 'type': 'line', 'data': cumulative_values},
                {'name': '平仓笔数', 'type': 'line', 'data': close_counts},
            ],
        }

    def _build_completed_trades(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict]:
        completed_trades, _ = self._scan_trade_campaigns(
            account_id=account_id,
            symbol=symbol,
            end_time=end_time,
        )

        filtered_trades = [
            item for item in completed_trades
            if (start_time is None or item['close_time'] >= start_time)
            and (end_time is None or item['close_time'] <= end_time)
        ]

        self._attach_funding(filtered_trades, account_id=account_id, symbol=symbol)
        for item in filtered_trades:
            self._update_net_pnl(item)

        filtered_trades.sort(key=lambda item: item['close_time'], reverse=True)
        return filtered_trades

    def _scan_trade_campaigns(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[Dict], List[Dict]]:
        trade_query = self.db.query(TransactionHistory).filter(TransactionHistory.type == 'TRADE')
        if account_id is not None:
            trade_query = trade_query.filter(TransactionHistory.account_id == account_id)
        if symbol:
            trade_query = trade_query.filter(func.upper(TransactionHistory.symbol) == symbol.strip().upper())
        if end_time is not None:
            trade_query = trade_query.filter(TransactionHistory.time <= end_time)

        trade_rows = trade_query.order_by(
            TransactionHistory.account_id.asc(),
            TransactionHistory.symbol.asc(),
            TransactionHistory.time.asc(),
            TransactionHistory.id.asc(),
        ).all()

        active_campaigns: Dict[Tuple[int, str, str], Dict] = {}
        sequence_map: Dict[Tuple[int, str, str], int] = defaultdict(int)
        completed_trades: List[Dict] = []

        for row in trade_rows:
            trade_symbol = (row.symbol or '').strip().upper()
            side = (row.side or '').strip().upper()
            if not trade_symbol or side not in {'BUY', 'SELL'}:
                continue

            total_qty = float(row.qty or 0.0)
            if total_qty <= EPSILON:
                continue

            position_side = (getattr(row, 'position_side', None) or 'NET').strip().upper()
            key = (row.account_id, trade_symbol, position_side)
            order_direction = 'LONG' if side == 'BUY' else 'SHORT'
            price = float(row.price or 0.0)
            commission_total = float(row.commission or 0.0)
            realized_pnl_total = float(row.realized_pnl or 0.0)
            commission_per_qty = commission_total / total_qty if total_qty > EPSILON else 0.0

            active = active_campaigns.get(key)
            close_allocatable_qty = 0.0
            if active and active['direction'] != order_direction:
                close_allocatable_qty = min(total_qty, active['open_qty'])
            realized_pnl_per_close_qty = (
                realized_pnl_total / close_allocatable_qty
                if close_allocatable_qty > EPSILON
                else 0.0
            )

            remaining_qty = total_qty
            while remaining_qty > EPSILON:
                active = active_campaigns.get(key)
                if not active:
                    sequence_map[key] += 1
                    active = self._new_campaign(
                        account_id=row.account_id,
                        symbol=trade_symbol,
                        position_side=position_side,
                        direction=order_direction,
                        open_time=row.time,
                        sequence=sequence_map[key],
                    )
                    active_campaigns[key] = active

                if active['direction'] == order_direction:
                    entry_qty = remaining_qty
                    commission_allocated = round(entry_qty * commission_per_qty, 8)
                    self._append_order_leg(
                        active['entry_orders'],
                        row=row,
                        qty=entry_qty,
                        commission=commission_allocated,
                        realized_pnl=0.0,
                    )
                    active['entry_qty'] += entry_qty
                    active['entry_notional'] += price * entry_qty
                    active['commission_cost'] += commission_allocated
                    active['open_qty'] += entry_qty
                    remaining_qty = 0.0
                    continue

                matched_qty = min(active['open_qty'], remaining_qty)
                commission_allocated = round(matched_qty * commission_per_qty, 8)
                realized_pnl_allocated = round(matched_qty * realized_pnl_per_close_qty, 8)
                self._append_order_leg(
                    active['exit_orders'],
                    row=row,
                    qty=matched_qty,
                    commission=commission_allocated,
                    realized_pnl=realized_pnl_allocated,
                )
                active['exit_qty'] += matched_qty
                active['exit_notional'] += price * matched_qty
                active['commission_cost'] += commission_allocated
                active['gross_realized_pnl'] += realized_pnl_allocated
                active['close_time'] = row.time
                active['open_qty'] -= matched_qty
                remaining_qty -= matched_qty

                if active['open_qty'] <= EPSILON:
                    self._finalize_campaign(active)
                    completed_trades.append(active)
                    del active_campaigns[key]

        for active in active_campaigns.values():
            self._finalize_campaign(active)

        return completed_trades, list(active_campaigns.values())

    def _attach_funding(
        self,
        completed_trades: List[Dict],
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> None:
        if not completed_trades:
            return

        min_open_time = min(item['open_time'] for item in completed_trades)
        max_close_time = max(item['close_time'] for item in completed_trades)

        funding_query = self.db.query(TransactionHistory).filter(
            TransactionHistory.type == 'FUNDING_FEE',
            TransactionHistory.time >= min_open_time,
            TransactionHistory.time <= max_close_time,
        )
        if account_id is not None:
            funding_query = funding_query.filter(TransactionHistory.account_id == account_id)
        if symbol:
            funding_query = funding_query.filter(func.upper(TransactionHistory.symbol) == symbol.strip().upper())

        funding_rows = funding_query.order_by(TransactionHistory.time.asc(), TransactionHistory.id.asc()).all()
        campaigns_by_key: Dict[Tuple[int, str], List[Dict]] = defaultdict(list)
        for item in completed_trades:
            campaigns_by_key[(item['account_id'], item['symbol'])].append(item)

        for items in campaigns_by_key.values():
            items.sort(key=lambda item: item['open_time'])

        for funding in funding_rows:
            funding_symbol = (funding.symbol or '').strip().upper()
            if not funding_symbol:
                continue

            amount = float(funding.realized_pnl or 0.0)
            for campaign in campaigns_by_key.get((funding.account_id, funding_symbol), []):
                if campaign['open_time'] <= funding.time <= campaign['close_time']:
                    campaign['funding_pnl'] += amount
                    campaign['funding_items'].append({
                        'transaction_id': funding.transaction_id,
                        'time': funding.time,
                        'amount': round(amount, 8),
                    })
                    break

    def _attach_trade_analytics(self, completed_trades: List[Dict]) -> None:
        if not completed_trades:
            return

        ticker_rows_by_key = self._load_ticker_rows(completed_trades)
        snapshot_rows_by_account = self._load_account_snapshot_rows(completed_trades)
        for campaign in completed_trades:
            campaign.update(
                self._build_trade_analytics(
                    campaign,
                    ticker_rows_by_key.get((campaign['account_id'], campaign['symbol']), []),
                    snapshot_rows_by_account.get(campaign['account_id'], []),
                )
            )

    def _load_ticker_rows(self, completed_trades: List[Dict]) -> Dict[Tuple[int, str], List[TickerHistory]]:
        grouped_ranges: Dict[Tuple[int, str], Dict[str, datetime]] = {}
        for campaign in completed_trades:
            key = (campaign['account_id'], campaign['symbol'])
            grouped_ranges.setdefault(
                key,
                {
                    'open_time': campaign['open_time'],
                    'close_time': campaign['close_time'],
                },
            )
            grouped_ranges[key]['open_time'] = min(grouped_ranges[key]['open_time'], campaign['open_time'])
            grouped_ranges[key]['close_time'] = max(grouped_ranges[key]['close_time'], campaign['close_time'])

        ticker_rows_by_key: Dict[Tuple[int, str], List[TickerHistory]] = {}
        for (account_id, trade_symbol), time_range in grouped_ranges.items():
            ticker_rows_by_key[(account_id, trade_symbol)] = (
                self.db.query(TickerHistory)
                .filter(TickerHistory.account_id == account_id)
                .filter(func.upper(TickerHistory.symbol) == trade_symbol)
                .filter(TickerHistory.timestamp >= time_range['open_time'])
                .filter(TickerHistory.timestamp <= time_range['close_time'])
                .order_by(TickerHistory.timestamp.asc(), TickerHistory.id.asc())
                .all()
            )

        return ticker_rows_by_key

    def _load_account_snapshot_rows(self, completed_trades: List[Dict]) -> Dict[int, List[AccountSnapshot]]:
        grouped_ranges: Dict[int, Dict[str, datetime]] = {}
        for campaign in completed_trades:
            grouped_ranges.setdefault(
                campaign['account_id'],
                {
                    'open_time': campaign['open_time'],
                    'close_time': campaign['close_time'],
                },
            )
            grouped_ranges[campaign['account_id']]['open_time'] = min(
                grouped_ranges[campaign['account_id']]['open_time'],
                campaign['open_time'],
            )
            grouped_ranges[campaign['account_id']]['close_time'] = max(
                grouped_ranges[campaign['account_id']]['close_time'],
                campaign['close_time'],
            )

        snapshot_rows_by_account: Dict[int, List[AccountSnapshot]] = {}
        for account_id, time_range in grouped_ranges.items():
            history_rows = (
                self.db.query(AccountSnapshot)
                .filter(AccountSnapshot.account_id == account_id)
                .filter(AccountSnapshot.timestamp >= time_range['open_time'])
                .filter(AccountSnapshot.timestamp <= time_range['close_time'])
                .order_by(AccountSnapshot.timestamp.asc(), AccountSnapshot.id.asc())
                .all()
            )
            initial_row = (
                self.db.query(AccountSnapshot)
                .filter(AccountSnapshot.account_id == account_id)
                .filter(AccountSnapshot.timestamp < time_range['open_time'])
                .order_by(AccountSnapshot.timestamp.desc(), AccountSnapshot.id.desc())
                .first()
            )

            rows = history_rows
            if initial_row:
                rows = [initial_row] + history_rows
            snapshot_rows_by_account[account_id] = rows

        return snapshot_rows_by_account

    def _build_trade_analytics(
        self,
        campaign: Dict,
        ticker_rows: List[TickerHistory],
        account_snapshot_rows: List[AccountSnapshot],
    ) -> Dict:
        analytics = {
            'max_floating_profit': 0.0,
            'max_drawdown': 0.0,
            'price_sample_count': 0,
            'holding_curve_point_count': 0,
            'account_equity_point_count': 0,
            'holding_curve': [],
            'account_equity_curve': [],
        }

        relevant_ticker_rows = [
            row for row in ticker_rows
            if campaign['open_time'] <= row.timestamp <= campaign['close_time']
        ]
        analytics['price_sample_count'] = len(relevant_ticker_rows)

        timeline_events = []
        sequence = 0
        for leg in campaign['entry_orders']:
            timeline_events.append({
                'time': leg['time'],
                'priority': 0,
                'sequence': sequence,
                'event_type': 'entry',
                'price': float(leg['price'] or 0.0),
                'qty': float(leg['qty'] or 0.0),
                'commission': float(leg['commission'] or 0.0),
                'realized_pnl': 0.0,
            })
            sequence += 1

        for leg in campaign['exit_orders']:
            timeline_events.append({
                'time': leg['time'],
                'priority': 0,
                'sequence': sequence,
                'event_type': 'exit',
                'price': float(leg['price'] or 0.0),
                'qty': float(leg['qty'] or 0.0),
                'commission': float(leg['commission'] or 0.0),
                'realized_pnl': float(leg['realized_pnl'] or 0.0),
            })
            sequence += 1

        for funding in campaign['funding_items']:
            timeline_events.append({
                'time': funding['time'],
                'priority': 1,
                'sequence': sequence,
                'event_type': 'funding',
                'price': None,
                'qty': 0.0,
                'commission': 0.0,
                'realized_pnl': float(funding['amount'] or 0.0),
            })
            sequence += 1

        for ticker in relevant_ticker_rows:
            timeline_events.append({
                'time': ticker.timestamp,
                'priority': 2,
                'sequence': sequence,
                'event_type': 'mark',
                'price': float(ticker.price or 0.0),
                'qty': 0.0,
                'commission': 0.0,
                'realized_pnl': 0.0,
            })
            sequence += 1

        if not timeline_events:
            return analytics

        timeline_events.sort(key=lambda item: (item['time'], item['priority'], item['sequence']))

        open_qty = 0.0
        open_cost = 0.0
        realized_pnl = 0.0
        funding_pnl = 0.0
        commission_cost = 0.0
        last_price: Optional[float] = None
        curve_points: List[Dict] = []

        for event in timeline_events:
            event_price = event['price']
            if event['event_type'] == 'entry':
                open_qty += event['qty']
                open_cost += (event_price or 0.0) * event['qty']
                commission_cost += event['commission']
                if event_price:
                    last_price = event_price
            elif event['event_type'] == 'exit':
                if event_price:
                    last_price = event_price
                matched_qty = min(open_qty, event['qty'])
                average_entry_price = (open_cost / open_qty) if open_qty > EPSILON else 0.0
                open_cost = max(open_cost - average_entry_price * matched_qty, 0.0)
                open_qty = max(open_qty - matched_qty, 0.0)
                realized_pnl += event['realized_pnl']
                commission_cost += event['commission']
            elif event['event_type'] == 'funding':
                funding_pnl += event['realized_pnl']
            elif event_price:
                last_price = event_price

            unrealized_pnl = self._calculate_unrealized_pnl(
                direction=campaign['direction'],
                open_qty=open_qty,
                open_cost=open_cost,
                mark_price=last_price,
            )
            curve_points.append({
                'time': event['time'],
                'event_type': event['event_type'],
                'price': round(last_price, 8) if last_price is not None else None,
                'open_qty': round(open_qty, 8),
                'realized_pnl': round(realized_pnl, 8),
                'unrealized_pnl': round(unrealized_pnl, 8),
                'net_pnl': round(realized_pnl - commission_cost + funding_pnl + unrealized_pnl, 8),
            })

        if curve_points:
            curve_points[-1]['unrealized_pnl'] = 0.0
            curve_points[-1]['net_pnl'] = round(float(campaign['net_pnl']), 8)

        analytics['max_floating_profit'] = round(
            max([0.0, *[point['net_pnl'] for point in curve_points]]),
            8,
        )

        peak_value = 0.0
        max_drawdown = 0.0
        for point in curve_points:
            peak_value = max(peak_value, point['net_pnl'])
            max_drawdown = max(max_drawdown, peak_value - point['net_pnl'])

        analytics['max_drawdown'] = round(max_drawdown, 8)
        analytics['holding_curve'] = self._compress_curve_points(curve_points)
        analytics['holding_curve_point_count'] = len(analytics['holding_curve'])
        analytics['account_equity_curve'] = self._build_account_equity_curve(campaign, account_snapshot_rows)
        analytics['account_equity_point_count'] = len(analytics['account_equity_curve'])
        return analytics

    def _build_account_equity_curve(
        self,
        campaign: Dict,
        account_snapshot_rows: List[AccountSnapshot],
    ) -> List[Dict]:
        if not account_snapshot_rows:
            return []

        latest_before_open: Optional[AccountSnapshot] = None
        in_range_rows: List[AccountSnapshot] = []
        for row in account_snapshot_rows:
            if row.timestamp <= campaign['open_time']:
                latest_before_open = row
            if campaign['open_time'] <= row.timestamp <= campaign['close_time']:
                in_range_rows.append(row)

        curve_points: List[Dict] = []
        if latest_before_open:
            curve_points.append({
                'time': campaign['open_time'],
                'total_equity': round(float(latest_before_open.total_equity or 0.0), 8),
                'total_balance': round(float(latest_before_open.total_balance or 0.0), 8),
            })

        for row in in_range_rows:
            point = {
                'time': row.timestamp,
                'total_equity': round(float(row.total_equity or 0.0), 8),
                'total_balance': round(float(row.total_balance or 0.0), 8),
            }
            if curve_points and curve_points[-1]['time'] == point['time']:
                curve_points[-1] = point
            else:
                curve_points.append(point)

        if curve_points and curve_points[-1]['time'] < campaign['close_time']:
            last_point = curve_points[-1]
            curve_points.append({
                'time': campaign['close_time'],
                'total_equity': last_point['total_equity'],
                'total_balance': last_point['total_balance'],
            })

        return self._compress_curve_points(curve_points)

    def _calculate_unrealized_pnl(
        self,
        direction: str,
        open_qty: float,
        open_cost: float,
        mark_price: Optional[float],
    ) -> float:
        if open_qty <= EPSILON or mark_price is None:
            return 0.0

        average_entry_price = open_cost / open_qty if open_qty > EPSILON else 0.0
        if direction == 'SHORT':
            return (average_entry_price - mark_price) * open_qty
        return (mark_price - average_entry_price) * open_qty

    def _compress_curve_points(self, curve_points: List[Dict]) -> List[Dict]:
        if len(curve_points) <= CURVE_POINT_LIMIT:
            return curve_points

        last_index = len(curve_points) - 1
        selected_indexes = {0, last_index}
        scale = last_index / (CURVE_POINT_LIMIT - 1)
        for index in range(1, CURVE_POINT_LIMIT - 1):
            selected_indexes.add(round(index * scale))

        return [curve_points[index] for index in sorted(selected_indexes)]

    def _new_campaign(
        self,
        account_id: int,
        symbol: str,
        position_side: str,
        direction: str,
        open_time: datetime,
        sequence: int,
    ) -> Dict:
        return {
            'id': f'{account_id}:{symbol}:{position_side}:{sequence}',
            'account_id': account_id,
            'symbol': symbol,
            'position_side': None if position_side == 'NET' else position_side,
            'direction': direction,
            'entry_side': 'BUY' if direction == 'LONG' else 'SELL',
            'exit_side': 'SELL' if direction == 'LONG' else 'BUY',
            'open_time': open_time,
            'close_time': open_time,
            'open_qty': 0.0,
            'entry_qty': 0.0,
            'exit_qty': 0.0,
            'entry_notional': 0.0,
            'exit_notional': 0.0,
            'entry_avg_price': 0.0,
            'exit_avg_price': 0.0,
            'quantity': 0.0,
            'gross_realized_pnl': 0.0,
            'commission_cost': 0.0,
            'funding_pnl': 0.0,
            'net_pnl': 0.0,
            'max_floating_profit': 0.0,
            'max_drawdown': 0.0,
            'price_sample_count': 0,
            'holding_curve_point_count': 0,
            'account_equity_point_count': 0,
            'holding_minutes': 0.0,
            'entry_order_count': 0,
            'exit_order_count': 0,
            'funding_event_count': 0,
            'entry_orders': [],
            'exit_orders': [],
            'funding_items': [],
            'holding_curve': [],
            'account_equity_curve': [],
        }

    def _append_order_leg(
        self,
        collection: List[Dict],
        row: TransactionHistory,
        qty: float,
        commission: float,
        realized_pnl: float,
    ) -> None:
        collection.append({
            'order_id': row.order_id,
            'transaction_id': row.transaction_id,
            'time': row.time,
            'side': row.side,
            'qty': round(qty, 8),
            'price': round(float(row.price or 0.0), 8),
            'commission': round(commission, 8),
            'realized_pnl': round(realized_pnl, 8),
        })

    def _finalize_campaign(self, campaign: Dict) -> None:
        campaign['quantity'] = round(min(campaign['entry_qty'], campaign['exit_qty']), 8)
        campaign['entry_avg_price'] = round(
            campaign['entry_notional'] / campaign['entry_qty'],
            8,
        ) if campaign['entry_qty'] > EPSILON else 0.0
        campaign['exit_avg_price'] = round(
            campaign['exit_notional'] / campaign['exit_qty'],
            8,
        ) if campaign['exit_qty'] > EPSILON else 0.0
        campaign['holding_minutes'] = round(
            max((campaign['close_time'] - campaign['open_time']).total_seconds() / 60, 0.0),
            2,
        )
        campaign['entry_order_count'] = len(campaign['entry_orders'])
        campaign['exit_order_count'] = len(campaign['exit_orders'])

    def _update_net_pnl(self, campaign: Dict) -> None:
        campaign['funding_pnl'] = round(float(campaign['funding_pnl']), 8)
        campaign['commission_cost'] = round(float(campaign['commission_cost']), 8)
        campaign['gross_realized_pnl'] = round(float(campaign['gross_realized_pnl']), 8)
        campaign['net_pnl'] = round(
            campaign['gross_realized_pnl'] - campaign['commission_cost'] + campaign['funding_pnl'],
            8,
        )
        campaign['funding_event_count'] = len(campaign['funding_items'])

    def _attach_open_trade_market_data(self, open_trades: List[Dict], reference_time: datetime) -> None:
        if not open_trades:
            return

        active_positions = self._load_active_positions(open_trades)
        latest_ticker_rows = self._load_latest_ticker_rows(open_trades, reference_time=reference_time)
        for campaign in open_trades:
            position = active_positions.get(self._position_lookup_key(campaign))
            latest_ticker = latest_ticker_rows.get((campaign['account_id'], campaign['symbol']))
            latest_mark_price = None
            if position and position.current_price is not None:
                latest_mark_price = float(position.current_price)
            elif latest_ticker and latest_ticker.price is not None:
                latest_mark_price = float(latest_ticker.price)

            if position and position.entry_price:
                campaign['entry_avg_price'] = round(float(position.entry_price), 8)
            if position and position.size is not None and float(position.size) > EPSILON:
                campaign['open_qty'] = round(float(position.size), 8)
            if position and position.leverage is not None:
                campaign['leverage'] = round(float(position.leverage), 4)

            campaign['latest_mark_price'] = round(latest_mark_price, 8) if latest_mark_price is not None else None
            campaign['holding_minutes'] = round(
                max((campaign['close_time'] - campaign['open_time']).total_seconds() / 60, 0.0),
                2,
            )
            campaign['entry_order_count'] = len(campaign['entry_orders'])
            campaign['exit_order_count'] = len(campaign['exit_orders'])
            campaign['order_ids'] = self._collect_order_ids(campaign)
            campaign['realized_pnl'] = round(float(campaign['gross_realized_pnl']), 8)
            campaign['funding_pnl'] = round(float(campaign['funding_pnl']), 8)
            campaign['commission_cost'] = round(float(campaign['commission_cost']), 8)
            if position and position.unrealized_pnl is not None:
                campaign['unrealized_pnl'] = round(float(position.unrealized_pnl), 8)
            else:
                campaign['unrealized_pnl'] = round(
                    self._calculate_unrealized_pnl(
                        direction=campaign['direction'],
                        open_qty=float(campaign['open_qty'] or 0.0),
                        open_cost=float(campaign['entry_avg_price'] or 0.0) * float(campaign['open_qty'] or 0.0),
                        mark_price=latest_mark_price,
                    ),
                    8,
                )
            campaign['net_pnl'] = round(
                campaign['realized_pnl'] - campaign['commission_cost'] + campaign['funding_pnl'] + campaign['unrealized_pnl'],
                8,
            )

    def _load_active_positions(self, open_trades: List[Dict]) -> Dict[Tuple[int, str, str], Position]:
        positions: Dict[Tuple[int, str, str], Position] = {}
        for campaign in open_trades:
            lookup_key = self._position_lookup_key(campaign)
            if lookup_key in positions:
                continue

            account_id, symbol, position_side = lookup_key
            query = (
                self.db.query(Position)
                .filter(Position.account_id == account_id)
                .filter(func.upper(Position.symbol) == symbol)
                .filter(Position.is_active == True)
            )
            if position_side == 'NET':
                query = query.filter((Position.position_side.is_(None)) | (func.upper(Position.position_side) == 'NET'))
            else:
                query = query.filter(func.upper(Position.position_side) == position_side)

            position = query.order_by(Position.updated_at.desc(), Position.id.desc()).first()
            if position:
                positions[lookup_key] = position
        return positions

    def _position_lookup_key(self, campaign: Dict) -> Tuple[int, str, str]:
        return (
            campaign['account_id'],
            campaign['symbol'],
            (campaign.get('position_side') or 'NET').strip().upper(),
        )

    def _load_latest_ticker_rows(
        self,
        open_trades: List[Dict],
        reference_time: datetime,
    ) -> Dict[Tuple[int, str], Optional[TickerHistory]]:
        latest_rows: Dict[Tuple[int, str], Optional[TickerHistory]] = {}
        for campaign in open_trades:
            key = (campaign['account_id'], campaign['symbol'])
            if key in latest_rows:
                continue
            latest_rows[key] = (
                self.db.query(TickerHistory)
                .filter(TickerHistory.account_id == campaign['account_id'])
                .filter(func.upper(TickerHistory.symbol) == campaign['symbol'])
                .filter(TickerHistory.timestamp >= campaign['open_time'])
                .filter(TickerHistory.timestamp <= reference_time)
                .order_by(TickerHistory.timestamp.desc(), TickerHistory.id.desc())
                .first()
            )
        return latest_rows

    def _collect_order_ids(self, campaign: Dict) -> List[str]:
        order_ids: List[str] = []
        seen = set()
        for leg in [*campaign['entry_orders'], *campaign['exit_orders']]:
            order_id = str(leg.get('order_id') or '').strip()
            if not order_id:
                continue
            lowered = order_id.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            order_ids.append(order_id)
        return order_ids

    def _serialize_open_trade(self, campaign: Dict) -> Dict:
        return {
            'id': campaign['id'],
            'account_id': campaign['account_id'],
            'symbol': campaign['symbol'],
            'position_side': campaign['position_side'],
            'direction': campaign['direction'],
            'leverage': campaign.get('leverage'),
            'open_time': campaign['open_time'],
            'last_activity_time': campaign['last_activity_time'],
            'holding_minutes': campaign['holding_minutes'],
            'open_qty': round(float(campaign['open_qty'] or 0.0), 8),
            'entry_avg_price': round(float(campaign['entry_avg_price'] or 0.0), 8),
            'realized_pnl': campaign['realized_pnl'],
            'commission_cost': campaign['commission_cost'],
            'funding_pnl': campaign['funding_pnl'],
            'unrealized_pnl': campaign['unrealized_pnl'],
            'net_pnl': campaign['net_pnl'],
            'latest_mark_price': campaign['latest_mark_price'],
            'entry_order_count': campaign['entry_order_count'],
            'exit_order_count': campaign['exit_order_count'],
            'order_ids': campaign['order_ids'],
        }

    def _get_bucket_mode(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        completed_trades: List[Dict],
    ) -> str:
        effective_start = start_time or completed_trades[-1]['close_time']
        effective_end = end_time or completed_trades[0]['close_time']
        return 'hour' if (effective_end - effective_start) <= timedelta(days=2) else 'day'

    def _truncate_bucket(self, value: datetime, bucket_mode: str) -> datetime:
        if bucket_mode == 'hour':
            return value.replace(minute=0, second=0, microsecond=0)
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    def _format_bucket_label(self, value: datetime, bucket_mode: str) -> str:
        if bucket_mode == 'hour':
            return value.strftime('%m-%d %H:00')
        return value.strftime('%m-%d')