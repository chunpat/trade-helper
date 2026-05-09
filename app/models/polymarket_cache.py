from sqlalchemy import Column, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint

from .base import Base, BaseMixin


class PolymarketCacheEntry(Base, BaseMixin):
    __tablename__ = "polymarket_cache_entries"
    __table_args__ = (
        UniqueConstraint("cache_type", "cache_key", name="uq_polymarket_cache_type_key"),
        Index("ix_polymarket_cache_type_expires_id", "cache_type", "expires_at", "id"),
        Index("ix_polymarket_cache_wallet_type_id", "wallet_address", "cache_type", "id"),
    )

    cache_type = Column(String(32), nullable=False, index=True)
    cache_key = Column(String(255), nullable=False, index=True)
    wallet_address = Column(String(64), nullable=True, index=True)
    category = Column(String(50), nullable=True)
    time_period = Column(String(20), nullable=True)
    order_by = Column(String(20), nullable=True)
    limit_value = Column(Integer, nullable=True)
    hours_value = Column(Integer, nullable=True)
    payload = Column(JSON, nullable=True)
    last_refresh_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)