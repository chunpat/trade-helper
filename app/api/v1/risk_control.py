import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas import risk_control as schemas
from app.services.risk_control_service import RiskControlService
from app.services.position_sync import get_position_sync_from_env
from app.services.trade_review_service import TradeReviewService
from app.core.database import SessionLocal

router = APIRouter(prefix="/risk-control", tags=["风险控制"])

REVIEW_RELEVANT_TRANSACTION_TYPES = {
    "TRADE",
    "REALIZED_PNL",
    "FUNDING_FEE",
    "COMMISSION",
    "TRANSFER",
    "INTERNAL_TRANSFER",
}

REVIEW_CASHFLOW_TRANSACTION_TYPES = {
    "REALIZED_PNL",
    "FUNDING_FEE",
    "COMMISSION",
    "TRANSFER",
    "INTERNAL_TRANSFER",
}

OKX_EXCHANGE_ALIASES = {"okx", "okex"}
ONE_TIME_HISTORY_BACKFILL_DAYS = 90
SYNC_HISTORY_STATUS_POLL_RUNNING = {"queued", "running"}
SYNC_HISTORY_JOBS: dict[int, dict] = {}
SYNC_HISTORY_TASKS: dict[int, asyncio.Task] = {}


def _datetime_to_iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _build_sync_history_status(
    *,
    account_id: int,
    days: int,
    status: str,
    account_name: Optional[str] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    result: Optional[dict] = None,
    history_90d_backfilled_at: Optional[datetime] = None,
) -> dict:
    return {
        "account_id": account_id,
        "account_name": account_name,
        "days": days,
        "status": status,
        "message": message,
        "error": error,
        "started_at": _datetime_to_iso(started_at),
        "finished_at": _datetime_to_iso(finished_at),
        "result": result,
        "history_90d_backfilled_at": _datetime_to_iso(history_90d_backfilled_at),
        "history_90d_backfill_locked": history_90d_backfilled_at is not None,
    }


async def _run_sync_history_job(account_id: int, days: int) -> None:
    from app.models.risk_control import Account
    from app.services.history_backfill_service import backfill_account_history

    started_at = datetime.utcnow()
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            SYNC_HISTORY_JOBS[account_id] = _build_sync_history_status(
                account_id=account_id,
                account_name=None,
                days=days,
                status="failed",
                error="Account not found",
                started_at=started_at,
                finished_at=datetime.utcnow(),
            )
            return

        SYNC_HISTORY_JOBS[account_id] = _build_sync_history_status(
            account_id=account.id,
            account_name=account.name,
            days=days,
            status="running",
            message="90天历史回补正在后台执行",
            started_at=started_at,
            history_90d_backfilled_at=account.history_90d_backfilled_at,
        )

        if days >= ONE_TIME_HISTORY_BACKFILL_DAYS and account.history_90d_backfilled_at is not None:
            SYNC_HISTORY_JOBS[account_id] = _build_sync_history_status(
                account_id=account.id,
                account_name=account.name,
                days=days,
                status="completed",
                message="当前交易账户已经完成过一次 90 天历史回补",
                started_at=started_at,
                finished_at=datetime.utcnow(),
                history_90d_backfilled_at=account.history_90d_backfilled_at,
            )
            return

        result = await backfill_account_history(
            db,
            account,
            days=days,
            include_snapshots=True,
        )
        if days >= ONE_TIME_HISTORY_BACKFILL_DAYS and account.history_90d_backfilled_at is None:
            account.history_90d_backfilled_at = datetime.utcnow()
            db.add(account)
            db.commit()
            db.refresh(account)

        result["history_90d_backfilled_at"] = _datetime_to_iso(account.history_90d_backfilled_at)
        result["history_90d_backfill_locked"] = account.history_90d_backfilled_at is not None

        SYNC_HISTORY_JOBS[account_id] = _build_sync_history_status(
            account_id=account.id,
            account_name=account.name,
            days=days,
            status="success",
            message=result.get("message") or "90天历史回补完成",
            started_at=started_at,
            finished_at=datetime.utcnow(),
            result=result,
            history_90d_backfilled_at=account.history_90d_backfilled_at,
        )
    except Exception as exc:
        logging.exception("background sync history failed for account %s", account_id)
        account = None
        try:
            account = db.query(Account).filter(Account.id == account_id).first()
        except Exception:
            logging.exception("failed to load account %s while capturing sync error", account_id)
        SYNC_HISTORY_JOBS[account_id] = _build_sync_history_status(
            account_id=account_id,
            account_name=getattr(account, "name", None),
            days=days,
            status="failed",
            error=str(exc),
            started_at=started_at,
            finished_at=datetime.utcnow(),
            history_90d_backfilled_at=getattr(account, "history_90d_backfilled_at", None),
        )
    finally:
        db.close()
        current_task = SYNC_HISTORY_TASKS.get(account_id)
        if current_task is asyncio.current_task():
            SYNC_HISTORY_TASKS.pop(account_id, None)


def _schedule_sync_history_job(account_id: int, account_name: Optional[str], days: int, history_90d_backfilled_at: Optional[datetime]) -> dict:
    existing_task = SYNC_HISTORY_TASKS.get(account_id)
    if existing_task and not existing_task.done():
        current_status = dict(SYNC_HISTORY_JOBS.get(account_id) or {})
        if current_status:
            current_status["history_90d_backfilled_at"] = _datetime_to_iso(history_90d_backfilled_at)
            current_status["history_90d_backfill_locked"] = history_90d_backfilled_at is not None
            return current_status

    scheduled_status = _build_sync_history_status(
        account_id=account_id,
        account_name=account_name,
        days=days,
        status="queued",
        message="90天历史回补已启动，正在后台执行",
        started_at=datetime.utcnow(),
        history_90d_backfilled_at=history_90d_backfilled_at,
    )
    SYNC_HISTORY_JOBS[account_id] = scheduled_status
    task = asyncio.create_task(_run_sync_history_job(account_id, days))
    SYNC_HISTORY_TASKS[account_id] = task
    return scheduled_status


def _get_sync_history_status_payload(account) -> dict:
    current_status = SYNC_HISTORY_JOBS.get(account.id)
    if current_status:
        payload = dict(current_status)
        payload["history_90d_backfilled_at"] = _datetime_to_iso(account.history_90d_backfilled_at)
        payload["history_90d_backfill_locked"] = account.history_90d_backfilled_at is not None
        return payload

    if account.history_90d_backfilled_at is not None:
        return _build_sync_history_status(
            account_id=account.id,
            account_name=account.name,
            days=ONE_TIME_HISTORY_BACKFILL_DAYS,
            status="completed",
            message="当前交易账户已经完成过一次 90 天历史回补",
            finished_at=account.history_90d_backfilled_at,
            history_90d_backfilled_at=account.history_90d_backfilled_at,
        )

    return _build_sync_history_status(
        account_id=account.id,
        account_name=account.name,
        days=ONE_TIME_HISTORY_BACKFILL_DAYS,
        status="idle",
        message="当前账户暂无进行中的历史回补任务",
        history_90d_backfilled_at=account.history_90d_backfilled_at,
    )


def _apply_record_scope(query, transaction_model, record_scope: str):
    if record_scope == "review":
        return query.filter(transaction_model.type.in_(REVIEW_RELEVANT_TRANSACTION_TYPES))
    if record_scope == "trades":
        return query.filter(transaction_model.type == "TRADE")
    if record_scope == "cashflow":
        return query.filter(transaction_model.type.in_(REVIEW_CASHFLOW_TRANSACTION_TYPES))
    return query


def _build_transaction_history_query(
    db: Session,
    account_id: Optional[int] = None,
    symbol: Optional[str] = None,
    transaction_type: Optional[str] = None,
    record_scope: str = "all",
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
):
    from app.models.risk_control import TransactionHistory

    query = db.query(TransactionHistory)

    if account_id is not None:
        query = query.filter(TransactionHistory.account_id == account_id)
    if symbol:
        query = query.filter(func.upper(TransactionHistory.symbol) == symbol.strip().upper())
    query = _apply_record_scope(query, TransactionHistory, record_scope)

    if transaction_type:
        query = query.filter(TransactionHistory.type == transaction_type)
    if start_time:
        query = query.filter(TransactionHistory.time >= start_time)
    if end_time:
        query = query.filter(TransactionHistory.time <= end_time)

    return query, TransactionHistory


def _sum_realized_pnl(query, transaction_model, types: List[str]) -> float:
    return float(
        query.filter(transaction_model.type.in_(types))
        .with_entities(func.sum(transaction_model.realized_pnl))
        .scalar()
        or 0.0
    )


def _coerce_time_range(start_time: Optional[datetime], end_time: Optional[datetime]) -> None:
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time must be earlier than end_time")


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _normalize_time_range(
    start_time: Optional[datetime],
    end_time: Optional[datetime]
) -> tuple[Optional[datetime], Optional[datetime]]:
    normalized_start = _normalize_datetime(start_time)
    normalized_end = _normalize_datetime(end_time)
    _coerce_time_range(normalized_start, normalized_end)
    return normalized_start, normalized_end


def _get_timeline_bucket_mode(start_time: Optional[datetime], end_time: Optional[datetime], history: list) -> str:
    effective_start = start_time or (history[0].time if history else None)
    effective_end = end_time or (history[-1].time if history else None)

    if not effective_start or not effective_end:
        return "day"

    return "hour" if (effective_end - effective_start) <= timedelta(days=2) else "day"


def _truncate_bucket(value: datetime, bucket_mode: str) -> datetime:
    if bucket_mode == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _format_bucket_label(value: datetime, bucket_mode: str) -> str:
    if bucket_mode == "hour":
        return value.strftime("%m-%d %H:00")
    return value.strftime("%m-%d")


def _timeline_contribution(item, transaction_type: Optional[str]) -> float:
    realized_pnl = float(item.realized_pnl or 0.0)
    commission = float(item.commission or 0.0)

    if transaction_type == "TRADE":
        return round(realized_pnl - commission, 2)
    if transaction_type == "COMMISSION":
        return round(realized_pnl, 2)
    if transaction_type in {"REALIZED_PNL", "FUNDING_FEE"}:
        return round(realized_pnl, 2)
    if transaction_type in {"TRANSFER", "INTERNAL_TRANSFER"}:
        return 0.0
    if transaction_type:
        return round(realized_pnl, 2)

    if item.type == "REALIZED_PNL":
        return round(realized_pnl, 2)
    if item.type == "FUNDING_FEE":
        return round(realized_pnl, 2)
    if item.type == "COMMISSION":
        return round(realized_pnl, 2)

    return 0.0


def _normalize_exchange_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in OKX_EXCHANGE_ALIASES:
        return "okx"
    return normalized


def _normalize_account_secret_fields(payload: dict) -> dict:
    normalized = dict(payload)
    if "exchange" in normalized:
        normalized["exchange"] = _normalize_exchange_name(normalized.get("exchange"))

    if "api_passphrase" in normalized and isinstance(normalized.get("api_passphrase"), str):
        normalized["api_passphrase"] = normalized["api_passphrase"].strip() or None

    return normalized


def _validate_account_exchange_credentials(exchange: Optional[str], api_passphrase: Optional[str]) -> None:
    if exchange == "okx" and not api_passphrase:
        raise HTTPException(status_code=400, detail="OKX account requires api_passphrase")

@router.post("/accounts/", response_model=schemas.AccountInDB)
async def create_account(account: schemas.AccountCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """创建交易账户"""
    from app.models.risk_control import Account

    payload = _normalize_account_secret_fields(account.dict())
    _validate_account_exchange_credentials(payload.get("exchange"), payload.get("api_passphrase"))

    db_account = Account(**payload)
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

@router.get("/accounts/{account_id}/risk-config", response_model=schemas.RiskConfigInDB)
async def get_risk_config(
    account_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取风控配置"""
    from app.models.risk_control import RiskConfig
    config = db.query(RiskConfig).filter(RiskConfig.account_id == account_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Risk configuration not found")
    return config

@router.put("/accounts/{account_id}/risk-config", response_model=schemas.RiskConfigInDB)
async def update_risk_config(
    account_id: int,
    config_update: schemas.RiskConfigUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """更新风控配置"""
    from app.models.risk_control import RiskConfig
    db_config = db.query(RiskConfig).filter(RiskConfig.account_id == account_id).first()
    
    if not db_config:
        # If not exists, create one (assuming account exists)
        # But we need to make sure account exists first
        from app.models.risk_control import Account
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
             raise HTTPException(status_code=404, detail="Account not found")
             
        # Create new config
        new_config_data = config_update.dict(exclude_unset=True)
        new_config_data["account_id"] = account_id
        db_config = RiskConfig(**new_config_data)
        db.add(db_config)
    else:
        # Update existing
        update_data = config_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_config, field, value)
            
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
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db)
):
    """List positions (optionally filter by account_id and is_active)"""
    from app.models.risk_control import Position

    query = db.query(Position)
    if account_id:
        query = query.filter(Position.account_id == account_id)
    if is_active is not None:
        query = query.filter(Position.is_active == is_active)

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

@router.put('/accounts/{account_id}', response_model=schemas.AccountInDB)
async def update_account(
    account_id: int,
    account_update: schemas.AccountUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update an account"""
    from app.models.risk_control import Account
    db_account = db.query(Account).filter(Account.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    update_data = _normalize_account_secret_fields(account_update.dict(exclude_unset=True))
    effective_exchange = update_data.get("exchange", db_account.exchange)
    effective_api_passphrase = update_data.get("api_passphrase", db_account.api_passphrase)
    _validate_account_exchange_credentials(effective_exchange, effective_api_passphrase)

    for field, value in update_data.items():
        setattr(db_account, field, value)
    
    db.commit()
    db.refresh(db_account)
    return db_account

@router.delete('/accounts/{account_id}', status_code=204)
async def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Delete an account"""
    from app.models.risk_control import Account
    db_account = db.query(Account).filter(Account.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    db.delete(db_account)
    db.commit()
    return None

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


@router.get('/accounts/{account_id}/connectivity', response_model=schemas.AccountConnectivityResult)
async def test_account_connectivity(
    account_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Run spot/futures connectivity checks for an account and return actionable hints."""
    from app.models.risk_control import Account
    from app.services.exchange.binance_adapter import create_adapter_for_account

    acct = db.query(Account).filter(Account.id == account_id).first()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    adapter = create_adapter_for_account(acct)
    if not adapter:
        raise HTTPException(status_code=400, detail="Adapter not available for this account")

    connectivity = await adapter.test_connectivity()
    return {
        "account_id": acct.id,
        "exchange": acct.exchange,
        "account_name": acct.name,
        **connectivity,
    }


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

@router.get("/alerts/", response_model=List[schemas.RiskAlertInDB])
async def get_alerts(
    skip: int = 0,
    limit: int = 100,
    is_resolved: Optional[bool] = None,
    risk_level: Optional[schemas.RiskLevel] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取风险预警列表"""
    from app.models.risk_control import RiskAlert
    query = db.query(RiskAlert)
    
    if is_resolved is not None:
        query = query.filter(RiskAlert.is_resolved == is_resolved)
    
    if risk_level:
        query = query.filter(RiskAlert.risk_level == risk_level)
        
    alerts = query.order_by(RiskAlert.created_at.desc()).offset(skip).limit(limit).all()
    return alerts

@router.put("/alerts/{alert_id}/resolve", response_model=schemas.RiskAlertInDB)
async def resolve_alert(
    alert_id: int,
    resolution: schemas.RiskAlertUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """处理/解决风险预警"""
    from app.models.risk_control import RiskAlert
    alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_resolved = resolution.is_resolved
    alert.resolution_notes = resolution.resolution_notes
    if resolution.is_resolved and not alert.resolved_at:
        alert.resolved_at = datetime.utcnow()
        
    db.commit()
    db.refresh(alert)
    return alert


@router.get("/history/transactions/summary", response_model=schemas.TransactionReviewSummary)
async def get_transaction_review_summary(
    account_id: Optional[int] = None,
    symbol: Optional[str] = None,
    transaction_type: Optional[str] = Query(None, alias="type"),
    record_scope: str = Query("review"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取交易复盘概览统计。"""
    start_time, end_time = _normalize_time_range(start_time, end_time)
    base_query, TransactionHistory = _build_transaction_history_query(
        db=db,
        account_id=account_id,
        symbol=symbol,
        transaction_type=transaction_type,
        record_scope=record_scope,
        start_time=start_time,
        end_time=end_time,
    )

    total_count = base_query.count()
    trade_query = base_query if transaction_type == "TRADE" else base_query.filter(TransactionHistory.type == "TRADE")
    trade_count = trade_query.count()
    win_count = trade_query.filter(TransactionHistory.realized_pnl > 0).count()
    loss_count = trade_query.filter(TransactionHistory.realized_pnl < 0).count()

    trade_realized_pnl = float(
        trade_query.with_entities(func.sum(TransactionHistory.realized_pnl)).scalar() or 0.0
    )
    trade_commission_cost = float(
        trade_query.with_entities(func.sum(TransactionHistory.commission)).scalar() or 0.0
    )

    if transaction_type == "TRADE":
        gross_realized_pnl = trade_realized_pnl
        commission_cost = trade_commission_cost
        funding_pnl = 0.0
        transfer_amount = 0.0
    elif transaction_type == "REALIZED_PNL":
        gross_realized_pnl = _sum_realized_pnl(base_query, TransactionHistory, ["REALIZED_PNL"])
        commission_cost = 0.0
        funding_pnl = 0.0
        transfer_amount = 0.0
    elif transaction_type == "COMMISSION":
        gross_realized_pnl = 0.0
        commission_cost = abs(_sum_realized_pnl(base_query, TransactionHistory, ["COMMISSION"]))
        funding_pnl = 0.0
        transfer_amount = 0.0
    elif transaction_type == "FUNDING_FEE":
        gross_realized_pnl = 0.0
        commission_cost = 0.0
        funding_pnl = _sum_realized_pnl(base_query, TransactionHistory, ["FUNDING_FEE"])
        transfer_amount = 0.0
    elif transaction_type in {"TRANSFER", "INTERNAL_TRANSFER"}:
        gross_realized_pnl = 0.0
        commission_cost = 0.0
        funding_pnl = 0.0
        transfer_amount = _sum_realized_pnl(base_query, TransactionHistory, [transaction_type])
    elif transaction_type:
        gross_realized_pnl = float(
            base_query.with_entities(func.sum(TransactionHistory.realized_pnl)).scalar() or 0.0
        )
        commission_cost = 0.0
        funding_pnl = 0.0
        transfer_amount = 0.0
    else:
        gross_realized_pnl = _sum_realized_pnl(base_query, TransactionHistory, ["REALIZED_PNL"])
        commission_cost = abs(_sum_realized_pnl(base_query, TransactionHistory, ["COMMISSION"]))
        funding_pnl = _sum_realized_pnl(base_query, TransactionHistory, ["FUNDING_FEE"])
        transfer_amount = _sum_realized_pnl(base_query, TransactionHistory, ["TRANSFER", "INTERNAL_TRANSFER"])

    win_rate = round((win_count / trade_count) * 100, 2) if trade_count else 0.0
    average_trade_pnl = round((trade_realized_pnl / trade_count), 2) if trade_count else 0.0

    positive_trade_pnl = float(
        trade_query.filter(TransactionHistory.realized_pnl > 0)
        .with_entities(func.sum(TransactionHistory.realized_pnl))
        .scalar()
        or 0.0
    )
    negative_trade_pnl = float(
        trade_query.filter(TransactionHistory.realized_pnl < 0)
        .with_entities(func.sum(TransactionHistory.realized_pnl))
        .scalar()
        or 0.0
    )

    profit_factor = None
    if negative_trade_pnl < 0:
        profit_factor = round(positive_trade_pnl / abs(negative_trade_pnl), 2)

    net_trading_pnl = round(gross_realized_pnl + funding_pnl - commission_cost, 2)

    return schemas.TransactionReviewSummary(
        total_count=total_count,
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_rate,
        gross_realized_pnl=round(gross_realized_pnl, 2),
        commission_cost=round(commission_cost, 2),
        funding_pnl=round(funding_pnl, 2),
        transfer_amount=round(transfer_amount, 2),
        net_trading_pnl=net_trading_pnl,
        average_trade_pnl=average_trade_pnl,
        profit_factor=profit_factor,
    )


@router.get("/history/transactions/timeline", response_model=schemas.TransactionHistoryTimeline)
async def get_transaction_review_timeline(
    account_id: Optional[int] = None,
    symbol: Optional[str] = None,
    transaction_type: Optional[str] = Query(None, alias="type"),
    record_scope: str = Query("review"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取交易复盘盈亏时间序列。"""
    start_time, end_time = _normalize_time_range(start_time, end_time)
    base_query, TransactionHistory = _build_transaction_history_query(
        db=db,
        account_id=account_id,
        symbol=symbol,
        transaction_type=transaction_type,
        record_scope=record_scope,
        start_time=start_time,
        end_time=end_time,
    )
    history = base_query.order_by(TransactionHistory.time.asc()).all()

    if not history:
        return schemas.TransactionHistoryTimeline(
            xAxis=[],
            series=[
                schemas.TransactionTimelineSeries(name="区间净值", type="bar", data=[]),
                schemas.TransactionTimelineSeries(name="累计净值", type="line", data=[]),
                schemas.TransactionTimelineSeries(name="成交笔数", type="line", data=[]),
            ],
        )

    bucket_mode = _get_timeline_bucket_mode(start_time, end_time, history)
    bucket_start = _truncate_bucket(start_time or history[0].time, bucket_mode)
    bucket_end = _truncate_bucket(end_time or history[-1].time, bucket_mode)
    step = timedelta(hours=1) if bucket_mode == "hour" else timedelta(days=1)

    bucket_values = {}
    bucket_trade_counts = {}
    for item in history:
        bucket_key = _truncate_bucket(item.time, bucket_mode)
        bucket_values[bucket_key] = round(
            bucket_values.get(bucket_key, 0.0) + _timeline_contribution(item, transaction_type),
            2,
        )
        if item.type == "TRADE":
            bucket_trade_counts[bucket_key] = bucket_trade_counts.get(bucket_key, 0) + 1

    buckets = []
    current = bucket_start
    while current <= bucket_end:
        buckets.append(current)
        current += step

    x_axis = [_format_bucket_label(bucket, bucket_mode) for bucket in buckets]
    period_values = [round(bucket_values.get(bucket, 0.0), 2) for bucket in buckets]
    trade_counts = [float(bucket_trade_counts.get(bucket, 0)) for bucket in buckets]

    cumulative_values = []
    running_total = 0.0
    for value in period_values:
        running_total = round(running_total + value, 2)
        cumulative_values.append(running_total)

    return schemas.TransactionHistoryTimeline(
        xAxis=x_axis,
        series=[
            schemas.TransactionTimelineSeries(name="区间净值", type="bar", data=period_values),
            schemas.TransactionTimelineSeries(name="累计净值", type="line", data=cumulative_values),
            schemas.TransactionTimelineSeries(name="成交笔数", type="line", data=trade_counts),
        ],
    )


@router.get("/history/completed-trades", response_model=schemas.CompletedTradeReviewList)
async def get_completed_trade_history(
    account_id: Optional[int] = None,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取按完整开平仓聚合后的已完成交易。"""
    start_time, end_time = _normalize_time_range(start_time, end_time)
    service = TradeReviewService(db)
    result = service.list_completed_trades(
        account_id=account_id,
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        limit=limit,
    )
    return schemas.CompletedTradeReviewList(**result)


@router.get("/history/completed-trades/summary", response_model=schemas.CompletedTradeReviewSummary)
async def get_completed_trade_summary(
    account_id: Optional[int] = None,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取完整交易口径的复盘概览。"""
    start_time, end_time = _normalize_time_range(start_time, end_time)
    service = TradeReviewService(db)
    result = service.summarize_completed_trades(
        account_id=account_id,
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
    )
    return schemas.CompletedTradeReviewSummary(**result)


@router.get("/history/completed-trades/timeline", response_model=schemas.TransactionHistoryTimeline)
async def get_completed_trade_timeline(
    account_id: Optional[int] = None,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取完整交易口径的复盘时间序列。"""
    start_time, end_time = _normalize_time_range(start_time, end_time)
    service = TradeReviewService(db)
    result = service.completed_trade_timeline(
        account_id=account_id,
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
    )
    return schemas.TransactionHistoryTimeline(**result)

@router.get("/history/transactions", response_model=List[schemas.TransactionHistoryInDB])
async def get_transaction_history(
    account_id: Optional[int] = None,
    symbol: Optional[str] = None,
    transaction_type: Optional[str] = Query(None, alias="type"),
    record_scope: str = Query("review"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """获取交易历史（包括资金费等）"""
    start_time, end_time = _normalize_time_range(start_time, end_time)
    query, TransactionHistory = _build_transaction_history_query(
        db=db,
        account_id=account_id,
        symbol=symbol,
        transaction_type=transaction_type,
        record_scope=record_scope,
        start_time=start_time,
        end_time=end_time,
    )

    history = query.order_by(TransactionHistory.time.desc()).offset(skip).limit(limit).all()
    return history

@router.post("/accounts/{account_id}/sync-history")
async def sync_account_history(
    account_id: int,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """按时间窗口回补账户历史数据，并补齐账户快照。"""
    from app.models.risk_control import Account
    from app.services.history_backfill_service import backfill_account_history
    
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if days >= ONE_TIME_HISTORY_BACKFILL_DAYS and account.history_90d_backfilled_at is not None:
        raise HTTPException(
            status_code=409,
            detail="当前交易账户已经完成过一次 90 天历史回补，不能重复执行",
        )
    try:
        result = await backfill_account_history(
            db,
            account,
            days=days,
            include_snapshots=True,
        )
        if days >= ONE_TIME_HISTORY_BACKFILL_DAYS and account.history_90d_backfilled_at is None:
            account.history_90d_backfilled_at = datetime.utcnow()
            db.add(account)
            db.commit()
            db.refresh(account)

        result["history_90d_backfilled_at"] = (
            account.history_90d_backfilled_at.isoformat() if account.history_90d_backfilled_at else None
        )
        result["history_90d_backfill_locked"] = account.history_90d_backfilled_at is not None
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        logging.exception("sync history failed for account %s", account_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/sync-history/start", status_code=202)
async def start_sync_account_history(
    account_id: int,
    days: int = Query(90, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Start account history backfill in the background so the UI does not wait on a long request."""
    from app.models.risk_control import Account

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if days >= ONE_TIME_HISTORY_BACKFILL_DAYS and account.history_90d_backfilled_at is not None:
        raise HTTPException(status_code=409, detail="当前交易账户已经完成过一次 90 天历史回补，不能重复执行")

    return _schedule_sync_history_job(
        account.id,
        account.name,
        days,
        account.history_90d_backfilled_at,
    )


@router.get("/accounts/{account_id}/sync-history/status")
async def get_sync_account_history_status(
    account_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Return the latest background sync-history status for a single account."""
    from app.models.risk_control import Account

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return _get_sync_history_status_payload(account)
