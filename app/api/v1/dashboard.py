from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.deps import get_db
from app.schemas.dashboard import DashboardSummary, PositionChartData, RiskDistributionItem, DashboardAlert, ChartSeries
from app.models.risk_control import Account, RiskAlert, RiskLevelEnum, Position
from typing import List

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"]
)

@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    # Accounts
    total_accounts = db.query(Account).count()
    active_accounts_count = db.query(Account).filter(Account.is_active == True).count()
    abnormal_accounts = total_accounts - active_accounts_count 

    # Financials (Sum of all accounts)
    total_equity = db.query(func.sum(Account.total_equity)).scalar() or 0.0
    total_balance = db.query(func.sum(Account.total_balance)).scalar() or 0.0
    
    # Calculate PnL (This is a simplification as we don't have daily snapshots yet)
    # Assuming today_pnl is stored in Account
    daily_pnl = db.query(func.sum(Account.today_pnl)).scalar() or 0.0
    
    # Alerts
    active_alerts = db.query(RiskAlert).filter(RiskAlert.is_resolved == False).count()
    high_risk_alerts = db.query(RiskAlert).filter(
        RiskAlert.is_resolved == False, 
        RiskAlert.risk_level.in_([RiskLevelEnum.HIGH, RiskLevelEnum.CRITICAL])
    ).count()
    medium_risk_alerts = db.query(RiskAlert).filter(
        RiskAlert.is_resolved == False, 
        RiskAlert.risk_level == RiskLevelEnum.MEDIUM
    ).count()

    # Calculate PnL Ratio
    pnl_ratio = (daily_pnl / total_balance * 100) if total_balance > 0 else 0.0

    return DashboardSummary(
        total_position_value=f"${total_equity:,.2f}",
        position_value_status="success", 
        day_change=0.0, # Placeholder as we don't have history
        active_alerts=active_alerts,
        alert_status="warning" if active_alerts > 0 else "success",
        high_risk_alerts=high_risk_alerts,
        medium_risk_alerts=medium_risk_alerts,
        daily_pnl=daily_pnl,
        pnl_status="success" if daily_pnl >= 0 else "danger",
        pnl_ratio=round(pnl_ratio, 2),
        active_accounts=total_accounts,
        normal_accounts=active_accounts_count,
        abnormal_accounts=abnormal_accounts
    )

@router.get("/charts/position", response_model=PositionChartData)
def get_position_chart(time_range: str = "today", db: Session = Depends(get_db)):
    # Mock data for charts as we don't have historical data table yet
    return PositionChartData(
        xAxis=['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
        series=[
            ChartSeries(name='BTC', type='line', data=[120, 132, 101, 134, 90]),
            ChartSeries(name='ETH', type='line', data=[220, 182, 191, 234, 290]),
            ChartSeries(name='Others', type='line', data=[150, 232, 201, 154, 190])
        ]
    )

@router.get("/charts/risk", response_model=List[RiskDistributionItem])
def get_risk_chart(db: Session = Depends(get_db)):
    results = db.query(Position.risk_level, func.count(Position.id)).group_by(Position.risk_level).all()
    
    data = []
    for risk_level, count in results:
        name = "未知"
        if risk_level == RiskLevelEnum.LOW: name = "低风险"
        elif risk_level == RiskLevelEnum.MEDIUM: name = "中风险"
        elif risk_level == RiskLevelEnum.HIGH: name = "高风险"
        elif risk_level == RiskLevelEnum.CRITICAL: name = "极高风险"
        
        data.append(RiskDistributionItem(name=name, value=count))
        
    if not data:
        data = [
            RiskDistributionItem(name='低风险', value=0),
            RiskDistributionItem(name='中风险', value=0),
            RiskDistributionItem(name='高风险', value=0)
        ]
        
    return data

@router.get("/alerts", response_model=List[DashboardAlert])
def get_recent_alerts(db: Session = Depends(get_db)):
    alerts = db.query(RiskAlert).order_by(RiskAlert.created_at.desc()).limit(10).all()
    
    res = []
    for alert in alerts:
        account_name = alert.account.name if alert.account else "Unknown"
        
        # Handle Enum value
        risk_level_str = "未知"
        if alert.risk_level == RiskLevelEnum.LOW: risk_level_str = "低风险"
        elif alert.risk_level == RiskLevelEnum.MEDIUM: risk_level_str = "中风险"
        elif alert.risk_level == RiskLevelEnum.HIGH: risk_level_str = "高风险"
        elif alert.risk_level == RiskLevelEnum.CRITICAL: risk_level_str = "极高风险"

        res.append(DashboardAlert(
            time=alert.created_at.strftime("%Y-%m-%d %H:%M:%S") if alert.created_at else "",
            type=alert.alert_type,
            account=account_name,
            message=alert.message,
            risk_level=risk_level_str,
            status="已处理" if alert.is_resolved else "未处理"
        ))
    return res
