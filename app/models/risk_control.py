from sqlalchemy import Column, String, Float, Boolean, JSON, ForeignKey, Enum, Integer, DateTime
from sqlalchemy.orm import relationship
import enum
from .base import Base, BaseMixin

class RiskLevelEnum(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Account(Base, BaseMixin):
    __tablename__ = "accounts"

    exchange = Column(String(50), nullable=False)
    api_key = Column(String(255), nullable=False)
    api_secret = Column(String(255), nullable=False)
    name = Column(String(100))
    is_active = Column(Boolean, default=True)
    settings = Column(JSON)

    risk_configs = relationship("RiskConfig", back_populates="account")
    positions = relationship("Position", back_populates="account")


class User(Base, BaseMixin):
    __tablename__ = 'users'

    username = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)


class RiskConfig(Base, BaseMixin):
    __tablename__ = "risk_configs"

    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    max_leverage = Column(Float, nullable=False)
    max_position_value = Column(Float, nullable=False)
    risk_ratio_threshold = Column(Float, nullable=False)
    max_single_order = Column(Float, nullable=False)
    price_deviation_limit = Column(Float, nullable=False)
    order_frequency_limit = Column(Integer, nullable=False)
    max_daily_loss = Column(Float, nullable=False)
    risk_level_threshold = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)

    account = relationship("Account", back_populates="risk_configs")

class Position(Base, BaseMixin):
    __tablename__ = "positions"

    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    size = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float)
    unrealized_pnl = Column(Float)
    leverage = Column(Float, nullable=False)
    risk_level = Column(Enum(RiskLevelEnum), nullable=False)
    liquidation_price = Column(Float)
    # position side for derivatives: LONG / SHORT / NET
    position_side = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)

    account = relationship("Account", back_populates="positions")

class RiskAlert(Base, BaseMixin):
    __tablename__ = "risk_alerts"

    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    risk_level = Column(Enum(RiskLevelEnum), nullable=False)
    message = Column(String(500), nullable=False)
    details = Column(JSON)
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    resolution_notes = Column(String(500))

class OrderLog(Base, BaseMixin):
    __tablename__ = "order_logs"

    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    order_id = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False)
    order_type = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    price = Column(Float)
    size = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)
    risk_check_passed = Column(Boolean, nullable=False)
    risk_check_details = Column(JSON)
    exchange_response = Column(JSON)


class TickerHistory(Base, BaseMixin):
    __tablename__ = "ticker_history"

    symbol = Column(String(20), nullable=False, index=True)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    source = Column(String(50), nullable=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
