from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Database URL construction
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "trade_helper")

# Use pymysql as the MySQL driver
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create database engine with MySQL-specific configuration
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Enable automatic reconnection
    pool_size=5,         # Set connection pool size
    max_overflow=10,     # Maximum number of connections that can be created beyond pool_size
    pool_recycle=3600,   # Recycle connections after 1 hour
    connect_args={
        "charset": os.getenv("DB_CHARSET", "utf8mb4")
    }
)

# Create SessionLocal class for database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Generator function to get database session.
    Usage:
        @app.get("/")
        def read_item(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Function to initialize database
def init_db():
    """
    Initialize database with all models.
    Should be called when application starts.
    """
    from app.models.base import Base
    from app.models.risk_control import (
        Account,
        RefreshToken,
        RiskConfig,
        Position,
        RiskAlert,
        OrderLog,
        TickerHistory,
        DailyTradeReview,
    )
    from app.models.market_anomaly import (
        MarketMetricSnapshot,
        AnomalyEvent,
        AnomalyNews,
        NarrativeEvent,
        NewsArchive,
    )
    from app.models.polymarket_cache import PolymarketCacheEntry
    from app.models.notification import NotificationChannelConfig, NotificationDeliveryLog
    from app.models.polymarket_copy import (
        PolymarketCopySignalLog,
        PolymarketCopySimulationRun,
        PolymarketCopySourcePosition,
        PolymarketCopyStrategy,
    )
    
    Base.metadata.create_all(bind=engine)

    # create_all 不会给已有表补字段，生产升级时需要显式兼容旧的通知配置表。
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            notification_columns = {
                "keyword": (
                    "ALTER TABLE notification_channel_configs "
                    "ADD COLUMN keyword VARCHAR(64) NOT NULL DEFAULT 'TradeHelper'"
                ),
                "market_alert_preset": (
                    "ALTER TABLE notification_channel_configs "
                    "ADD COLUMN market_alert_preset VARCHAR(32) NOT NULL DEFAULT 'balanced'"
                ),
                "market_news_analysis_enabled": (
                    "ALTER TABLE notification_channel_configs "
                    "ADD COLUMN market_news_analysis_enabled BOOLEAN NOT NULL DEFAULT TRUE"
                ),
                "market_min_score": (
                    "ALTER TABLE notification_channel_configs "
                    "ADD COLUMN market_min_score DOUBLE NOT NULL DEFAULT 60.0"
                ),
                "market_cooldown_minutes": (
                    "ALTER TABLE notification_channel_configs "
                    "ADD COLUMN market_cooldown_minutes INT NOT NULL DEFAULT 60"
                ),
            }
            for column_name, alter_sql in notification_columns.items():
                res = conn.execute(
                    text(
                        "SHOW COLUMNS FROM notification_channel_configs "
                        f"LIKE '{column_name}'"
                    )
                )
                if res.first() is None:
                    conn.execute(text(alter_sql))

            res = conn.execute(
                text(
                    "SHOW COLUMNS FROM notification_delivery_logs "
                    "LIKE 'context_payload'"
                )
            )
            if res.first() is None:
                conn.execute(
                    text(
                        "ALTER TABLE notification_delivery_logs "
                        "ADD COLUMN context_payload JSON DEFAULT NULL"
                    )
                )
    except Exception:
        import logging
        logging.exception("init_db: failed to update notification config columns (ignored)")

    # Ensure new column position_side exists for positions table (safe alter for development)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            def ensure_index(table_name: str, index_name: str, create_sql: str) -> None:
                res = conn.execute(text(f"SHOW INDEX FROM {table_name} WHERE Key_name = :index_name"), {"index_name": index_name})
                if res.first() is not None:
                    return
                import logging
                logging.info("init_db: %s missing, attempting to create it", index_name)
                conn.execute(text(create_sql))

            # check whether column exists
            res = conn.execute(text("SHOW COLUMNS FROM positions LIKE 'position_side'"))
            exists = res.first() is not None
            if not exists:
                import logging
                logging.info("init_db: position_side column missing, attempting to add it")
                # Try a modern ALTER with IF NOT EXISTS first (MySQL 8+). If that fails
                # we'll fall back to the older ALTER TABLE form.
                try:
                    conn.execute(text("ALTER TABLE positions ADD COLUMN IF NOT EXISTS position_side VARCHAR(10) DEFAULT NULL"))
                    logging.info("init_db: ALTER TABLE with IF NOT EXISTS executed")
                except Exception as e:
                    logging.info("init_db: ALTER TABLE IF NOT EXISTS failed — trying plain ALTER; error=%s", e)
                    conn.execute(text("ALTER TABLE positions ADD COLUMN position_side VARCHAR(10) DEFAULT NULL"))
                    logging.info("init_db: plain ALTER TABLE executed")
    except Exception:
        # best-effort only; do not fail startup if alter fails
        import logging
        logging.exception("init_db: failed to add position_side column (ignored)")

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("SHOW COLUMNS FROM transaction_history LIKE 'position_side'"))
            exists = res.first() is not None
            if not exists:
                import logging
                logging.info("init_db: transaction_history.position_side missing, attempting to add it")
                try:
                    conn.execute(text("ALTER TABLE transaction_history ADD COLUMN IF NOT EXISTS position_side VARCHAR(10) DEFAULT NULL"))
                except Exception as e:
                    logging.info("init_db: ALTER transaction_history IF NOT EXISTS failed — trying plain ALTER; error=%s", e)
                    conn.execute(text("ALTER TABLE transaction_history ADD COLUMN position_side VARCHAR(10) DEFAULT NULL"))
    except Exception:
        import logging
        logging.exception("init_db: failed to add transaction_history.position_side column (ignored)")

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("SHOW COLUMNS FROM transaction_history LIKE 'leverage'"))
            exists = res.first() is not None
            if not exists:
                import logging
                logging.info("init_db: transaction_history.leverage missing, attempting to add it")
                try:
                    conn.execute(text("ALTER TABLE transaction_history ADD COLUMN IF NOT EXISTS leverage DOUBLE DEFAULT NULL"))
                except Exception as e:
                    logging.info("init_db: ALTER transaction_history leverage IF NOT EXISTS failed — trying plain ALTER; error=%s", e)
                    conn.execute(text("ALTER TABLE transaction_history ADD COLUMN leverage DOUBLE DEFAULT NULL"))
    except Exception:
        import logging
        logging.exception("init_db: failed to add transaction_history.leverage column (ignored)")

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("SHOW COLUMNS FROM accounts LIKE 'api_passphrase'"))
            exists = res.first() is not None
            if not exists:
                import logging
                logging.info("init_db: accounts.api_passphrase missing, attempting to add it")
                try:
                    conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS api_passphrase VARCHAR(255) DEFAULT NULL"))
                except Exception as e:
                    logging.info("init_db: ALTER accounts IF NOT EXISTS failed — trying plain ALTER; error=%s", e)
                    conn.execute(text("ALTER TABLE accounts ADD COLUMN api_passphrase VARCHAR(255) DEFAULT NULL"))
    except Exception:
        import logging
        logging.exception("init_db: failed to add accounts.api_passphrase column (ignored)")

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("SHOW COLUMNS FROM accounts LIKE 'history_90d_backfilled_at'"))
            exists = res.first() is not None
            if not exists:
                import logging
                logging.info("init_db: accounts.history_90d_backfilled_at missing, attempting to add it")
                try:
                    conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS history_90d_backfilled_at DATETIME DEFAULT NULL"))
                except Exception as e:
                    logging.info("init_db: ALTER accounts history_90d_backfilled_at IF NOT EXISTS failed — trying plain ALTER; error=%s", e)
                    conn.execute(text("ALTER TABLE accounts ADD COLUMN history_90d_backfilled_at DATETIME DEFAULT NULL"))
    except Exception:
        import logging
        logging.exception("init_db: failed to add accounts.history_90d_backfilled_at column (ignored)")

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("SHOW COLUMNS FROM daily_trade_reviews LIKE 'linked_orders'"))
            exists = res.first() is not None
            if not exists:
                import logging
                logging.info("init_db: daily_trade_reviews.linked_orders missing, attempting to add it")
                try:
                    conn.execute(text("ALTER TABLE daily_trade_reviews ADD COLUMN IF NOT EXISTS linked_orders JSON DEFAULT NULL"))
                except Exception as e:
                    logging.info("init_db: ALTER daily_trade_reviews linked_orders IF NOT EXISTS failed — trying plain ALTER; error=%s", e)
                    conn.execute(text("ALTER TABLE daily_trade_reviews ADD COLUMN linked_orders JSON DEFAULT NULL"))
    except Exception:
        import logging
        logging.exception("init_db: failed to add daily_trade_reviews.linked_orders column (ignored)")

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            def ensure_index(table_name: str, index_name: str, create_sql: str) -> None:
                res = conn.execute(text(f"SHOW INDEX FROM {table_name} WHERE Key_name = :index_name"), {"index_name": index_name})
                if res.first() is not None:
                    return
                import logging
                logging.info("init_db: %s missing, attempting to create it", index_name)
                conn.execute(text(create_sql))

            ensure_index(
                "transaction_history",
                "ix_transaction_history_type_time_id",
                "CREATE INDEX ix_transaction_history_type_time_id ON transaction_history (type, time, id)",
            )
            ensure_index(
                "transaction_history",
                "ix_transaction_history_account_type_time_id",
                "CREATE INDEX ix_transaction_history_account_type_time_id ON transaction_history (account_id, type, time, id)",
            )
            ensure_index(
                "transaction_history",
                "ix_transaction_history_type_account_symbol_time_id",
                "CREATE INDEX ix_transaction_history_type_account_symbol_time_id ON transaction_history (type, account_id, symbol, time, id)",
            )
            ensure_index(
                "ticker_history",
                "ix_ticker_history_account_symbol_timestamp_id",
                "CREATE INDEX ix_ticker_history_account_symbol_timestamp_id ON ticker_history (account_id, symbol, timestamp, id)",
            )
            ensure_index(
                "account_snapshots",
                "ix_account_snapshots_account_timestamp_id",
                "CREATE INDEX ix_account_snapshots_account_timestamp_id ON account_snapshots (account_id, timestamp, id)",
            )
    except Exception:
        import logging
        logging.exception("init_db: failed to create history query indexes (ignored)")
