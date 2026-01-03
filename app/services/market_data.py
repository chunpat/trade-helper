import asyncio
import logging
import os
from typing import List

import httpx

from app.core.database import SessionLocal
from app.models.risk_control import Position, RiskConfig, TickerHistory
from datetime import datetime
from app.services.risk_control_service import RiskControlService
from app.services.ws_broadcast import manager as ws_manager


class MarketDataService:
    """Simple market-data poller that fetches ticker prices and updates Positions.

    - Uses Binance REST public endpoint for price (no API key required for ticker price)
    - Updates Position.current_price and unrealized_pnl, and recalculates risk_level
    """

    BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    BINANCE_FAPI_TICKER = "https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"

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

        # Prefer the futures (fapi) ticker for perpetual/symbols that may be futures-only.
        # Fall back to the spot endpoint if fapi returns invalid symbol / 400.
        fapi_url = self.BINANCE_FAPI_TICKER.format(symbol=sym)
        spot_url = self.BINANCE_TICKER.format(symbol=sym)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # try fapi first
                r = await client.get(fapi_url)
                if r.status_code == 200:
                    data = r.json()
                    return float(data.get("price"))

                # if fapi says invalid symbol, try spot as a fallback
                if r.status_code == 400 and r.text and 'Invalid symbol' in r.text:
                    logging.debug("market-data: futures API returned Invalid symbol for %s, trying spot endpoint", sym)
                    try:
                        r2 = await client.get(spot_url)
                        if r2.status_code == 200:
                            data = r2.json()
                            return float(data.get("price"))
                    except Exception:
                        pass

                # if fapi returned something else (not 200), attempt spot too as a safeguard
                try:
                    r2 = await client.get(spot_url)
                    if r2.status_code == 200:
                        data = r2.json()
                        return float(data.get("price"))
                except Exception:
                    pass
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

            # persist a ticker history record for auditing / history
            try:
                ticker = TickerHistory(
                    symbol=position.symbol,
                    price=price,
                    timestamp=datetime.utcnow(),
                    source=os.getenv("MARKET_DATA_SOURCE", "binance"),
                    position_id=position.id,
                    account_id=position.account_id,
                )
                db.add(ticker)
            except Exception:
                logging.exception("market-data: failed to create ticker history record")

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
            logging.debug("market-data: no active positions found")
            return

        # fetch prices concurrently (attach position id to each fetch result)
        async def _fetch_with_id(pid: int, symbol: str):
            price = await self.fetch_price(symbol)
            return pid, price

        tasks = [asyncio.create_task(_fetch_with_id(p.id, p.symbol)) for p in positions]

        for task in asyncio.as_completed(tasks):
            try:
                pid, price = await task
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
            except Exception as e:
                logging.exception("market-data: error handling task for pid=%s", pid)
                # ignore per-position errors but log them
                continue

    async def poller(self):
        self._running = True
        logging.info("market-data: poller started (interval=%s)", self.poll_interval)
        while self._running:
            try:
                await self._poll_once()
            except Exception:
                # keep polling even if errors occur
                pass
            await asyncio.sleep(self.poll_interval)

    def start(self):
        if self._task is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()

            logging.info("market-data: scheduling background poller task (loop=%s)", loop)
            self._task = loop.create_task(self.poller())
            # schedule an immediate poll once so we don't wait for the first interval
            try:
                loop.create_task(self._poll_once())
                logging.info("market-data: scheduled immediate first poll")
            except Exception:
                logging.exception("market-data: failed to schedule immediate poll")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


def get_poller_from_env() -> MarketDataService:
    interval = int(os.getenv("MARKET_POLL_INTERVAL", "10"))
    return MarketDataService(poll_interval=interval)
