"""1小时 RSI 背离数据结构。"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

RsiPreset = Literal["balanced", "strict", "strong"]


class RsiDivergencePoint(BaseModel):
    time: int = Field(..., description="拐点K线开盘时间，毫秒")
    price: float
    rsi: float


class RsiDivergenceSignal(BaseModel):
    symbol: str
    interval: Literal["1h"] = "1h"
    direction: Literal["bullish", "bearish"]
    label: str
    previous: RsiDivergencePoint
    current: RsiDivergencePoint
    confirmed_at: int = Field(..., description="右侧第5根K线收盘后的确认时间，毫秒")
    bars_between: int
    last_close: float = Field(..., description="最新已收盘1小时K线收盘价")
    last_rsi: float


class RsiCandle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    rsi: Optional[float] = None


class RsiDivergenceRules(BaseModel):
    preset: RsiPreset = "strict"
    preset_label: str = "严格"
    rsi_period: int = 14
    pivot_left: int = 5
    pivot_right: int = 5
    min_bars: int = 10
    max_bars: int = 60
    min_price_change_percent: float = 0.5
    min_rsi_change: float = 5
    overbought: float = 70
    oversold: float = 30
    require_price_pivots: bool = True


def get_rsi_rules(preset: RsiPreset = "strict") -> RsiDivergenceRules:
    if preset == "balanced":
        return RsiDivergenceRules(preset=preset, preset_label="均衡", min_price_change_percent=0.3,
                                  min_rsi_change=3, overbought=65, oversold=35)
    if preset == "strong":
        return RsiDivergenceRules(preset=preset, preset_label="更强", min_price_change_percent=1,
                                  min_rsi_change=8, overbought=75, oversold=25, min_bars=12)
    return RsiDivergenceRules()


class RsiDivergenceDetail(RsiDivergenceRules):
    symbol: str
    interval: Literal["1h"] = "1h"
    candles: List[RsiCandle] = Field(default_factory=list)
    signals: List[RsiDivergenceSignal] = Field(default_factory=list)


class RsiDivergenceRadar(RsiDivergenceRules):
    interval: Literal["1h"] = "1h"
    lookback_hours: int = 24
    signals: List[RsiDivergenceSignal] = Field(default_factory=list)
    scanned_count: int = 0
    failed_count: int = 0
    timestamp: datetime
