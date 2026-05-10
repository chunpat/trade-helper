from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from .base import Base, BaseMixin


class PolymarketCopyStrategy(Base, BaseMixin):
    __tablename__ = "polymarket_copy_strategies"
    __table_args__ = (
        Index("ix_polymarket_copy_strategy_status_created_id", "status", "created_at", "id"),
        Index("ix_polymarket_copy_strategy_source_status_id", "source_wallet", "status", "id"),
    )

    strategy_name = Column(String(120), nullable=False)
    source_wallet = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="draft")
    copy_mode = Column(String(32), nullable=False, default="proportional_notional")
    copy_ratio = Column(Float, nullable=False, default=0.1)
    min_copy_order_usdc = Column(Float, nullable=False, default=20.0)
    max_order_usdc = Column(Float, nullable=False, default=200.0)
    max_position_notional_usdc = Column(Float, nullable=False, default=1000.0)
    max_market_exposure_usdc = Column(Float, nullable=False, default=500.0)
    max_signal_delay_seconds = Column(Integer, nullable=False, default=120)
    max_slippage_bps = Column(Integer, nullable=False, default=80)
    close_only = Column(Boolean, nullable=False, default=False)
    dry_run = Column(Boolean, nullable=False, default=True)
    same_outcome_only = Column(Boolean, nullable=False, default=True)
    follow_reduce_only_after_open = Column(Boolean, nullable=False, default=True)
    allow_partial_close_sync = Column(Boolean, nullable=False, default=True)
    signal_cooldown_seconds = Column(Integer, nullable=False, default=15)
    allowed_markets = Column(JSON, nullable=True)
    blocked_markets = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)


class PolymarketCopySimulationRun(Base, BaseMixin):
    __tablename__ = "polymarket_copy_simulation_runs"
    __table_args__ = (
        Index("ix_polymarket_copy_simulation_strategy_created_id", "strategy_id", "created_at", "id"),
    )

    strategy_id = Column(Integer, ForeignKey("polymarket_copy_strategies.id"), nullable=False, index=True)
    lookback_hours = Column(Integer, nullable=False, default=72)
    activity_limit = Column(Integer, nullable=False, default=200)
    raw_trade_count = Column(Integer, nullable=False, default=0)
    grouped_trade_count = Column(Integer, nullable=False, default=0)
    simulated_signal_count = Column(Integer, nullable=False, default=0)
    executed_signal_count = Column(Integer, nullable=False, default=0)
    skipped_signal_count = Column(Integer, nullable=False, default=0)
    total_source_notional_usdc = Column(Float, nullable=False, default=0.0)
    total_copied_notional_usdc = Column(Float, nullable=False, default=0.0)
    summary = Column(JSON, nullable=True)


class PolymarketCopySourcePosition(Base, BaseMixin):
    __tablename__ = "polymarket_copy_source_positions"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "condition_id",
            "asset",
            "outcome",
            name="uq_polymarket_copy_source_position_key",
        ),
        Index("ix_polymarket_copy_source_position_strategy_updated_id", "strategy_id", "updated_at", "id"),
    )

    strategy_id = Column(Integer, ForeignKey("polymarket_copy_strategies.id"), nullable=False, index=True)
    condition_id = Column(String(255), nullable=False)
    asset = Column(String(255), nullable=False)
    outcome = Column(String(80), nullable=False)
    estimated_source_size = Column(Float, nullable=False, default=0.0)
    estimated_source_notional_usdc = Column(Float, nullable=False, default=0.0)
    estimated_source_avg_price = Column(Float, nullable=True)
    last_source_activity_at = Column(DateTime, nullable=True)
    last_source_tx_hash = Column(String(255), nullable=True)