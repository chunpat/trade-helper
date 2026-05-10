import asyncio
import logging
import os
from typing import Optional

from app.schemas.polymarket_copy import PolymarketCopyRunnerStatus
from app.services.polymarket_copy_service import PolymarketCopyService, polymarket_copy_service


logger = logging.getLogger(__name__)


class PolymarketCopyRunnerService:
    def __init__(
        self,
        copy_service: Optional[PolymarketCopyService] = None,
        interval_seconds: Optional[int] = None,
    ):
        self.copy_service = copy_service or polymarket_copy_service
        self.interval_seconds = interval_seconds or int(os.getenv("POLYMARKET_COPY_RUNNER_INTERVAL", "15"))
        self._task = None
        self._running = False

    async def poller(self) -> None:
        self._running = True
        logger.info("polymarket-copy-runner: started interval=%s", self.interval_seconds)
        while self._running:
            strategy_ids = self.copy_service.list_running_strategy_ids()
            for strategy_id in strategy_ids:
                try:
                    await self.copy_service.run_strategy_cycle(strategy_id)
                except Exception as exc:
                    logger.exception("polymarket-copy-runner: failed strategy_id=%s", strategy_id)
                    try:
                        self.copy_service.record_strategy_error(strategy_id, str(exc))
                    except Exception:
                        logger.exception("polymarket-copy-runner: failed to record strategy error strategy_id=%s", strategy_id)
            await asyncio.sleep(self.interval_seconds)

    def start(self) -> None:
        if self._task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.poller())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    def get_status(self) -> PolymarketCopyRunnerStatus:
        strategy_count = len(self.copy_service.list_running_strategy_ids())
        return PolymarketCopyRunnerStatus(
            running=self._running,
            interval_seconds=self.interval_seconds,
            strategy_count=strategy_count,
        )


polymarket_copy_runner_service = PolymarketCopyRunnerService()