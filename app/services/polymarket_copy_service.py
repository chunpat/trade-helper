from collections import Counter
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.database import SessionLocal
from app.models.polymarket_copy import (
    PolymarketCopySignalLog,
    PolymarketCopySimulationRun,
    PolymarketCopyStrategy,
)
from app.schemas.polymarket import PolymarketActivityItem
from app.schemas.polymarket_copy import (
    PolymarketCopyRunnerStatus,
    PolymarketCopySimulationRequest,
    PolymarketCopySimulationResult,
    PolymarketCopySimulationSignal,
    PolymarketCopySimulationRunRead,
    PolymarketCopySimulationSummary,
    PolymarketCopyStrategyCreate,
    PolymarketCopyStrategyRead,
)
from app.services.polymarket_trader_analytics_service import (
    PolymarketTraderAnalyticsService,
    polymarket_trader_analytics_service,
)


class PolymarketCopyService:
    def __init__(
        self,
        analytics_service: Optional[PolymarketTraderAnalyticsService] = None,
        session_factory: Optional[Callable[[], Any]] = None,
    ):
        self.analytics_service = analytics_service or polymarket_trader_analytics_service
        self.session_factory = session_factory or SessionLocal

    def create_strategy(self, payload: PolymarketCopyStrategyCreate) -> PolymarketCopyStrategyRead:
        wallet = self.analytics_service.normalize_wallet(payload.source_wallet)
        db = self.session_factory()
        try:
            strategy = PolymarketCopyStrategy(
                strategy_name=payload.strategy_name.strip(),
                source_wallet=wallet,
                status="draft",
                copy_mode=payload.copy_mode,
                copy_ratio=payload.copy_ratio,
                min_copy_order_usdc=payload.min_copy_order_usdc,
                max_order_usdc=payload.max_order_usdc,
                max_position_notional_usdc=payload.max_position_notional_usdc,
                max_market_exposure_usdc=payload.max_market_exposure_usdc,
                max_signal_delay_seconds=payload.max_signal_delay_seconds,
                max_slippage_bps=payload.max_slippage_bps,
                close_only=payload.close_only,
                dry_run=payload.dry_run,
                same_outcome_only=payload.same_outcome_only,
                follow_reduce_only_after_open=payload.follow_reduce_only_after_open,
                allow_partial_close_sync=payload.allow_partial_close_sync,
                signal_cooldown_seconds=payload.signal_cooldown_seconds,
                runner_lookback_hours=payload.runner_lookback_hours,
                runner_activity_limit=payload.runner_activity_limit,
                allowed_markets=payload.allowed_markets,
                blocked_markets=payload.blocked_markets,
                notes=payload.notes,
            )
            db.add(strategy)
            db.commit()
            db.refresh(strategy)
            return self._to_strategy_read(strategy)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_strategy(self, strategy_id: int) -> Optional[PolymarketCopyStrategyRead]:
        db = self.session_factory()
        try:
            row = db.query(PolymarketCopyStrategy).filter(PolymarketCopyStrategy.id == strategy_id).first()
            return self._to_strategy_read(row) if row else None
        finally:
            db.close()

    def list_strategies(self) -> List[PolymarketCopyStrategyRead]:
        db = self.session_factory()
        try:
            rows = db.query(PolymarketCopyStrategy).order_by(PolymarketCopyStrategy.created_at.desc()).all()
            return [self._to_strategy_read(row) for row in rows]
        finally:
            db.close()

    def list_simulation_runs(self, strategy_id: int, limit: int = 20) -> List[PolymarketCopySimulationRunRead]:
        db = self.session_factory()
        try:
            rows = (
                db.query(PolymarketCopySimulationRun)
                .filter(PolymarketCopySimulationRun.strategy_id == strategy_id)
                .order_by(PolymarketCopySimulationRun.created_at.desc())
                .limit(limit)
                .all()
            )
            return [PolymarketCopySimulationRunRead.model_validate({**row.to_dict(), "summary": row.summary or {}}) for row in rows]
        finally:
            db.close()

    def start_strategy(self, strategy_id: int) -> Optional[PolymarketCopyStrategyRead]:
        return self._update_strategy_status(strategy_id, status="running")

    def stop_strategy(self, strategy_id: int) -> Optional[PolymarketCopyStrategyRead]:
        return self._update_strategy_status(strategy_id, status="stopped")

    def _update_strategy_status(self, strategy_id: int, *, status: str) -> Optional[PolymarketCopyStrategyRead]:
        db = self.session_factory()
        try:
            row = db.query(PolymarketCopyStrategy).filter(PolymarketCopyStrategy.id == strategy_id).first()
            if row is None:
                return None
            row.status = status
            if status == "running":
                row.last_started_at = datetime.utcnow()
                row.last_error = None
            elif status == "stopped":
                row.last_stopped_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._to_strategy_read(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def simulate_strategy(
        self,
        strategy_id: int,
        payload: PolymarketCopySimulationRequest,
    ) -> Optional[PolymarketCopySimulationResult]:
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            return None

        activities = await self.analytics_service.get_activity(
            strategy.source_wallet,
            limit=payload.activity_limit,
            hours=payload.lookback_hours,
        )
        raw_trades = [item for item in activities if item.activity_type == "TRADE"]
        grouped_trades = self.analytics_service._group_trade_activities(raw_trades)
        grouped_trades = sorted(grouped_trades, key=lambda item: item.timestamp)

        signals: List[PolymarketCopySimulationSignal] = []
        skip_reason_counts: Counter = Counter()
        source_positions: Dict[Tuple[str, str, str], Dict[str, float]] = {}
        follower_positions: Dict[Tuple[str, str, str], Dict[str, float]] = {}
        total_source_notional = 0.0
        total_copied_notional = 0.0

        for index, trade in enumerate(grouped_trades, start=1):
            signal = self._simulate_trade_signal(
                signal_index=index,
                trade=trade,
                strategy=strategy,
                source_positions=source_positions,
                follower_positions=follower_positions,
            )
            total_source_notional += signal.source_trade_usdc
            if signal.status == "executed":
                total_copied_notional += signal.follower_order_usdc
            elif signal.skip_reason:
                skip_reason_counts[signal.skip_reason] += 1
            signals.append(signal)

        summary = PolymarketCopySimulationSummary(
            raw_trade_count=len(raw_trades),
            grouped_trade_count=len(grouped_trades),
            simulated_signal_count=len(signals),
            executed_signal_count=len([item for item in signals if item.status == "executed"]),
            skipped_signal_count=len([item for item in signals if item.status == "skipped"]),
            total_source_notional_usdc=round(total_source_notional, 4),
            total_copied_notional_usdc=round(total_copied_notional, 4),
            skip_reason_counts=dict(skip_reason_counts),
        )
        notes = [
            "V1 模拟按源单名义金额同比例复制开仓/加仓，减仓和平仓按源仓位变化比例同步。",
            "当前模拟仅基于公开 TRADE 活动，不处理 MERGE、SPLIT、REDEEM。",
        ]

        run_id = self._persist_simulation_run(strategy_id, payload, summary)
        return PolymarketCopySimulationResult(
            strategy=strategy,
            simulation_run_id=run_id,
            lookback_hours=payload.lookback_hours,
            activity_limit=payload.activity_limit,
            summary=summary,
            signals=signals,
            notes=notes,
        )

    async def run_strategy_cycle(self, strategy_id: int) -> Optional[PolymarketCopySimulationResult]:
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            return None
        payload = PolymarketCopySimulationRequest(
            lookback_hours=strategy.runner_lookback_hours,
            activity_limit=strategy.runner_activity_limit,
        )
        result = await self.simulate_strategy(strategy_id, payload)
        if result is None:
            return None
        self._persist_signal_logs(strategy_id, result)
        self._mark_strategy_run(strategy_id)
        return result

    def _mark_strategy_run(self, strategy_id: int, error_message: Optional[str] = None) -> None:
        db = self.session_factory()
        try:
            row = db.query(PolymarketCopyStrategy).filter(PolymarketCopyStrategy.id == strategy_id).first()
            if row is None:
                return
            row.last_run_at = datetime.utcnow()
            row.last_error = error_message
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def record_strategy_error(self, strategy_id: int, error_message: str) -> None:
        self._mark_strategy_run(strategy_id, error_message=error_message)

    def _persist_signal_logs(self, strategy_id: int, result: PolymarketCopySimulationResult) -> int:
        db = self.session_factory()
        inserted = 0
        try:
            existing_keys = {
                item[0]
                for item in db.query(PolymarketCopySignalLog.idempotency_key)
                .filter(PolymarketCopySignalLog.strategy_id == strategy_id)
                .all()
            }
            for signal in result.signals:
                idempotency_key = self._build_signal_idempotency_key(strategy_id, signal)
                if idempotency_key in existing_keys:
                    continue
                db.add(
                    PolymarketCopySignalLog(
                        strategy_id=strategy_id,
                        simulation_run_id=result.simulation_run_id,
                        idempotency_key=idempotency_key,
                        signal_type=signal.signal_type,
                        signal_status=signal.status,
                        source_timestamp=signal.source_timestamp,
                        condition_id=signal.condition_id,
                        asset=signal.asset,
                        outcome=signal.outcome,
                        side=signal.side,
                        source_trade_usdc=signal.source_trade_usdc,
                        follower_order_usdc=signal.follower_order_usdc,
                        skip_reason=signal.skip_reason,
                        signal_payload=signal.model_dump(mode="json"),
                    )
                )
                existing_keys.add(idempotency_key)
                inserted += 1
            db.commit()
            return inserted
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _build_signal_idempotency_key(strategy_id: int, signal: PolymarketCopySimulationSignal) -> str:
        timestamp_bucket = int(signal.source_timestamp.timestamp())
        return ":".join(
            [
                str(strategy_id),
                signal.signal_type,
                signal.condition_id or "unknown",
                signal.asset or "unknown",
                signal.outcome or "unknown",
                signal.side or "unknown",
                str(timestamp_bucket),
            ]
        )

    def list_running_strategy_ids(self) -> List[int]:
        db = self.session_factory()
        try:
            rows = (
                db.query(PolymarketCopyStrategy.id)
                .filter(PolymarketCopyStrategy.status == "running")
                .all()
            )
            return [row[0] for row in rows]
        finally:
            db.close()

    def _persist_simulation_run(
        self,
        strategy_id: int,
        payload: PolymarketCopySimulationRequest,
        summary: PolymarketCopySimulationSummary,
    ) -> int:
        db = self.session_factory()
        try:
            row = PolymarketCopySimulationRun(
                strategy_id=strategy_id,
                lookback_hours=payload.lookback_hours,
                activity_limit=payload.activity_limit,
                raw_trade_count=summary.raw_trade_count,
                grouped_trade_count=summary.grouped_trade_count,
                simulated_signal_count=summary.simulated_signal_count,
                executed_signal_count=summary.executed_signal_count,
                skipped_signal_count=summary.skipped_signal_count,
                total_source_notional_usdc=summary.total_source_notional_usdc,
                total_copied_notional_usdc=summary.total_copied_notional_usdc,
                summary=summary.model_dump(mode="json"),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _simulate_trade_signal(
        self,
        *,
        signal_index: int,
        trade: PolymarketActivityItem,
        strategy: PolymarketCopyStrategyRead,
        source_positions: Dict[Tuple[str, str, str], Dict[str, float]],
        follower_positions: Dict[Tuple[str, str, str], Dict[str, float]],
    ) -> PolymarketCopySimulationSignal:
        position_key = (
            trade.condition_id or trade.title or "unknown",
            trade.asset or "unknown",
            trade.outcome or "unknown",
        )
        source_state = source_positions.setdefault(position_key, {"size": 0.0, "notional": 0.0})
        follower_state = follower_positions.setdefault(position_key, {"size": 0.0, "notional": 0.0})

        trade_size = float(trade.size or 0.0)
        trade_usdc = float(self.analytics_service._trade_usdc_size(trade) or 0.0)
        side = (trade.side or "").upper()
        source_before = float(source_state["size"])
        follower_before = float(follower_state["size"])

        signal_type = "OPEN"
        source_after = source_before
        follower_after = follower_before
        follower_order_usdc = 0.0
        source_reduce_ratio = None
        status = "executed"
        skip_reason = None

        if side == "BUY":
            signal_type = "OPEN" if source_before <= 0 else "ADD"
            source_after = source_before + trade_size
            if strategy.close_only:
                status = "skipped"
                skip_reason = "close_only"
            else:
                follower_order_usdc = min(trade_usdc * strategy.copy_ratio, strategy.max_order_usdc)
                market_notional_after = float(follower_state["notional"]) + follower_order_usdc
                if follower_order_usdc < strategy.min_copy_order_usdc:
                    status = "skipped"
                    skip_reason = "below_min_copy_order"
                elif market_notional_after > strategy.max_market_exposure_usdc:
                    status = "skipped"
                    skip_reason = "market_exposure_limit"
                elif market_notional_after > strategy.max_position_notional_usdc:
                    status = "skipped"
                    skip_reason = "position_limit"
                else:
                    follower_size_delta = trade_size * strategy.copy_ratio
                    follower_after = follower_before + follower_size_delta
                    follower_state["size"] = follower_after
                    follower_state["notional"] = market_notional_after
        elif side == "SELL":
            source_reduced_size = min(trade_size, source_before) if source_before > 0 else trade_size
            source_after = max(0.0, source_before - source_reduced_size)
            signal_type = "CLOSE" if source_after <= 1e-9 else "REDUCE"
            if source_before <= 0 and strategy.follow_reduce_only_after_open:
                status = "skipped"
                skip_reason = "no_source_position_context"
            else:
                source_reduce_ratio = source_reduced_size / source_before if source_before > 0 else 1.0
                if follower_before <= 0:
                    status = "skipped"
                    skip_reason = "no_follower_position"
                else:
                    follower_size_delta = follower_before * source_reduce_ratio
                    follower_after = max(0.0, follower_before - follower_size_delta)
                    follower_order_usdc = min(float(follower_state["notional"]) * source_reduce_ratio, trade_usdc * strategy.copy_ratio)
                    follower_state["size"] = follower_after
                    follower_state["notional"] = max(0.0, float(follower_state["notional"]) - follower_order_usdc)
        else:
            status = "skipped"
            skip_reason = "unsupported_side"

        source_state["size"] = source_after
        if side == "BUY":
            source_state["notional"] = float(source_state["notional"]) + trade_usdc
        elif side == "SELL":
            source_state["notional"] = max(0.0, float(source_state["notional"]) - trade_usdc)

        return PolymarketCopySimulationSignal(
            signal_index=signal_index,
            signal_type=signal_type,
            source_timestamp=trade.timestamp,
            title=trade.title,
            condition_id=trade.condition_id,
            asset=trade.asset,
            outcome=trade.outcome,
            side=trade.side,
            source_trade_usdc=round(trade_usdc, 4),
            source_position_before=round(source_before, 4),
            source_position_after=round(source_after, 4),
            source_reduce_ratio=round(source_reduce_ratio, 4) if source_reduce_ratio is not None else None,
            follower_order_usdc=round(follower_order_usdc, 4),
            follower_position_before=round(follower_before, 4),
            follower_position_after=round(follower_after, 4),
            status=status,
            skip_reason=skip_reason,
        )

    @staticmethod
    def _to_strategy_read(row: PolymarketCopyStrategy) -> PolymarketCopyStrategyRead:
        return PolymarketCopyStrategyRead.model_validate(
            {
                **row.to_dict(),
                "allowed_markets": row.allowed_markets or [],
                "blocked_markets": row.blocked_markets or [],
            }
        )


polymarket_copy_service = PolymarketCopyService()