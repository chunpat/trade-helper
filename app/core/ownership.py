"""请求级数据隔离；后台采集任务仍使用独立的系统会话。"""

from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import event, inspect, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, with_loader_criteria

from app.core.database import SessionLocal
from app.core.deps import get_current_user
from app.models.polymarket_copy import (
    PolymarketCopySignalLog,
    PolymarketCopySimulationRun,
    PolymarketCopySourcePosition,
    PolymarketCopyStrategy,
)
from app.models.risk_control import (
    Account,
    AccountSnapshot,
    DailyTradeReview,
    OrderLog,
    Position,
    RiskAlert,
    RiskConfig,
    TickerHistory,
    TransactionHistory,
    User,
)

ACCOUNT_DATA_MODELS = (
    AccountSnapshot,
    DailyTradeReview,
    OrderLog,
    Position,
    RiskAlert,
    RiskConfig,
    TickerHistory,
    TransactionHistory,
)
STRATEGY_DATA_MODELS = (
    PolymarketCopySignalLog,
    PolymarketCopySimulationRun,
    PolymarketCopySourcePosition,
)


def owner_filter(model: Any, user: User):
    condition = model.user_id == user.id
    # 迁移时没有管理员的旧数据仅允许后续管理员接管。
    if user.is_admin:
        condition = or_(condition, model.user_id.is_(None))
    return condition


def scope_session(db: Session, user: User) -> Session:
    """在新建会话上限制列表、聚合、关联加载和写入，避免遗漏单个接口。"""
    account_ids = select(Account.id).where(owner_filter(Account, user))
    strategy_ids = select(PolymarketCopyStrategy.id).where(
        owner_filter(PolymarketCopyStrategy, user)
    )
    options = [
        with_loader_criteria(
            Account, owner_filter(Account, user), include_aliases=True
        ),
        with_loader_criteria(
            PolymarketCopyStrategy,
            owner_filter(PolymarketCopyStrategy, user),
            include_aliases=True,
        ),
    ]
    options.extend(
        with_loader_criteria(
            model, model.account_id.in_(account_ids), include_aliases=True
        )
        for model in ACCOUNT_DATA_MODELS
    )
    options.extend(
        with_loader_criteria(
            model, model.strategy_id.in_(strategy_ids), include_aliases=True
        )
        for model in STRATEGY_DATA_MODELS
    )

    @event.listens_for(db, "do_orm_execute")
    def restrict_queries(execute_state):
        if not execute_state.is_select or not execute_state.is_orm_statement:
            raise HTTPException(
                status_code=403, detail="用户会话不允许执行未隔离的批量操作"
            )
        execute_state.statement = execute_state.statement.options(*options)

    @event.listens_for(db, "before_flush")
    def validate_writes(session, flush_context, instances):
        for obj in session.new.union(session.dirty).union(session.deleted):
            if isinstance(obj, (Account, PolymarketCopyStrategy)):
                if obj in session.new:
                    obj.user_id = user.id
                elif inspect(obj).attrs.user_id.history.has_changes():
                    raise HTTPException(
                        status_code=403, detail="不允许变更数据所属用户"
                    )
                elif obj.user_id != user.id and not (
                    user.is_admin and obj.user_id is None
                ):
                    raise HTTPException(status_code=404, detail="数据不存在")
            if isinstance(obj, ACCOUNT_DATA_MODELS):
                require_account(session, obj.account_id)
            if (
                isinstance(obj, PolymarketCopyStrategy)
                and obj.execution_account_id is not None
            ):
                require_account(session, obj.execution_account_id)
            if isinstance(obj, STRATEGY_DATA_MODELS):
                strategy = (
                    session.query(PolymarketCopyStrategy)
                    .filter_by(id=obj.strategy_id)
                    .first()
                )
                if strategy is None:
                    raise HTTPException(status_code=404, detail="策略不存在")

    return db


def require_account(db: Session, account_id: int) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="账户不存在")
    return account


def get_user_db(current_user=Depends(get_current_user)):
    db = scope_session(SessionLocal(), current_user)
    try:
        yield db
    finally:
        db.close()


def migrate_ownership(engine: Engine) -> None:
    """幂等补齐归属字段，将旧数据交给现有管理员；失败时阻止启动。"""
    with engine.begin() as conn:
        mysql = conn.dialect.name == "mysql"
        if (
            mysql
            and conn.execute(
                text("SELECT GET_LOCK('trade_helper_ownership_v1', 30)")
            ).scalar()
            != 1
        ):
            raise RuntimeError("无法取得用户归属迁移锁")
        try:
            _migrate_ownership(conn)
        finally:
            if mysql:
                conn.execute(text("SELECT RELEASE_LOCK('trade_helper_ownership_v1')"))


def _migrate_ownership(conn) -> None:
    for table in ("accounts", "polymarket_copy_strategies"):
        columns = {column["name"] for column in inspect(conn).get_columns(table)}
        if "user_id" not in columns:
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NULL REFERENCES users(id)"
                )
            )
        index_name = f"ix_{table}_user_id"
        if index_name not in {
            index["name"] for index in inspect(conn).get_indexes(table)
        }:
            conn.execute(text(f"CREATE INDEX {index_name} ON {table} (user_id)"))
    admin_id = conn.execute(
        text(
            "SELECT id FROM users WHERE is_admin = true AND is_active = true "
            "ORDER BY CASE WHEN username = 'admin' THEN 0 ELSE 1 END, id LIMIT 1"
        )
    ).scalar()
    # 有执行账户的旧策略优先跟随账户归属。
    conn.execute(
        text(
            "UPDATE polymarket_copy_strategies SET user_id = "
            "(SELECT user_id FROM accounts WHERE accounts.id = execution_account_id) "
            "WHERE user_id IS NULL AND execution_account_id IS NOT NULL"
        )
    )
    if admin_id is not None:
        for table in ("accounts", "polymarket_copy_strategies"):
            conn.execute(
                text(f"UPDATE {table} SET user_id = :user_id WHERE user_id IS NULL"),
                {"user_id": admin_id},
            )
