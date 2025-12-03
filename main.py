from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn
from dotenv import load_dotenv
import os

from app.core.database import init_db
from app.services.market_data import get_poller_from_env
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
    # start market-data poller (background task)
    app.state.market_poller = get_poller_from_env()
    app.state.market_poller.start()

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    # stop market-data poller if running
    poller = getattr(app.state, "market_poller", None)
    if poller:
        poller.stop()

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
