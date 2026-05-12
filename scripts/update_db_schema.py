import os
import pymysql
from dotenv import load_dotenv


def ensure_column(cursor, table_name, column_name, ddl_sql, success_message):
    cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE %s", (column_name,))
    result = cursor.fetchone()
    if result:
        print(f"Column '{column_name}' already exists on '{table_name}'.")
        return
    print(f"Adding '{column_name}' column to '{table_name}' table...")
    cursor.execute(ddl_sql)
    print(success_message)


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

            cursor.execute("SHOW TABLES LIKE 'polymarket_copy_strategies'")
            if cursor.fetchone():
                ensure_column(
                    cursor,
                    "polymarket_copy_strategies",
                    "execution_account_id",
                    "ALTER TABLE polymarket_copy_strategies ADD COLUMN execution_account_id INT NULL AFTER source_wallet",
                    "Column 'execution_account_id' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_strategies",
                    "runner_lookback_hours",
                    "ALTER TABLE polymarket_copy_strategies ADD COLUMN runner_lookback_hours INT NOT NULL DEFAULT 24 AFTER signal_cooldown_seconds",
                    "Column 'runner_lookback_hours' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_strategies",
                    "runner_activity_limit",
                    "ALTER TABLE polymarket_copy_strategies ADD COLUMN runner_activity_limit INT NOT NULL DEFAULT 120 AFTER runner_lookback_hours",
                    "Column 'runner_activity_limit' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_strategies",
                    "last_started_at",
                    "ALTER TABLE polymarket_copy_strategies ADD COLUMN last_started_at DATETIME NULL AFTER blocked_markets",
                    "Column 'last_started_at' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_strategies",
                    "last_stopped_at",
                    "ALTER TABLE polymarket_copy_strategies ADD COLUMN last_stopped_at DATETIME NULL AFTER last_started_at",
                    "Column 'last_stopped_at' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_strategies",
                    "last_run_at",
                    "ALTER TABLE polymarket_copy_strategies ADD COLUMN last_run_at DATETIME NULL AFTER last_stopped_at",
                    "Column 'last_run_at' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_strategies",
                    "last_error",
                    "ALTER TABLE polymarket_copy_strategies ADD COLUMN last_error TEXT NULL AFTER last_run_at",
                    "Column 'last_error' added successfully.",
                )
            else:
                print("Table 'polymarket_copy_strategies' does not exist yet. It will be created by init_db().")

            cursor.execute("SHOW TABLES LIKE 'polymarket_copy_source_positions'")
            if cursor.fetchone():
                ensure_column(
                    cursor,
                    "polymarket_copy_source_positions",
                    "estimated_follower_size",
                    "ALTER TABLE polymarket_copy_source_positions ADD COLUMN estimated_follower_size DOUBLE NOT NULL DEFAULT 0.0 AFTER estimated_source_notional_usdc",
                    "Column 'estimated_follower_size' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_source_positions",
                    "estimated_follower_notional_usdc",
                    "ALTER TABLE polymarket_copy_source_positions ADD COLUMN estimated_follower_notional_usdc DOUBLE NOT NULL DEFAULT 0.0 AFTER estimated_follower_size",
                    "Column 'estimated_follower_notional_usdc' added successfully.",
                )
            else:
                print("Table 'polymarket_copy_source_positions' does not exist yet. It will be created by init_db().")

            cursor.execute("SHOW TABLES LIKE 'polymarket_copy_signal_logs'")
            if cursor.fetchone():
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "source_trade_size",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN source_trade_size DOUBLE NOT NULL DEFAULT 0.0 AFTER side",
                    "Column 'source_trade_size' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_execution_status",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_execution_status VARCHAR(32) NULL AFTER skip_reason",
                    "Column 'live_execution_status' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_order_id",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_order_id VARCHAR(255) NULL AFTER live_execution_status",
                    "Column 'live_order_id' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_order_status",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_order_status VARCHAR(64) NULL AFTER live_order_id",
                    "Column 'live_order_status' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_execution_error",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_execution_error TEXT NULL AFTER live_order_status",
                    "Column 'live_execution_error' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_order_response",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_order_response JSON NULL AFTER live_execution_error",
                    "Column 'live_order_response' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_executed_at",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_executed_at DATETIME NULL AFTER live_order_response",
                    "Column 'live_executed_at' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_canceled_at",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_canceled_at DATETIME NULL AFTER live_executed_at",
                    "Column 'live_canceled_at' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_cancel_response",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_cancel_response JSON NULL AFTER live_canceled_at",
                    "Column 'live_cancel_response' added successfully.",
                )
                ensure_column(
                    cursor,
                    "polymarket_copy_signal_logs",
                    "live_cancel_error",
                    "ALTER TABLE polymarket_copy_signal_logs ADD COLUMN live_cancel_error TEXT NULL AFTER live_cancel_response",
                    "Column 'live_cancel_error' added successfully.",
                )
            else:
                print("Table 'polymarket_copy_signal_logs' does not exist yet. It will be created by init_db().")

            conn.commit()
    except Exception as e:
        print(f"Error updating schema: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    update_schema()
