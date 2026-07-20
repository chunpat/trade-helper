# AGENTS.md

This is a digital currency futures trading risk-control and monitoring system (数字货币合约交易风控系统). It is a monitoring and decision-support platform, NOT an automated trading bot.

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 1.4+ (MySQL 8.0), Redis 6+, JWT dual-token auth (python-jose + passlib)
- **Frontend:** Vue 3 (Composition API), Vuex 4, Vue Router 4, Element Plus, ECharts 5, Vite 4
- **Infrastructure:** Docker Compose (5 services: backend, frontend, mysql, redis, nginx)

## Directory Structure

```
trade-helper/
├── app/                         # Backend (FastAPI)
│   ├── api/v1/                  # Route modules (auth, market, market_insight, risk_control, dashboard)
│   ├── core/                    # database.py, deps.py, security.py
│   ├── models/                  # SQLAlchemy models (12 tables + mixins)
│   ├── schemas/                 # Pydantic request/response schemas
│   └── services/                # Business logic (risk_control, position_sync, anomaly_monitor, market_data, news, trade_review, etc.)
│       └── exchange/            # Exchange adapters (binance_adapter.py, okx_adapter.py)
├── frontend/                    # Vue 3 SPA
│   └── src/
│       ├── api/index.js         # Axios client with JWT auto-refresh interceptors
│       ├── views/               # Page components (Dashboard, Positions, TradeReview, RiskAlerts, MarketInsight, etc.)
│       ├── store/index.js       # Vuex store
│       ├── router/index.js      # Vue Router with auth guards
│       └── services/wsClient.js # WebSocket client for real-time updates
├── tests/                       # pytest test suite (18 files, flat structure)
├── scripts/                     # Utility scripts (db init, backfill, admin creation, ws testing)
├── main.py                      # FastAPI app entry point
├── docker-compose.yml
└── requirements.txt
```

## Commands

```bash
# Backend
uvicorn main:app --reload --port 8029          # Dev server
pytest tests/ -v                                 # Run all tests
pytest tests/test_risk_control_service.py -v     # Run specific test file
pip install -r requirements.txt                  # Install deps

# Frontend
cd frontend && npm run dev                       # Dev server (port 8030)
cd frontend && npm run build                     # Production build
cd frontend && npm run lint                      # ESLint

# Docker
docker compose up -d                             # Start all services
docker compose logs -f backend                   # Follow backend logs
```

## Architecture

### Dual-Role Backend

The backend supports split deployments via env vars:
- **API/WebSocket/Poller role:** `START_MARKET_POLLER=true`, `START_POSITION_SYNC=true`, `START_ANOMALY_MONITOR=false`
- **Insight-worker role:** `START_ANOMALY_MONITOR=true` (anomaly scanning + news ingestion)

### Service Pattern

- Services in `app/services/` are stateless classes or module-level singletons
- DB sessions are short-lived: `SessionLocal()` created per operation with try/finally cleanup
- Exchange adapters in `app/services/exchange/` implement a common interface (HMAC-signed REST calls, position normalization)
- `ws_broadcast.py`: WebSocket connection manager singleton broadcasting real-time updates

### Key Service Flows

1. **Position sync** (`position_sync.py`): Periodic polling of Binance/OKX futures → position normalization → DB upsert → WebSocket broadcast
2. **Market data** (`market_data.py`): Price polling → DB update → WebSocket broadcast
3. **Anomaly detection** (`anomaly_monitor_service.py`): Scans top-100 Binance USDT tickers every 5min, multi-factor scoring, news correlation
4. **News** (`news_service.py`): Multi-source (exchange announcements, RSS, CryptoPanic) → archive → analysis

## Coding Conventions

### Python
- **Imports:** stdlib → third-party → local (isort-compatible)
- **Type hints:** `Optional`, `List`, `Dict`, `Any` used throughout (Python 3.8+ style)
- **Async:** Nearly all services use `async def` + `httpx.AsyncClient` + `asyncio.create_task`
- **Logging:** `logging.getLogger(__name__)` per module; info/exception/debug levels
- **Error handling:** Defensive try/except in loops, log and continue rather than crash
- **Models:** `BaseMixin` (id, created_at, updated_at) and `TimestampMixin` used as SQLAlchemy base classes
- **Config:** `os.getenv()` with defaults; boolean env vars parsed via `_read_bool_env` helper

### Testing
- **Framework:** pytest + pytest-asyncio
- **Mocks:** `types.SimpleNamespace` for lightweight objects, `monkeypatch` for async method overrides
- **No shared fixtures/conftest** — tests are self-contained
- **File naming:** `tests/test_<module>.py`

### Frontend
- **API client:** `api/index.js` with axios interceptors that proactively refresh JWT 90s before expiry
- **State:** Vuex store with `modules` pattern
- **Real-time:** `wsClient.js` for position/price WebSocket updates
- **Charts:** ECharts for dashboards, lightweight-charts for K-line

### General
- Comments and user-facing messages are in Chinese
- No Alembic migrations — schema changes via `ALTER TABLE` in `scripts/init_db.py`

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | MySQL connection |
| `REDIS_HOST`, `REDIS_PORT` | Redis connection |
| `START_MARKET_POLLER` | Enable price polling background task |
| `START_POSITION_SYNC` | Enable position sync background task |
| `START_ANOMALY_MONITOR` | Enable anomaly scanning + news worker |
| `ENABLE_GPT_5_1` | Enable LLM market analysis |
| `ANOMALY_LLM_PROVIDER` | LLM provider for anomaly analysis |
| `NEWS_PROVIDER` | News source selection (`auto`, `cryptopanic`) |
