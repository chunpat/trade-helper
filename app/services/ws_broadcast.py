import asyncio
import json
import logging
import time
from typing import Set

from fastapi import HTTPException
from jose import JWTError
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal
from app.core.deps import get_current_user
from app.core.security import decode_token
from app.models.risk_control import Account


def authenticate_token(token):
    db = SessionLocal()
    try:
        user = get_current_user(token=token, db=db)
        return {"id": user.id, "is_admin": user.is_admin, "expires_at": decode_token(token)["exp"]}
    finally:
        db.close()


def account_owner(account_id):
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        return (account is not None, account.user_id if account else None)
    finally:
        db.close()


class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.identities = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        # 首帧认证，避免令牌出现在 URL 和代理访问日志中。
        try:
            message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            if not isinstance(message, dict) or message.get("type") != "auth" or not isinstance(message.get("token"), str):
                raise ValueError("缺少身份凭证")
            identity = await asyncio.to_thread(authenticate_token, message["token"])
        except WebSocketDisconnect:
            return False
        except (HTTPException, JWTError, ValueError, KeyError, asyncio.TimeoutError):
            await websocket.close(code=1008)
            return False
        logging.info("ws: new connection incoming")
        async with self._lock:
            self.active_connections.add(websocket)
            self.identities[websocket] = identity
            logging.info("ws: connections=%d", len(self.active_connections))
        return True

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                self.identities.pop(websocket, None)
                logging.info("ws: disconnected, connections=%d", len(self.active_connections))

    async def broadcast(self, message: dict):
        owner_id = None
        if message.get("type") == "position_update":
            account_id = (message.get("data") or {}).get("account_id")
            if account_id is None:
                return
            exists, owner_id = await asyncio.to_thread(account_owner, account_id)
            if not exists:
                return
        elif message.get("type") not in {"heartbeat", "server_shutdown"}:
            # 新增私人消息类型时必须先定义归属，默认不广播。
            return
        data = json.dumps(message)
        # snapshot to avoid iteration changes
        async with self._lock:
            conns = list(self.active_connections)

        logging.info("ws: broadcasting message type=%s to %d connections", message.get('type'), len(conns))
        for ws in conns:
            try:
                identity = self.identities.get(ws)
                if not identity or identity["expires_at"] <= time.time():
                    await ws.close(code=1008)
                    await self.disconnect(ws)
                    continue
                if message.get("type") == "position_update" and not (
                    identity["id"] == owner_id or (owner_id is None and identity["is_admin"])
                ):
                    continue
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
