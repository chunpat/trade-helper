import sys
import os

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

def add_columns():
    with engine.connect() as conn:
        # Check if columns exist
        result = conn.execute(text("SHOW COLUMNS FROM accounts LIKE 'total_equity'"))
        if not result.fetchone():
            print("Adding total_equity column...")
            conn.execute(text("ALTER TABLE accounts ADD COLUMN total_equity FLOAT DEFAULT 0.0"))
        
        result = conn.execute(text("SHOW COLUMNS FROM accounts LIKE 'total_balance'"))
        if not result.fetchone():
            print("Adding total_balance column...")
            conn.execute(text("ALTER TABLE accounts ADD COLUMN total_balance FLOAT DEFAULT 0.0"))
            
        result = conn.execute(text("SHOW COLUMNS FROM accounts LIKE 'today_pnl'"))
        if not result.fetchone():
            print("Adding today_pnl column...")
            conn.execute(text("ALTER TABLE accounts ADD COLUMN today_pnl FLOAT DEFAULT 0.0"))
            
        conn.commit()
        print("Columns added successfully or already exist.")

if __name__ == "__main__":
    add_columns()
