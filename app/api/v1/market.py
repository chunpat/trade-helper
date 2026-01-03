from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.risk_control import TickerHistory
from app.schemas.risk_control import TickerHistoryInDB

router = APIRouter(prefix="/market", tags=["market"])


@router.get('/ticker-history', response_model=List[TickerHistoryInDB])
async def get_ticker_history(
    symbol: Optional[str] = None,
    account_id: Optional[int] = None,
    position_id: Optional[int] = None,
    limit: int = Query(50, gt=0, le=500),
    db: Session = Depends(get_db),
):
    """Return recent ticker history.

    Filters: symbol, account_id, position_id. Sorted by newest first.
    """
    query = db.query(TickerHistory)
    if symbol:
        query = query.filter(TickerHistory.symbol == symbol)
    if account_id:
        query = query.filter(TickerHistory.account_id == account_id)
    if position_id:
        query = query.filter(TickerHistory.position_id == position_id)

    return query.order_by(TickerHistory.timestamp.desc()).limit(limit).all()
