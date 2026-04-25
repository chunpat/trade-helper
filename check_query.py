from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects import mysql
import datetime

Base = declarative_base()

class TransactionHistory(Base):
    __tablename__ = 'transaction_history'
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer)
    type = Column(String(50))
    time = Column(DateTime)
    symbol = Column(String(20))

engine = create_engine("mysql+pymysql://root:root@localhost:3306/trade_helper")
Session = sessionmaker(bind=engine)
db = Session()

query = db.query(TransactionHistory)
# record_scope='trades' means type='TRADE'
query = query.filter(TransactionHistory.type == 'TRADE')
# add a time range
query = query.filter(TransactionHistory.time >= datetime.datetime(2023, 1, 1))
query = query.filter(TransactionHistory.time <= datetime.datetime(2024, 12, 31))

# apply hint
query = query.with_hint(
    TransactionHistory,
    "USE INDEX (ix_transaction_history_type_time_id)",
    dialect_name="mysql",
)

# order and limit
query = query.order_by(TransactionHistory.time.desc(), TransactionHistory.id.desc()).limit(20)

# Compile to SQL
compiled = query.statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})
print(str(compiled))
