from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.deps import get_db
from app.schemas.dashboard import DashboardSummary, PositionChartData, RiskDistributionItem, DashboardAlert, ChartSeries
from app.models.risk_control import Account, RiskAlert, RiskLevelEnum, Position, TransactionHistory, AccountSnapshot
from typing import List
from datetime import datetime, time as dt_time, timedelta

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
    
    # Calculate Daily PnL from TransactionHistory
    # Use UTC for consistency with Binance data
    now_utc = datetime.utcnow()
    today_start = datetime.combine(now_utc.date(), dt_time.min)
    
    # Sum realized_pnl from income types (REALIZED_PNL, FUNDING_FEE, COMMISSION)
    # We exclude 'TRADE' type to avoid double counting with 'REALIZED_PNL'
    daily_pnl = db.query(func.sum(TransactionHistory.realized_pnl)).filter(
        TransactionHistory.time >= today_start,
        TransactionHistory.type.in_(['REALIZED_PNL', 'FUNDING_FEE', 'COMMISSION'])
    ).scalar() or 0.0
    
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

    # Calculate PnL Ratio (PnL / (Total Equity - PnL))
    previous_equity_calc = total_equity - daily_pnl
    pnl_ratio = (daily_pnl / previous_equity_calc * 100) if previous_equity_calc > 0 else 0.0
    
    # Day change (Equity change percentage compared to 24h ago)
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    # Get the latest snapshot for each account that is older than 24h
    subq = db.query(
        AccountSnapshot.account_id,
        func.max(AccountSnapshot.timestamp).label('max_ts')
    ).filter(AccountSnapshot.timestamp <= yesterday).group_by(AccountSnapshot.account_id).subquery()
    
    old_snapshots = db.query(AccountSnapshot).join(
        subq,
        (AccountSnapshot.account_id == subq.c.account_id) & 
        (AccountSnapshot.timestamp == subq.c.max_ts)
    ).all()
    
    old_total_equity = sum(s.total_equity for s in old_snapshots)
    
    if old_total_equity > 0:
        day_change = ((total_equity - old_total_equity) / old_total_equity) * 100
    else:
        # Fallback to pnl_ratio if no snapshot exists
        day_change = pnl_ratio

    return DashboardSummary(
        total_position_value=f"${total_equity:,.2f}",
        position_value_status="success" if day_change >= 0 else "danger", 
        day_change=round(day_change, 2),
        active_alerts=active_alerts,
        alert_status="warning" if active_alerts > 0 else "success",
        high_risk_alerts=high_risk_alerts,
        medium_risk_alerts=medium_risk_alerts,
        daily_pnl=round(daily_pnl, 2),
        pnl_status="success" if daily_pnl >= 0 else "danger",
        pnl_ratio=round(pnl_ratio, 2),
        active_accounts=total_accounts,
        normal_accounts=active_accounts_count,
        abnormal_accounts=abnormal_accounts
    )

@router.get("/charts/position", response_model=PositionChartData)
def get_position_chart(time_range: str = "today", db: Session = Depends(get_db)):
    # Calculate daily realized PnL for the last 7 days
    days = 7
    if time_range == "week": days = 7
    elif time_range == "month": days = 30
    
    # Use UTC for consistency
    now_utc = datetime.utcnow()
    end_date = now_utc.date()
    start_date = end_date - timedelta(days=days-1)
    
    # Generate date list
    date_list = [(start_date + timedelta(days=i)) for i in range(days)]
    date_strs = [d.strftime("%m-%d") for d in date_list]
    
    # Query realized PnL grouped by date
    pnl_data = []
    for d in date_list:
        d_start = datetime.combine(d, dt_time.min)
        d_end = datetime.combine(d, dt_time.max)
        
        daily_sum = db.query(func.sum(TransactionHistory.realized_pnl)).filter(
            TransactionHistory.time >= d_start,
            TransactionHistory.time <= d_end,
            TransactionHistory.type.in_(['REALIZED_PNL', 'FUNDING_FEE', 'COMMISSION'])
        ).scalar() or 0.0
        pnl_data.append(round(daily_sum, 2))
    
    return PositionChartData(
        xAxis=date_strs,
        series=[
            ChartSeries(name='日内盈亏', type='bar', data=pnl_data)
        ]
    )

@router.get("/charts/risk", response_model=List[RiskDistributionItem])
def get_risk_chart(db: Session = Depends(get_db)):
    # Only count active positions
    results = db.query(Position.risk_level, func.count(Position.id)).filter(
        Position.is_active == True
    ).group_by(Position.risk_level).all()
    
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
