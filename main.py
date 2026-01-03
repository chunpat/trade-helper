from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn
from dotenv import load_dotenv
import os

from app.core.database import init_db
from app.services.market_data import get_poller_from_env
from app.services.position_sync import get_position_sync_from_env
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
from app.services.ws_broadcast import manager as ws_manager
from app.api.v1 import router as api_router

# Load environment variables
load_dotenv()

app = FastAPI(
    title=os.getenv("APP_NAME", "Trade Helper"),
    description="数字货币合约交易风险管控系统",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# configure basic logging so our service-level logs show up in docker/uvicorn output
logging.basicConfig(level=logging.INFO)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Import and include routers
app.include_router(api_router, prefix=os.getenv("API_PREFIX", "/api/v1"))

# Startup event
@app.on_event("startup")


async def startup_event():
    """Initialize services on startup"""
    # Initialize database
    init_db()
    logging.info("startup: initializing market poller")
    # start market-data poller (background task)
    app.state.market_poller = get_poller_from_env()
    app.state.market_poller.start()
    # start position-sync service for real account positions
    app.state.position_sync = get_position_sync_from_env()
    app.state.position_sync.start()
    # confirm task scheduled
    poller = app.state.market_poller
    logging.info("startup: poller task=%s running=%s", getattr(poller, '_task', None), getattr(poller, '_running', None))
    # ensure websocket manager is available on app state (no-op but explicit)
    app.state.ws_manager = ws_manager

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    # stop market-data poller if running
    poller = getattr(app.state, "market_poller", None)
    if poller:
        poller.stop()
    # stop position sync
    syncer = getattr(app.state, "position_sync", None)
    if syncer:
        syncer.stop()
    # attempt to close any remaining websocket connections
    mgr = getattr(app.state, "ws_manager", None)
    if mgr:
        # best-effort: close connections by sending a shutdown message
        try:
            # Frame a shutdown message and broadcast it
            import asyncio
            asyncio.create_task(mgr.broadcast({"type": "server_shutdown", "data": "server is shutting down"}))
        except Exception:
            pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Simple websocket endpoint for pushing real-time updates to front-end clients.

    This endpoint now runs two cooperating tasks:
    - receiver: awaits any incoming messages from the client (keeps the connection alive and allows graceful disconnect detection)
    - heartbeat: periodically sends a lightweight heartbeat so proxies/load-balancers keep the connection open

    When either task ends (client disconnects or send fails) we make sure to remove the connection.
    """
    await ws_manager.connect(websocket)
    heartbeat_interval = int(os.getenv("WS_HEARTBEAT_INTERVAL", "25"))

    async def _receiver():
        # read any messages client may send; we don't expect messages but reading allows us
        # to detect client-initiated disconnects promptly.
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            # bubble up to outer handler
            raise
        except Exception:
            # ignore other receive errors but let outer handler remove connection
            logging.exception("ws: receiver loop error")
            raise

    async def _heartbeat():
        try:
            while True:
                await asyncio.sleep(heartbeat_interval)
                try:
                    # send a lightweight heartbeat the frontend will ignore
                    await websocket.send_text('{"type":"heartbeat"}')
                except Exception:
                    logging.exception("ws: heartbeat failed for connection")
                    raise
        except asyncio.CancelledError:
            # normal cancellation - ignore
            return

    recv_task = asyncio.create_task(_receiver())
    hb_task = asyncio.create_task(_heartbeat())

    try:
        # keep endpoint alive until either task raises (disconnect) or fails
        done, pending = await asyncio.wait({recv_task, hb_task}, return_when=asyncio.FIRST_EXCEPTION)
        # if any task finished with exception, propagate so we execute the cleanup
        for t in done:
            if t.exception():
                raise t.exception()
    except WebSocketDisconnect:
        # normal disconnect
        logging.info("ws: client disconnected (WebSocketDisconnect)")
    except Exception:
        logging.exception("ws: unexpected error in connection")
    finally:
        # cleanup tasks and remove connection
        for t in (recv_task, hb_task):
            if not t.done():
                t.cancel()
        await ws_manager.disconnect(websocket)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    # Start server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv("ENVIRONMENT") == "development"
    )
