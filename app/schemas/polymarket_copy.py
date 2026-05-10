from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PolymarketCopyStrategyCreate(BaseModel):
    strategy_name: str = Field(..., min_length=1, max_length=120)
    source_wallet: str = Field(..., min_length=42, max_length=42)
    copy_mode: str = Field("proportional_notional")
    copy_ratio: float = Field(0.1, gt=0, le=1)
    min_copy_order_usdc: float = Field(20.0, ge=0)
    max_order_usdc: float = Field(200.0, gt=0)
    max_position_notional_usdc: float = Field(1000.0, gt=0)
    max_market_exposure_usdc: float = Field(500.0, gt=0)
    max_signal_delay_seconds: int = Field(120, ge=1, le=3600)
    max_slippage_bps: int = Field(80, ge=0, le=5000)
    close_only: bool = False
    dry_run: bool = True
    same_outcome_only: bool = True
    follow_reduce_only_after_open: bool = True
    allow_partial_close_sync: bool = True
    signal_cooldown_seconds: int = Field(15, ge=0, le=3600)
    allowed_markets: List[str] = Field(default_factory=list)
    blocked_markets: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class PolymarketCopyStrategyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_name: str
    source_wallet: str
    status: str
    copy_mode: str
    copy_ratio: float
    min_copy_order_usdc: float
    max_order_usdc: float
    max_position_notional_usdc: float
    max_market_exposure_usdc: float
    max_signal_delay_seconds: int
    max_slippage_bps: int
    close_only: bool
    dry_run: bool
    same_outcome_only: bool
    follow_reduce_only_after_open: bool
    allow_partial_close_sync: bool
    signal_cooldown_seconds: int
    allowed_markets: List[str] = Field(default_factory=list)
    blocked_markets: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PolymarketCopySimulationRequest(BaseModel):
    lookback_hours: int = Field(72, ge=1, le=720)
    activity_limit: int = Field(200, ge=1, le=500)


class PolymarketCopySimulationSignal(BaseModel):
    signal_index: int
    signal_type: str
    source_timestamp: datetime
    title: Optional[str] = None
    condition_id: Optional[str] = None
    asset: Optional[str] = None
    outcome: Optional[str] = None
    side: Optional[str] = None
    source_trade_usdc: float = 0.0
    source_position_before: float = 0.0
    source_position_after: float = 0.0
    source_reduce_ratio: Optional[float] = None
    follower_order_usdc: float = 0.0
    follower_position_before: float = 0.0
    follower_position_after: float = 0.0
    status: str
    skip_reason: Optional[str] = None


class PolymarketCopySimulationSummary(BaseModel):
    raw_trade_count: int = 0
    grouped_trade_count: int = 0
    simulated_signal_count: int = 0
    executed_signal_count: int = 0
    skipped_signal_count: int = 0
    total_source_notional_usdc: float = 0.0
    total_copied_notional_usdc: float = 0.0
    skip_reason_counts: Dict[str, int] = Field(default_factory=dict)


class PolymarketCopySimulationResult(BaseModel):
    strategy: PolymarketCopyStrategyRead
    simulation_run_id: Optional[int] = None
    lookback_hours: int
    activity_limit: int
    summary: PolymarketCopySimulationSummary
    signals: List[PolymarketCopySimulationSignal] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)