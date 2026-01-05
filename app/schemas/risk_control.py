from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AccountBase(BaseModel):
    exchange: str = Field(..., description="交易所名称")
    name: Optional[str] = Field(None, description="账户名称")
    api_key: str = Field(..., description="API Key")
    api_secret: str = Field(..., description="API Secret")
    settings: Optional[Dict] = Field(default={}, description="账户设置")

class AccountCreate(AccountBase):
    pass

class AccountUpdate(BaseModel):
    exchange: Optional[str] = None
    name: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    settings: Optional[Dict] = None
    is_active: Optional[bool] = None

class AccountInDB(AccountBase):
    id: int
    is_active: bool
    total_equity: Optional[float] = 0.0
    total_balance: Optional[float] = 0.0
    today_pnl: Optional[float] = 0.0
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class RiskConfigBase(BaseModel):
    max_leverage: float = Field(..., ge=1, description="最大杠杆倍数")
    max_position_value: float = Field(..., gt=0, description="最大持仓价值")
    risk_ratio_threshold: float = Field(..., gt=0, lt=1, description="风险率阈值")
    max_single_order: float = Field(..., gt=0, description="单笔最大下单量")
    price_deviation_limit: float = Field(..., gt=0, lt=1, description="价格偏离度限制")
    order_frequency_limit: int = Field(..., gt=0, description="每分钟最大下单次数")
    max_daily_loss: float = Field(..., gt=0, description="每日最大亏损额")
    risk_level_threshold: float = Field(..., gt=0, lt=1, description="风险等级阈值")

class RiskConfigCreate(RiskConfigBase):
    account_id: int

class RiskConfigUpdate(RiskConfigBase):
    is_active: Optional[bool] = None

class RiskConfigInDB(RiskConfigBase):
    id: int
    account_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class PositionBase(BaseModel):
    symbol: str = Field(..., description="交易对")
    position_side: Optional[str] = Field(None, description="持仓方向 LONG/SHORT/NET")
    size: float = Field(..., ge=0, description="持仓大小")
    entry_price: float = Field(..., gt=0, description="入场价格")
    leverage: float = Field(..., ge=1, description="杠杆倍数")

class PositionCreate(PositionBase):
    account_id: int

class PositionUpdate(BaseModel):
    current_price: Optional[float] = Field(None, gt=0, description="当前价格")
    is_active: Optional[bool] = Field(None, description="是否活跃")

class PositionInDB(PositionBase):
    id: int
    account_id: int
    current_price: Optional[float]
    unrealized_pnl: Optional[float]
    risk_level: RiskLevel
    liquidation_price: Optional[float]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class OrderData(BaseModel):
    order_id: str = Field(..., description="订单ID")
    symbol: str = Field(..., description="交易对")
    type: str = Field(..., description="订单类型")
    side: str = Field(..., description="订单方向")
    price: Optional[float] = Field(None, description="价格")
    size: float = Field(..., gt=0, description="数量")
    status: str = Field("CREATED", description="订单状态")

class RiskCheckResult(BaseModel):
    passed: bool = Field(..., description="风险检查是否通过")
    reason: Optional[str] = Field(None, description="未通过原因")

class RiskAlertCreate(BaseModel):
    account_id: int
    alert_type: str
    risk_level: RiskLevel
    message: str
    details: Optional[Dict] = None

class RiskAlertInDB(RiskAlertCreate):
    id: int
    is_resolved: bool
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class AccountRiskSummary(BaseModel):
    total_position_value: float
    total_unrealized_pnl: float
    highest_risk_level: str
    active_positions_count: int
    risk_level_distribution: Dict[RiskLevel, int]


class TickerHistoryInDB(BaseModel):
    id: int
    symbol: str
    price: float
    timestamp: datetime
    source: Optional[str]
    position_id: Optional[int]
    account_id: Optional[int]

    class Config:
        orm_mode = True

class RiskAlertBase(BaseModel):
    alert_type: str = Field(..., description="预警类型")
    risk_level: RiskLevel = Field(..., description="风险等级")
    message: str = Field(..., description="预警消息")
    details: Optional[Dict] = Field(None, description="详细信息")

class RiskAlertCreate(RiskAlertBase):
    account_id: int

class RiskAlertUpdate(BaseModel):
    is_resolved: bool
    resolution_notes: Optional[str] = None

class RiskAlertInDB(RiskAlertBase):
    id: int
    account_id: int
    is_resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]

    class Config:
        orm_mode = True

class TransactionHistoryBase(BaseModel):
    symbol: Optional[str]
    type: str
    side: Optional[str]
    price: Optional[float]
    qty: Optional[float]
    quote_qty: Optional[float]
    commission: Optional[float]
    commission_asset: Optional[str]
    realized_pnl: Optional[float]
    time: datetime
    order_id: Optional[str]
    transaction_id: Optional[str]

class TransactionHistoryCreate(TransactionHistoryBase):
    account_id: int

class TransactionHistoryInDB(TransactionHistoryBase):
    id: int
    account_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
