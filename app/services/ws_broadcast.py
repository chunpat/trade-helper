import asyncio
import json
from typing import Set

from starlette.websockets import WebSocket


class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        # snapshot to avoid iteration changes
        async with self._lock:
            conns = list(self.active_connections)

        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                # ignore and remove dead connections
                try:
                    await self.disconnect(ws)
                except Exception:
                    pass


# module-level default manager (singleton)
manager = WebSocketManager()
