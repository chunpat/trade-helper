import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
import mysql.connector
from sqlalchemy import create_engine
from app.core.database import init_db, DATABASE_URL

def create_database():
    """Create the database if it doesn't exist"""
    load_dotenv()

    DB_NAME = os.getenv("DB_NAME", "trade_helper")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")

    try:
        # Connect to MySQL server
        conn = mysql.connector.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        
        cursor = conn.cursor()

        # Create database if it doesn't exist
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"Database {DB_NAME} created or already exists.")

        cursor.close()
        conn.close()

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        sys.exit(1)

def init_tables():
    """Initialize database tables"""
    print("Initializing database tables...")
    try:
        # Create database engine
        engine = create_engine(DATABASE_URL)
        
        # Initialize database tables
        init_db()
        
        print("Database tables initialized successfully!")
        return True
    except Exception as e:
        print(f"Error initializing database tables: {str(e)}")
        return False

def create_default_config():
    """Create default risk control configuration"""
    from app.models.risk_control import Account, RiskConfig
    from sqlalchemy.orm import Session
    from app.core.database import SessionLocal

    print("Creating default configuration...")
    try:
        db = SessionLocal()
        
        # Check if default account exists
        default_account = db.query(Account).filter(Account.name == "Default").first()
        
        if not default_account:
            # Create default account
            default_account = Account(
                name="Default",
                exchange="binance",
                api_key="your-api-key",
                api_secret="your-api-secret",
                settings={"test_mode": True}
            )
            db.add(default_account)
            db.commit()
            db.refresh(default_account)
            
            # Create default risk configuration
            default_config = RiskConfig(
                account_id=default_account.id,
                max_leverage=20.0,
                max_position_value=1000000.0,
                risk_ratio_threshold=0.8,
                max_single_order=100000.0,
                price_deviation_limit=0.05,
                order_frequency_limit=10,
                max_daily_loss=50000.0,
                risk_level_threshold=0.9,
                is_active=True
            )
            db.add(default_config)
            db.commit()
            
            print("Default configuration created successfully!")
        else:
            print("Default configuration already exists.")
            
    except Exception as e:
        print(f"Error creating default configuration: {str(e)}")
    finally:
        db.close()

def main():
    """Main initialization function"""
    print("Starting database initialization...")
    
    # Create database
    create_database()
    
    # Initialize tables
    if init_tables():
        # Create default configuration
        create_default_config()
    
    print("Database initialization completed!")

if __name__ == "__main__":
    main()
