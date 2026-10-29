"""多周期布林带轨外监测数据。"""
from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field


class BollingerBandSnapshot(BaseModel):
    interval: Literal["4h", "1h", "15m"]
    close: float
    middle: float
    upper: float
    lower: float
    closed_at: int = Field(..., description="K线完成收盘时间，毫秒")


class BollingerSignal(BaseModel):
    symbol: str
    direction: Literal["above_upper", "below_lower"]
    quote_volume_24h: float = Field(..., description="滚动24小时成交额，USDT")
    bands: List[BollingerBandSnapshot]


class BollingerRadarResponse(BaseModel):
    signals: List[BollingerSignal] = Field(default_factory=list)
    scanned_count: int = 0
    failed_count: int = 0
    min_quote_volume: float = 100_000_000
    period: int = 24
    stddev_multiplier: float = 2
    timestamp: datetime
