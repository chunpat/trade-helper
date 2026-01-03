import asyncio
import json
import logging
from typing import Set

from starlette.websockets import WebSocket


class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        logging.info("ws: new connection incoming")
        async with self._lock:
            self.active_connections.add(websocket)
            logging.info("ws: connections=%d", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                logging.info("ws: disconnected, connections=%d", len(self.active_connections))

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        # snapshot to avoid iteration changes
        async with self._lock:
            conns = list(self.active_connections)

        logging.info("ws: broadcasting message type=%s to %d connections", message.get('type'), len(conns))
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception as exc:
                # log and remove dead connections
                logging.exception("ws: failed to send to connection, removing it: %s", exc)
                try:
                    await self.disconnect(ws)
                except Exception:
                    logging.exception("ws: error while removing dead connection")


# module-level default manager (singleton)
manager = WebSocketManager()
