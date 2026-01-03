from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas import risk_control as schemas
from app.services.risk_control_service import RiskControlService
from app.services.position_sync import get_position_sync_from_env
from app.core.database import SessionLocal

router = APIRouter(prefix="/risk-control", tags=["风险控制"])

@router.post("/accounts/", response_model=schemas.AccountInDB)
async def create_account(account: schemas.AccountCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """创建交易账户"""
    from app.models.risk_control import Account
    db_account = Account(**account.dict())
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@router.post("/accounts/{account_id}/risk-config", response_model=schemas.RiskConfigInDB)
async def create_risk_config(
    account_id: int,
    config: schemas.RiskConfigCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """创建风控配置"""
    from app.models.risk_control import RiskConfig
    if config.account_id != account_id:
        raise HTTPException(status_code=400, detail="Account ID mismatch")
    
    db_config = RiskConfig(**config.dict())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

@router.post("/check-position-risk")
async def check_position_risk(
    account_id: int,
    symbol: str,
    size: float,
    leverage: float,
    db: Session = Depends(get_db)
):
    """检查持仓风险"""
    risk_service = RiskControlService(db)
    result = risk_service.check_position_risk(account_id, symbol, size, leverage)
    return result

@router.post("/check-order-risk")
async def check_order_risk(
    account_id: int,
    symbol: str,
    size: float,
    price: float,
    db: Session = Depends(get_db)
):
    """检查订单风险"""
    risk_service = RiskControlService(db)
    result = risk_service.check_order_risk(account_id, symbol, size, price)
    return result

@router.post("/positions/", response_model=schemas.PositionInDB)
async def create_position(
    position: schemas.PositionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """创建新持仓"""
    from app.models.risk_control import Position, RiskLevelEnum
    
    # 首先检查持仓风险
    risk_service = RiskControlService(db)
    risk_check = risk_service.check_position_risk(
        position.account_id,
        position.symbol,
        position.size,
        position.leverage
    )
    
    if not risk_check["passed"]:
        raise HTTPException(status_code=400, detail=risk_check["reason"])
    
    db_position = Position(
        **position.dict(),
        risk_level=RiskLevelEnum.LOW  # 初始风险等级设为低
    )
    db.add(db_position)
    db.commit()
    db.refresh(db_position)
    return db_position


@router.get('/positions/', response_model=List[schemas.PositionInDB])
async def list_positions(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List positions (optionally filter by account_id)"""
    from app.models.risk_control import Position

    query = db.query(Position)
    if account_id:
        query = query.filter(Position.account_id == account_id)

    return query.order_by(Position.updated_at.desc()).all()


@router.post('/positions/sync', status_code=202)
async def trigger_positions_sync(current_user=Depends(get_current_user)):
    """Trigger a background one-shot positions sync.

    This endpoint will run a single sync across active accounts and return 202 Accepted.
    It is intended for manual testing when you added account API keys.
    """
    syncer = get_position_sync_from_env()
    # fire-and-forget the one-shot sync
    import asyncio
    asyncio.create_task(syncer.sync_once())
    return {"status": "sync scheduled"}


@router.get('/accounts/', response_model=List[schemas.AccountInDB])
async def list_accounts(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """List all accounts"""
    from app.models.risk_control import Account
    return db.query(Account).order_by(Account.updated_at.desc()).all()


@router.post('/accounts/{account_id}/positions/sync', status_code=202)
async def trigger_account_sync(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Trigger a sync for a single account (manual/test only)."""
    from app.models.risk_control import Account
    acct = db.query(Account).filter(Account.id == account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    # run one-shot sync for this account
    from app.services.position_sync import PositionSyncService

    syncer = PositionSyncService()
    # call internal method _sync_account with account ORM object
    import asyncio
    asyncio.create_task(syncer._sync_account(acct))
    return {"status": "account sync scheduled", "account_id": account_id}


@router.get('/accounts/{account_id}/positions/test')
async def test_account_positions(account_id: int, current_user=Depends(get_current_user)):
    """Debug endpoint: call adapter for an account and return raw positions or error.

    Useful to verify API key permissions and response body (does not store results).
    """
    db = SessionLocal()
    try:
        from app.models.risk_control import Account

        acct = db.query(Account).filter(Account.id == account_id).first()
        if not acct:
            return {"error": "account not found"}

        from app.services.exchange.binance_adapter import create_adapter_for_account

        adapter = create_adapter_for_account(acct)
        if not adapter:
            return {"error": "adapter not available for this account (check exchange field or credentials)"}

        # we want to surface raw status/body when adapter can't parse positions
        try:
            rows = await adapter.fetch_positions()
        except Exception:
            rows = None

        if rows is not None:
            return {"rows": rows}

        # try raw debug to surface server status/body
        raw = await adapter.fetch_positions_raw()
        return {"rows": None, "debug": raw}
    finally:
        db.close()

@router.patch("/positions/{position_id}", response_model=schemas.PositionInDB)
async def update_position(
    position_id: int,
    position_update: schemas.PositionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """更新持仓信息"""
    risk_service = RiskControlService(db)
    if position_update.current_price:
        updated_position = risk_service.update_position(position_id, position_update.current_price)
        if not updated_position:
            raise HTTPException(status_code=404, detail="Position not found")
        return updated_position
    
    # 如果只是更新是否活跃状态
    from app.models.risk_control import Position
    db_position = db.query(Position).filter(Position.id == position_id).first()
    if not db_position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    for key, value in position_update.dict(exclude_unset=True).items():
        setattr(db_position, key, value)
    
    db.commit()
    db.refresh(db_position)
    return db_position

@router.get("/accounts/{account_id}/risk-summary", response_model=schemas.AccountRiskSummary)
async def get_account_risk_summary(
    account_id: int,
    db: Session = Depends(get_db)
):
    """获取账户风险概览"""
    risk_service = RiskControlService(db)
    return risk_service.get_account_risk_summary(account_id)

@router.post("/alerts/", response_model=schemas.RiskAlertInDB)
async def create_risk_alert(
    alert: schemas.RiskAlertCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """创建风险预警"""
    risk_service = RiskControlService(db)
    return risk_service.create_risk_alert(
        alert.account_id,
        alert.alert_type,
        alert.risk_level,
        alert.message,
        alert.details
    )

@router.get("/alerts/", response_model=List[schemas.RiskAlertInDB])
async def get_risk_alerts(
    account_id: Optional[int] = None,
    risk_level: Optional[schemas.RiskLevel] = None,
    is_resolved: Optional[bool] = False,
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取风险预警列表"""
    from app.models.risk_control import RiskAlert
    
    query = db.query(RiskAlert)
    if account_id:
        query = query.filter(RiskAlert.account_id == account_id)
    if risk_level:
        query = query.filter(RiskAlert.risk_level == risk_level)
    if is_resolved is not None:
        query = query.filter(RiskAlert.is_resolved == is_resolved)
    
    return query.order_by(RiskAlert.created_at.desc()).offset(skip).limit(limit).all()

@router.patch("/alerts/{alert_id}", response_model=schemas.RiskAlertInDB)
async def resolve_risk_alert(
    alert_id: int,
    resolution_notes: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """处理风险预警"""
    from app.models.risk_control import RiskAlert
    
    alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolution_notes = resolution_notes
    
    db.commit()
    db.refresh(alert)
    return alert
