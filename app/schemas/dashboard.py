from pydantic import BaseModel
from typing import List, Dict, Any, Union

class DashboardSummary(BaseModel):
    total_position_value: str
    position_value_status: str
    day_change: float
    active_alerts: int
    alert_status: str
    high_risk_alerts: int
    medium_risk_alerts: int
    daily_pnl: float
    pnl_status: str
    pnl_ratio: float
    active_accounts: int
    normal_accounts: int
    abnormal_accounts: int

class ChartSeries(BaseModel):
    name: str
    type: str
    data: List[Union[int, float]]

class PositionChartData(BaseModel):
    xAxis: List[str]
    series: List[ChartSeries]

class RiskDistributionItem(BaseModel):
    name: str
    value: int

class DashboardAlert(BaseModel):
    time: str
    type: str
    account: str
    message: str
    risk_level: str
    status: str
