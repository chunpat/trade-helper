import asyncio
import logging
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Load environment variables before importing singleton services.
load_dotenv()

from app.core.database import init_db
from app.services.anomaly_monitor_service import anomaly_monitor_service


logging.basicConfig(level=logging.INFO)


async def main() -> None:
    init_db()
    anomaly_monitor_service.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logging.info("anomaly-worker: started")
    try:
        await stop_event.wait()
    finally:
        anomaly_monitor_service.stop()
        logging.info("anomaly-worker: stopped")


if __name__ == "__main__":
    asyncio.run(main())