import asyncio
import logging
import os
from typing import List, Dict

from app.core.database import SessionLocal
from app.services.exchange.binance_adapter import create_adapter_for_account
from app.services.ws_broadcast import manager as ws_manager
from app.services.risk_control_service import RiskControlService
from app.models.risk_control import Account, Position, RiskConfig, RiskLevelEnum, AccountSnapshot
from sqlalchemy.exc import OperationalError


class PositionSyncService:
    def __init__(self, interval: int = 30):
        self.interval = interval
        self._task = None
        self._running = False
        self._history_sync_counter = 0
        self._history_sync_interval = 10  # Sync history every 10 position sync cycles

    async def _sync_account(self, account: Account):
        adapter = create_adapter_for_account(account)
        if not adapter:
            logging.debug("position-sync: account %s missing API credentials", account.id)
            return

        rows = await adapter.fetch_positions()
        account_info = await adapter.fetch_account_info()
        
        if rows is None and account_info is None:
            logging.debug("position-sync: no data for account %s", account.id)
            return
            
        if rows:
            logging.info("position-sync: received %s position rows for account %s", len(rows), account.id)

        # upsert positions and account info
        db = SessionLocal()
        try:
            # Update Account Info
            if account_info:
                db_account = db.query(Account).get(account.id)
                if db_account:
                    try:
                        db_account.total_balance = float(account_info.get('totalWalletBalance', 0))
                        db_account.total_equity = float(account_info.get('totalMarginBalance', 0))
                        
                        # Take a snapshot if the last one was more than 1 hour ago
                        last_snapshot = db.query(AccountSnapshot).filter(
                            AccountSnapshot.account_id == account.id
                        ).order_by(AccountSnapshot.timestamp.desc()).first()
                        
                        if not last_snapshot or (datetime.utcnow() - last_snapshot.timestamp) > timedelta(hours=1):
                            snapshot = AccountSnapshot(
                                account_id=account.id,
                                total_equity=db_account.total_equity,
                                total_balance=db_account.total_balance
                            )
                            db.add(snapshot)
                            logging.info("position-sync: took snapshot for account %s", account.id)
                            
                    except Exception as e:
                        logging.error("position-sync: failed to update account info for %s: %s", account.id, e)

            # Periodic History Sync
            if self._history_sync_counter % self._history_sync_interval == 0:
                await self._sync_history(account, adapter, db)

            by_symbol = {}
            if rows:
                # aggregate Binance rows by (symbol, positionSide) so LONG and SHORT are separate
                for r in rows:
                    try:
                        symbol = r.get('symbol')
                        pside = (r.get('positionSide') or "NET").upper()
                        amt = float(r.get('positionAmt', 0) or 0)
                        entry_price = float(r.get('entryPrice', 0)) if r.get('entryPrice') else None
                        mark_price = float(r.get('markPrice', 0)) if r.get('markPrice') else None
                        unrealized = float(r.get('unRealizedProfit', 0) or 0)
                        leverage = float(r.get('leverage', 1) or 1)

                        key = (symbol, pside)
                        if key not in by_symbol:
                            by_symbol[key] = {
                                'net_amt': 0.0,
                                'entry_price': None,
                                'mark_price': None,
                                'unrealized': 0.0,
                                'leverage': leverage,
                            }

                        info = by_symbol[key]
                        info['net_amt'] += amt
                        # prefer a non-zero entry_price if available
                        if info['entry_price'] is None and entry_price and entry_price > 0:
                            info['entry_price'] = entry_price
                        # update mark_price to latest non-null
                        if mark_price is not None:
                            info['mark_price'] = mark_price
                        info['unrealized'] += unrealized
                        # keep leverage if present
                        if leverage:
                            info['leverage'] = leverage

                    except Exception:
                        logging.exception("position-sync: error processing row for account %s row=%s", account.id, r)

            # now upsert per-symbol consolidated info
            updated_keys = set()
            for (symbol, pside), info in by_symbol.items():
                try:
                    net_amt = info['net_amt']
                    size = abs(net_amt)
                    is_active = abs(net_amt) > 1e-12
                    entry_price = info['entry_price'] or 0.0
                    mark_price = info['mark_price']
                    unrealized = info['unrealized']
                    leverage = info.get('leverage', 1.0)

                    updated_keys.add((symbol, pside))

                    # the position_side column may not exist yet in older schemas; if that
                    # is the case, catch the OperationalError and fall back to the
                    # older net-per-symbol lookup (avoid crashing the poller).
                    try:
                        db_pos = db.query(Position).filter(
                            Position.account_id == account.id,
                            Position.symbol == symbol,
                            Position.position_side == pside
                        ).first()
                    except OperationalError:
                        logging.warning("position-sync: DB missing 'position_side' column — falling back to symbol-only lookup")
                        db.rollback()
                        db_pos = db.query(Position).filter(
                            Position.account_id == account.id,
                            Position.symbol == symbol
                        ).first()

                    if db_pos:
                        db_pos.size = size
                        if entry_price and entry_price > 0:
                            db_pos.entry_price = entry_price
                        if mark_price is not None:
                            db_pos.current_price = mark_price
                        db_pos.unrealized_pnl = unrealized
                        db_pos.leverage = leverage
                        db_pos.is_active = is_active

                        risk_cfg = db.query(RiskConfig).filter(
                            RiskConfig.account_id == account.id,
                            RiskConfig.is_active == True
                        ).first()
                        if risk_cfg:
                            svc = RiskControlService(db)
                            db_pos.risk_level = svc.calculate_risk_level(db_pos, risk_cfg)

                        db.add(db_pos)
                        db.commit()
                        db.refresh(db_pos)
                        await ws_manager.broadcast({
                            "type": "position_update",
                            "data": {
                                "id": db_pos.id,
                                "account_id": db_pos.account_id,
                                "symbol": db_pos.symbol,
                                "position_side": db_pos.position_side,
                                "size": db_pos.size,
                                "entry_price": db_pos.entry_price,
                                "current_price": db_pos.current_price,
                                "unrealized_pnl": db_pos.unrealized_pnl,
                                "risk_level": getattr(db_pos.risk_level, 'value', str(db_pos.risk_level)),
                                "is_active": db_pos.is_active,
                                "updated_at": db_pos.updated_at.isoformat() if db_pos.updated_at else None,
                            }
                        })
                        logging.info("position-sync: updated position %s/%s[%s] size=%s price=%s", account.id, symbol, pside, size, db_pos.current_price)
                    else:
                        if not is_active:
                            # no active net position -> nothing to create
                            continue
                        # create a new position - ensure position_side gets stored
                        new_pos = Position(
                            account_id=account.id,
                            symbol=symbol,
                            size=size,
                            entry_price=entry_price,
                            current_price=mark_price,
                            unrealized_pnl=unrealized,
                            leverage=leverage,
                            risk_level=RiskLevelEnum.LOW,
                            is_active=is_active,
                            position_side=pside,
                        )
                        db.add(new_pos)
                        db.commit()
                        db.refresh(new_pos)
                        await ws_manager.broadcast({
                            "type": "position_update",
                            "data": {
                                "id": new_pos.id,
                                "account_id": new_pos.account_id,
                                "symbol": new_pos.symbol,
                                "position_side": new_pos.position_side,
                                "size": new_pos.size,
                                "entry_price": new_pos.entry_price,
                                "current_price": new_pos.current_price,
                                "unrealized_pnl": new_pos.unrealized_pnl,
                                "risk_level": getattr(new_pos.risk_level, 'value', str(new_pos.risk_level)),
                                "is_active": new_pos.is_active,
                                "updated_at": new_pos.updated_at.isoformat() if new_pos.updated_at else None,
                            }
                        })
                        logging.info("position-sync: created position %s/%s[%s] size=%s price=%s", account.id, symbol, pside, size, new_pos.current_price)

                except Exception:
                    logging.exception("position-sync: error upserting consolidated position %s for account %s", symbol, account.id)

            # Deactivate positions that are no longer in Binance response
            try:
                active_in_db = db.query(Position).filter(
                    Position.account_id == account.id,
                    Position.is_active == True
                ).all()
                for pos in active_in_db:
                    key = (pos.symbol, (pos.position_side or "NET").upper())
                    if key not in updated_keys:
                        pos.is_active = False
                        pos.size = 0.0
                        pos.unrealized_pnl = 0.0
                        db.add(pos)
                        
                        # Broadcast deactivation
                        await ws_manager.broadcast({
                            "type": "position_update",
                            "data": {
                                "id": pos.id,
                                "account_id": pos.account_id,
                                "symbol": pos.symbol,
                                "position_side": pos.position_side,
                                "size": 0.0,
                                "is_active": False,
                                "updated_at": datetime.utcnow().isoformat()
                            }
                        })
                        logging.info("position-sync: deactivating position %s/%s[%s] (not in Binance response)", account.id, pos.symbol, pos.position_side)
                db.commit()
            except Exception:
                logging.exception("position-sync: error deactivating stale positions for account %s", account.id)

        finally:
            db.close()

    async def _sync_all(self):
        db = SessionLocal()
        try:
            accounts = db.query(Account).filter(Account.is_active == True).all()
        finally:
            db.close()

        # fetch positions concurrently for each account
        async def _for_account(a):
            try:
                await self._sync_account(a)
            except Exception:
                logging.exception("position-sync: failed sync for account %s", getattr(a, 'id', None))

        tasks = [asyncio.create_task(_for_account(a)) for a in accounts]
        if tasks:
            await asyncio.gather(*tasks)
        
        self._history_sync_counter += 1

    async def _sync_history(self, account, adapter, db):
        """Internal method to sync history for an account during the regular sync loop."""
        from app.models.risk_control import TransactionHistory
        from datetime import datetime
        
        logging.info("position-sync: syncing history for account %s", account.id)
        try:
            # Clean up old trade-level records (T_ prefix) if any exist
            db.query(TransactionHistory).filter(
                TransactionHistory.account_id == account.id,
                TransactionHistory.transaction_id.like('T_%')
            ).delete(synchronize_session=False)
            db.commit()

            income_history = await adapter.fetch_income_history(limit=50)
            user_trades = await adapter.fetch_user_trades(limit=50)
            
            count = 0
            if income_history:
                for item in income_history:
                    tran_id = item.get('tranId')
                    if not tran_id: continue
                    exists = db.query(TransactionHistory).filter(TransactionHistory.transaction_id == str(tran_id)).first()
                    if not exists:
                        db_item = TransactionHistory(
                            account_id=account.id,
                            symbol=item.get('symbol'),
                            type=item.get('incomeType'),
                            realized_pnl=float(item.get('income')),
                            commission_asset=item.get('asset'),
                            time=datetime.utcfromtimestamp(item.get('time') / 1000),
                            transaction_id=str(tran_id)
                        )
                        db.add(db_item)
                        count += 1

            if user_trades:
                # Aggregate trades by orderId
                aggregated_trades = {}
                for trade in user_trades:
                    oid = str(trade.get('orderId'))
                    if not oid: continue
                    
                    if oid not in aggregated_trades:
                        aggregated_trades[oid] = {
                            'symbol': trade.get('symbol'),
                            'side': trade.get('side'),
                            'price_sum': float(trade.get('price', 0)) * float(trade.get('qty', 0)),
                            'qty': float(trade.get('qty', 0)),
                            'quote_qty': float(trade.get('quoteQty', 0)),
                            'commission': float(trade.get('commission', 0)),
                            'commission_asset': trade.get('commissionAsset'),
                            'realized_pnl': float(trade.get('realizedPnl', 0)),
                            'time': trade.get('time')
                        }
                    else:
                        item = aggregated_trades[oid]
                        item['price_sum'] += float(trade.get('price', 0)) * float(trade.get('qty', 0))
                        item['qty'] += float(trade.get('qty', 0))
                        item['quote_qty'] += float(trade.get('quoteQty', 0))
                        item['commission'] += float(trade.get('commission', 0))
                        item['realized_pnl'] += float(trade.get('realizedPnl', 0))
                        item['time'] = max(item['time'], trade.get('time'))

                for oid, data in aggregated_trades.items():
                    global_id = f"ORDER_{oid}"
                    exists = db.query(TransactionHistory).filter(TransactionHistory.transaction_id == global_id).first()
                    
                    avg_price = data['price_sum'] / data['qty'] if data['qty'] > 0 else 0
                    
                    if not exists:
                        db_item = TransactionHistory(
                            account_id=account.id,
                            symbol=data['symbol'],
                            type="TRADE",
                            side=data['side'],
                            price=avg_price,
                            qty=data['qty'],
                            quote_qty=data['quote_qty'],
                            commission=data['commission'],
                            commission_asset=data['commission_asset'],
                            realized_pnl=data['realized_pnl'],
                            time=datetime.utcfromtimestamp(data['time'] / 1000),
                            order_id=oid,
                            transaction_id=global_id
                        )
                        db.add(db_item)
                        count += 1
                    else:
                        # Update existing aggregated record if data changed
                        exists.price = avg_price
                        exists.qty = data['qty']
                        exists.quote_qty = data['quote_qty']
                        exists.commission = data['commission']
                        exists.realized_pnl = data['realized_pnl']
                        exists.time = datetime.utcfromtimestamp(data['time'] / 1000)
                        db.add(exists)
            
            if count > 0:
                db.commit()
                logging.info("position-sync: synced %s new history items for account %s", count, account.id)
        except Exception:
            logging.exception("position-sync: error syncing history for account %s", account.id)
            db.rollback()

    async def poller(self):
        self._running = True
        logging.info("position-sync: poller started (interval=%s)", self.interval)
        while self._running:
            try:
                await self._sync_all()
            except Exception:
                logging.exception("position-sync: unexpected polling error")
            await asyncio.sleep(self.interval)

    async def sync_once(self):
        """Run a single sync pass (useful for triggered/manual sync)."""
        await self._sync_all()

    def start(self):
        if self._task is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()

            logging.info("position-sync: scheduling background sync task (loop=%s)", loop)
            self._task = loop.create_task(self.poller())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


def get_position_sync_from_env() -> PositionSyncService:
    interval = int(os.getenv("POSITION_SYNC_INTERVAL", "30"))
    return PositionSyncService(interval=interval)
