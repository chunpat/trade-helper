import asyncio
import logging
import os
from typing import List

import httpx

from app.core.database import SessionLocal
from app.models.risk_control import Position, RiskConfig
from app.services.risk_control_service import RiskControlService
from app.services.ws_broadcast import manager as ws_manager


class MarketDataService:
    """Simple market-data poller that fetches ticker prices and updates Positions.

    - Uses Binance REST public endpoint for price (no API key required for ticker price)
    - Updates Position.current_price and unrealized_pnl, and recalculates risk_level
    """

    BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price?symbol={symbol}"

    def __init__(self, poll_interval: int = 10):
        self.poll_interval = poll_interval
        self._task = None
        self._running = False

    async def fetch_price(self, symbol: str) -> float | None:
        # Binance expects uppercase symbol like BTCUSDT; support formats like BTC/USDT
        if "/" in symbol:
            sym = symbol.replace("/", "")
        else:
            sym = symbol
        sym = sym.upper()

        url = self.BINANCE_TICKER.format(symbol=sym)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    return float(data.get("price"))
        except Exception:
            # swallow temporary network errors, return None
            return None

        return None

    def _get_active_positions(self) -> List[Position]:
        db = SessionLocal()
        try:
            # load all active positions
            return db.query(Position).filter(Position.is_active == True).all()
        finally:
            db.close()

    def _update_position_sync(self, position_id: int, price: float) -> dict | None:
        db = SessionLocal()
        try:
            position = db.query(Position).filter(Position.id == position_id).first()
            if not position:
                return None

            position.current_price = price
            position.unrealized_pnl = (price - position.entry_price) * position.size

            # recompute risk_level by loading config and using RiskControlService
            risk_config = db.query(RiskConfig).filter(
                RiskConfig.account_id == position.account_id,
                RiskConfig.is_active == True
            ).first()

            if risk_config:
                svc = RiskControlService(db)
                # use the service's calculate_risk_level which expects Position object
                position.risk_level = svc.calculate_risk_level(position, risk_config)

            db.commit()
            db.refresh(position)

            # return a small summary for broadcasting
            return {
                "id": position.id,
                "symbol": position.symbol,
                "current_price": position.current_price,
                "unrealized_pnl": position.unrealized_pnl,
                "risk_level": position.risk_level.value if hasattr(position.risk_level, 'value') else str(position.risk_level),
                "updated_at": position.updated_at.isoformat() if getattr(position, 'updated_at', None) else None,
            }
        finally:
            db.close()

    async def _poll_once(self):
        positions = await asyncio.to_thread(self._get_active_positions)
        if not positions:
            return

        # fetch prices concurrently
        tasks = {asyncio.create_task(self.fetch_price(p.symbol)): p.id for p in positions}

        for task in asyncio.as_completed(tasks.keys()):
            pid = tasks[task]
            try:
                price = await task
                if price is None:
                    logging.debug("market-data: no price for pid=%s", pid)
                    continue
                # update position in DB in threadpool (sync)
                updated = await asyncio.to_thread(self._update_position_sync, pid, price)
                if updated:
                    # broadcast update to connected websocket clients
                    try:
                        await ws_manager.broadcast({"type": "position_update", "data": updated})
                    except Exception:
                        # keep polling even if broadcast fails
                        pass
                logging.info("market-data: updated position %s price=%s", pid, price)
            except Exception:
                # ignore per-position errors
                continue

    async def poller(self):
        self._running = True
        while self._running:
            try:
                await self._poll_once()
            except Exception:
                # keep polling even if errors occur
                pass
            await asyncio.sleep(self.poll_interval)

    def start(self):
        if self._task is None:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self.poller())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


def get_poller_from_env() -> MarketDataService:
    interval = int(os.getenv("MARKET_POLL_INTERVAL", "10"))
    return MarketDataService(poll_interval=interval)
