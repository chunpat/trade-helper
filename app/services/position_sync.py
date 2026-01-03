import asyncio
import logging
import os
from typing import List, Dict

from app.core.database import SessionLocal
from app.services.exchange.binance_adapter import create_adapter_for_account
from app.services.ws_broadcast import manager as ws_manager
from app.services.risk_control_service import RiskControlService
from app.models.risk_control import Account, Position, RiskConfig, RiskLevelEnum
from sqlalchemy.exc import OperationalError


class PositionSyncService:
    def __init__(self, interval: int = 30):
        self.interval = interval
        self._task = None
        self._running = False

    async def _sync_account(self, account: Account):
        adapter = create_adapter_for_account(account)
        if not adapter:
            logging.debug("position-sync: account %s missing API credentials", account.id)
            return

        rows = await adapter.fetch_positions()
        if rows is None:
            logging.debug("position-sync: no position data for account %s", account.id)
            return
        logging.info("position-sync: received %s position rows for account %s", len(rows), account.id)

        # upsert positions
        db = SessionLocal()
        try:
            # aggregate Binance rows by (symbol, positionSide) so LONG and SHORT are separate
            by_symbol = {}
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
            for (symbol, pside), info in by_symbol.items():
                try:
                    net_amt = info['net_amt']
                    size = abs(net_amt)
                    is_active = abs(net_amt) > 1e-12
                    entry_price = info['entry_price'] or 0.0
                    mark_price = info['mark_price']
                    unrealized = info['unrealized']
                    leverage = info.get('leverage', 1.0)

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
                                "symbol": db_pos.symbol,
                                "current_price": db_pos.current_price,
                                "unrealized_pnl": db_pos.unrealized_pnl,
                                "risk_level": getattr(db_pos.risk_level, 'value', str(db_pos.risk_level)),
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
                                "symbol": new_pos.symbol,
                                "current_price": new_pos.current_price,
                                "unrealized_pnl": new_pos.unrealized_pnl,
                                "risk_level": getattr(new_pos.risk_level, 'value', str(new_pos.risk_level)),
                                "updated_at": new_pos.updated_at.isoformat() if new_pos.updated_at else None,
                            }
                        })
                        logging.info("position-sync: created position %s/%s[%s] size=%s price=%s", account.id, symbol, pside, size, new_pos.current_price)

                except Exception:
                    logging.exception("position-sync: error upserting consolidated position %s for account %s", symbol, account.id)

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
