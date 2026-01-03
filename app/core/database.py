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
        RiskConfig,
        Position,
        RiskAlert,
        OrderLog,
        TickerHistory
    )
    
    Base.metadata.create_all(bind=engine)

    # Ensure new column position_side exists for positions table (safe alter for development)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
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
