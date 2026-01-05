import os
import pymysql
from dotenv import load_dotenv

def update_schema():
    load_dotenv()
    
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", 3306))
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    database = os.getenv("DB_NAME", "trade_helper")

    print(f"Connecting to {host}:{port} as {user}...")
    
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        with conn.cursor() as cursor:
            # Check if order_id exists
            cursor.execute("SHOW COLUMNS FROM transaction_history LIKE 'order_id'")
            result = cursor.fetchone()
            
            if not result:
                print("Adding 'order_id' column to 'transaction_history' table...")
                cursor.execute("ALTER TABLE transaction_history ADD COLUMN order_id VARCHAR(100) AFTER time")
                cursor.execute("CREATE INDEX ix_transaction_history_order_id ON transaction_history (order_id)")
                print("Column 'order_id' added successfully.")
            else:
                print("Column 'order_id' already exists.")

            # Check if position_side exists in positions table
            cursor.execute("SHOW COLUMNS FROM positions LIKE 'position_side'")
            result = cursor.fetchone()
            if not result:
                print("Adding 'position_side' column to 'positions' table...")
                cursor.execute("ALTER TABLE positions ADD COLUMN position_side VARCHAR(10) AFTER leverage")
                print("Column 'position_side' added successfully.")
            else:
                print("Column 'position_side' already exists.")
                
            # Create account_snapshots table if not exists
            cursor.execute("SHOW TABLES LIKE 'account_snapshots'")
            result = cursor.fetchone()
            if not result:
                print("Creating 'account_snapshots' table...")
                cursor.execute("""
                    CREATE TABLE account_snapshots (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        account_id INT NOT NULL,
                        total_equity DOUBLE NOT NULL,
                        total_balance DOUBLE NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX ix_account_snapshots_timestamp (timestamp),
                        FOREIGN KEY (account_id) REFERENCES accounts(id)
                    )
                """)
                print("Table 'account_snapshots' created successfully.")
            else:
                print("Table 'account_snapshots' already exists.")

            conn.commit()
    except Exception as e:
        print(f"Error updating schema: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    update_schema()
