from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.database import SessionLocal
from app.models.risk_control import Account
from app.models.polymarket_copy import (
    PolymarketCopySignalLog,
    PolymarketCopySourcePosition,
    PolymarketCopySimulationRun,
    PolymarketCopyStrategy,
)
from app.schemas.polymarket import PolymarketActivityItem
from app.schemas.polymarket_copy import (
    PolymarketLivePreflightCheck,
    PolymarketLivePreflightResult,
    PolymarketCopyRunnerStatus,
    PolymarketCopySimulationRequest,
    PolymarketCopySimulationResult,
    PolymarketCopySimulationSignal,
    PolymarketCopySimulationRunRead,
    PolymarketCopySimulationSummary,
    PolymarketCopyStrategyCreate,
    PolymarketCopyStrategyRead,
)
from app.services.exchange.binance_adapter import create_adapter_for_account
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
            execution_account = self._validate_execution_account(
                db,
                payload.execution_account_id,
                require_for_live=not payload.dry_run,
            )
            strategy = PolymarketCopyStrategy(
                strategy_name=payload.strategy_name.strip(),
                source_wallet=wallet,
                execution_account_id=execution_account.id if execution_account else None,
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
            return self._to_strategy_read(strategy, execution_account=execution_account)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_strategy(self, strategy_id: int) -> Optional[PolymarketCopyStrategyRead]:
        db = self.session_factory()
        try:
            row = db.query(PolymarketCopyStrategy).filter(PolymarketCopyStrategy.id == strategy_id).first()
            if row is None:
                return None
            execution_account = self._load_execution_account(db, row.execution_account_id)
            return self._to_strategy_read(row, execution_account=execution_account)
        finally:
            db.close()

    def list_strategies(self) -> List[PolymarketCopyStrategyRead]:
        db = self.session_factory()
        try:
            rows = db.query(PolymarketCopyStrategy).order_by(PolymarketCopyStrategy.created_at.desc()).all()
            account_ids = {row.execution_account_id for row in rows if row.execution_account_id is not None}
            accounts = self._load_execution_accounts(db, account_ids)
            return [self._to_strategy_read(row, execution_account=accounts.get(row.execution_account_id)) for row in rows]
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
            if status == "running":
                self._validate_startable_strategy(db, row)
            execution_account = self._load_execution_account(db, row.execution_account_id)
            row.status = status
            if status == "running":
                row.last_started_at = datetime.utcnow()
                row.last_error = None
            elif status == "stopped":
                if row.execution_account_id and not row.dry_run and execution_account is not None:
                    self._cancel_pending_live_orders(row.id, execution_account)
                row.last_stopped_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._to_strategy_read(row, execution_account=execution_account)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _validate_startable_strategy(self, db: Any, row: PolymarketCopyStrategy) -> None:
        if row.dry_run:
            return
        account = self._validate_execution_account(db, row.execution_account_id, require_for_live=True)
        adapter = create_adapter_for_account(account)
        if adapter is None:
            raise ValueError("Polymarket 执行适配器不可用")
        can_place_orders = getattr(adapter, "can_place_orders", None)
        if callable(can_place_orders):
            can_place, reason = can_place_orders()
            if not can_place:
                raise ValueError(reason or "当前账户不满足 Polymarket live 下单条件")

    @staticmethod
    def _apply_max_limit(value: float, limit_value: float) -> float:
        if limit_value <= 0:
            return value
        return min(value, limit_value)

    @staticmethod
    def _is_limit_exceeded(value: float, limit_value: float) -> bool:
        if limit_value <= 0:
            return False
        return value > limit_value

    def _validate_execution_account(
        self,
        db: Any,
        execution_account_id: Optional[int],
        *,
        require_for_live: bool,
    ) -> Optional[Account]:
        if execution_account_id is None:
            if require_for_live:
                raise ValueError("真实交易模式必须绑定一个有效的交易账户")
            return None

        account = db.query(Account).filter(Account.id == execution_account_id).first()
        if account is None:
            raise ValueError("绑定的交易账户不存在")
        if not account.is_active:
            raise ValueError("绑定的交易账户已停用，无法用于真实交易")
        if str(account.exchange or "").strip().lower() != "polymarket":
            raise ValueError("Polymarket 跟单策略只能绑定 Polymarket 账户")
        return account

    @staticmethod
    def _load_execution_account(db: Any, execution_account_id: Optional[int]) -> Optional[Account]:
        if execution_account_id is None:
            return None
        return db.query(Account).filter(Account.id == execution_account_id).first()

    @staticmethod
    def _load_execution_accounts(db: Any, account_ids: set[int]) -> Dict[int, Account]:
        if not account_ids:
            return {}
        rows = db.query(Account).filter(Account.id.in_(account_ids)).all()
        return {row.id: row for row in rows}

    async def simulate_strategy(
        self,
        strategy_id: int,
        payload: PolymarketCopySimulationRequest,
    ) -> Optional[PolymarketCopySimulationResult]:
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            return None

        result = await self._preview_strategy(strategy, payload)
        run_id = self._persist_simulation_run(strategy_id, payload, result.summary)
        return PolymarketCopySimulationResult(
            strategy=result.strategy,
            simulation_run_id=run_id,
            lookback_hours=result.lookback_hours,
            activity_limit=result.activity_limit,
            summary=result.summary,
            signals=result.signals,
            notes=result.notes,
        )

    async def preflight_live_strategy(
        self,
        strategy_id: int,
        payload: Optional[PolymarketCopySimulationRequest] = None,
    ) -> Optional[PolymarketLivePreflightResult]:
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            return None
        if strategy.dry_run:
            raise ValueError("dry-run 策略无需做 live 预检")

        request_payload = payload or PolymarketCopySimulationRequest(
            lookback_hours=strategy.runner_lookback_hours,
            activity_limit=strategy.runner_activity_limit,
        )

        db = self.session_factory()
        try:
            account = self._validate_execution_account(db, strategy.execution_account_id, require_for_live=True)
        finally:
            db.close()

        adapter = create_adapter_for_account(account)
        if adapter is None:
            raise ValueError("Polymarket 执行适配器不可用")

        connectivity = await adapter.test_connectivity()
        checks = self._extract_preflight_checks(connectivity)
        preview = await self._preview_strategy(strategy, request_payload)
        executable_signals = [item for item in preview.signals if item.status == "executed"]
        sample_signal = next((item for item in executable_signals if item.asset), None)

        notes = list(preview.notes)
        if connectivity.get("account_mode_note"):
            notes.append(str(connectivity["account_mode_note"]))

        if sample_signal is not None:
            orderbook_check = await adapter.preflight_orderbook(sample_signal.asset, sample_signal.side or "BUY")
            checks.append(self._to_preflight_check("sample_orderbook", orderbook_check))
        else:
            checks.append(
                PolymarketLivePreflightCheck(
                    name="sample_orderbook",
                    endpoint="/book",
                    ok=True,
                    status_code=204,
                    message="当前窗口内没有可执行信号，未执行盘口检查",
                    hint="可增大回看窗口，或等源钱包产生新成交后再做一次 live 预检。",
                )
            )

        overall_ok = all(check.ok for check in checks if check.status_code != 204)
        return PolymarketLivePreflightResult(
            strategy=strategy,
            account_id=account.id,
            account_name=account.name,
            exchange=account.exchange,
            checked_at=datetime.utcnow(),
            overall_ok=overall_ok,
            overall_hint=(
                connectivity.get("overall_hint")
                or ("live 预检通过，可以继续进入真实下单执行接线阶段。" if overall_ok else "live 预检未通过，请先处理失败检查项。")
            ),
            executable_signal_count=len(executable_signals),
            sample_signal=sample_signal,
            checks=checks,
            notes=notes,
        )

    async def _preview_strategy(
        self,
        strategy: PolymarketCopyStrategyRead,
        payload: PolymarketCopySimulationRequest,
    ) -> PolymarketCopySimulationResult:
        activities = await self.analytics_service.get_activity(
            strategy.source_wallet,
            limit=payload.activity_limit,
            hours=payload.lookback_hours,
        )
        raw_trades = [item for item in activities if item.activity_type == "TRADE"]
        grouped_trades = self.analytics_service._group_trade_activities(raw_trades)
        grouped_trades = sorted(grouped_trades, key=lambda item: item.timestamp)

        summary, signals = self._build_simulation_signals(
            grouped_trades=grouped_trades,
            strategy=strategy,
            source_positions={},
            follower_positions={},
            raw_trade_count=len(raw_trades),
        )
        return PolymarketCopySimulationResult(
            strategy=strategy,
            simulation_run_id=None,
            lookback_hours=payload.lookback_hours,
            activity_limit=payload.activity_limit,
            summary=summary,
            signals=signals,
            notes=[
                "V1 模拟按源单名义金额同比例复制开仓/加仓，减仓和平仓按源仓位变化比例同步。",
                "当前模拟仅基于公开 TRADE 活动，不处理 MERGE、SPLIT、REDEEM。",
            ],
        )

    async def run_strategy_cycle(self, strategy_id: int) -> Optional[PolymarketCopySimulationResult]:
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            return None
        payload = PolymarketCopySimulationRequest(
            lookback_hours=strategy.runner_lookback_hours,
            activity_limit=strategy.runner_activity_limit,
        )
        raw_trades, grouped_trades = await self._load_incremental_grouped_trades(strategy, payload)
        source_positions, follower_positions = self._load_shadow_positions(strategy_id)
        planned_source_positions = deepcopy(source_positions)
        planned_follower_positions = deepcopy(follower_positions)

        summary, signals = self._build_simulation_signals(
            grouped_trades=grouped_trades,
            strategy=strategy,
            source_positions=planned_source_positions,
            follower_positions=planned_follower_positions,
            raw_trade_count=len(raw_trades),
        )
        notes = [
            "Runner 模式按最新 source activity watermark 增量抓取成交，并持久化 source/follower 影子仓位。",
            "无新增 grouped trade 时不会写入新的 simulation run。",
        ]
        live_execution_results: Dict[str, Dict[str, Any]] = {}

        if grouped_trades and not strategy.dry_run:
            live_execution_results, follower_positions = self._execute_live_signals(
                strategy=strategy,
                signals=signals,
                follower_positions=follower_positions,
            )
            notes.append("live 模式会把可执行信号提交到 Polymarket CLOB，并把订单回执写入 signal log。")
        else:
            follower_positions = planned_follower_positions

        run_id = None
        if grouped_trades:
            run_id = self._persist_simulation_run(strategy_id, payload, summary)

        result = PolymarketCopySimulationResult(
            strategy=strategy,
            simulation_run_id=run_id,
            lookback_hours=payload.lookback_hours,
            activity_limit=payload.activity_limit,
            summary=summary,
            signals=signals,
            notes=notes,
        )

        if grouped_trades:
            self._persist_shadow_positions(strategy_id, planned_source_positions, follower_positions)
            self._persist_signal_logs(strategy_id, result, execution_results=live_execution_results)
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

    def _persist_signal_logs(
        self,
        strategy_id: int,
        result: PolymarketCopySimulationResult,
        *,
        execution_results: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> int:
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
                execution_payload = (execution_results or {}).get(idempotency_key) or {}
                serializable_execution_payload = {
                    key: value.isoformat() if isinstance(value, datetime) else value
                    for key, value in execution_payload.items()
                }
                signal_payload = signal.model_dump(mode="json")
                if serializable_execution_payload:
                    signal_payload["live_execution"] = serializable_execution_payload
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
                        source_trade_size=signal.source_trade_size,
                        source_trade_usdc=signal.source_trade_usdc,
                        follower_order_usdc=signal.follower_order_usdc,
                        skip_reason=signal.skip_reason,
                        live_execution_status=execution_payload.get("execution_status"),
                        live_order_id=execution_payload.get("order_id"),
                        live_order_status=execution_payload.get("order_status"),
                        live_execution_error=execution_payload.get("execution_error"),
                        live_order_response=execution_payload.get("order_response"),
                        live_executed_at=execution_payload.get("executed_at"),
                        live_canceled_at=execution_payload.get("canceled_at"),
                        live_cancel_response=execution_payload.get("cancel_response"),
                        live_cancel_error=execution_payload.get("cancel_error"),
                        signal_payload=signal_payload,
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
                signal.condition_id or "unknown",
                signal.asset or "unknown",
                signal.outcome or "unknown",
                signal.side or "unknown",
                f"{signal.source_trade_size:.6f}",
                f"{signal.source_trade_usdc:.6f}",
                str(timestamp_bucket),
            ]
        )

    def _build_trade_idempotency_key(self, strategy_id: int, trade: PolymarketActivityItem) -> str:
        trade_size = float(trade.size or 0.0)
        trade_usdc = float(self.analytics_service._trade_usdc_size(trade) or 0.0)
        timestamp_bucket = int(trade.timestamp.timestamp())
        return ":".join(
            [
                str(strategy_id),
                trade.condition_id or "unknown",
                trade.asset or "unknown",
                trade.outcome or "unknown",
                trade.side or "unknown",
                f"{trade_size:.6f}",
                f"{trade_usdc:.6f}",
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

    async def _load_incremental_grouped_trades(
        self,
        strategy: PolymarketCopyStrategyRead,
        payload: PolymarketCopySimulationRequest,
    ) -> Tuple[List[PolymarketActivityItem], List[PolymarketActivityItem]]:
        wallet = self.analytics_service.normalize_wallet(strategy.source_wallet)
        cutoff = datetime.utcnow() - timedelta(hours=payload.lookback_hours)
        latest_signal_at = self._get_latest_processed_timestamp(strategy.id)
        start_at = cutoff
        if latest_signal_at is not None:
            overlap_seconds = max(int(strategy.max_signal_delay_seconds), 1)
            start_at = max(cutoff, latest_signal_at - timedelta(seconds=overlap_seconds))

        page_size = max(int(payload.activity_limit), 1)
        rows = await self._fetch_activity_pages(
            wallet,
            page_size=page_size,
            start_at=start_at,
        )
        activities = [self.analytics_service._activity_item(row) for row in rows]
        raw_trades = [item for item in activities if item.activity_type == "TRADE" and item.timestamp >= cutoff]
        grouped_trades = self.analytics_service._group_trade_activities(raw_trades)
        grouped_trades = sorted(grouped_trades, key=lambda item: item.timestamp)

        recent_keys = self._list_signal_idempotency_keys(strategy.id, cutoff)
        incremental_trades = [
            trade for trade in grouped_trades if self._build_trade_idempotency_key(strategy.id, trade) not in recent_keys
        ]
        return raw_trades, incremental_trades

    async def _fetch_activity_pages(
        self,
        wallet: str,
        *,
        page_size: int,
        start_at: datetime,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        offset = 0

        while True:
            page_rows = await self.analytics_service.client.get_activity(
                wallet,
                limit=page_size,
                offset=offset,
                start=int(start_at.timestamp()),
            )
            if not page_rows:
                break
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            offset += len(page_rows)

        return rows

    def _build_simulation_signals(
        self,
        *,
        grouped_trades: List[PolymarketActivityItem],
        strategy: PolymarketCopyStrategyRead,
        source_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
        follower_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
        raw_trade_count: int,
    ) -> Tuple[PolymarketCopySimulationSummary, List[PolymarketCopySimulationSignal]]:
        signals: List[PolymarketCopySimulationSignal] = []
        skip_reason_counts: Counter = Counter()
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
            raw_trade_count=raw_trade_count,
            grouped_trade_count=len(grouped_trades),
            simulated_signal_count=len(signals),
            executed_signal_count=len([item for item in signals if item.status == "executed"]),
            skipped_signal_count=len([item for item in signals if item.status == "skipped"]),
            total_source_notional_usdc=round(total_source_notional, 4),
            total_copied_notional_usdc=round(total_copied_notional, 4),
            skip_reason_counts=dict(skip_reason_counts),
        )
        return summary, signals

    def _load_shadow_positions(
        self,
        strategy_id: int,
    ) -> Tuple[Dict[Tuple[str, str, str], Dict[str, Any]], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        db = self.session_factory()
        try:
            rows = (
                db.query(PolymarketCopySourcePosition)
                .filter(PolymarketCopySourcePosition.strategy_id == strategy_id)
                .all()
            )
            source_positions: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
            follower_positions: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
            for row in rows:
                key = (row.condition_id, row.asset, row.outcome)
                source_positions[key] = {
                    "size": float(row.estimated_source_size or 0.0),
                    "notional": float(row.estimated_source_notional_usdc or 0.0),
                    "last_activity_at": row.last_source_activity_at,
                    "last_tx_hash": row.last_source_tx_hash,
                }
                follower_positions[key] = {
                    "size": float(row.estimated_follower_size or 0.0),
                    "notional": float(row.estimated_follower_notional_usdc or 0.0),
                }
            return source_positions, follower_positions
        finally:
            db.close()

    def _persist_shadow_positions(
        self,
        strategy_id: int,
        source_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
        follower_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
    ) -> None:
        db = self.session_factory()
        try:
            existing_rows = {
                (row.condition_id, row.asset, row.outcome): row
                for row in db.query(PolymarketCopySourcePosition)
                .filter(PolymarketCopySourcePosition.strategy_id == strategy_id)
                .all()
            }
            for position_key, source_state in source_positions.items():
                condition_id, asset, outcome = position_key
                follower_state = follower_positions.get(position_key, {"size": 0.0, "notional": 0.0})
                row = existing_rows.get(position_key)
                if row is None:
                    row = PolymarketCopySourcePosition(
                        strategy_id=strategy_id,
                        condition_id=condition_id,
                        asset=asset,
                        outcome=outcome,
                    )
                    db.add(row)
                    existing_rows[position_key] = row
                row.estimated_source_size = float(source_state.get("size") or 0.0)
                row.estimated_source_notional_usdc = float(source_state.get("notional") or 0.0)
                row.estimated_follower_size = float(follower_state.get("size") or 0.0)
                row.estimated_follower_notional_usdc = float(follower_state.get("notional") or 0.0)
                row.estimated_source_avg_price = self._estimate_avg_price(
                    row.estimated_source_notional_usdc,
                    row.estimated_source_size,
                )
                row.last_source_activity_at = source_state.get("last_activity_at")
                row.last_source_tx_hash = source_state.get("last_tx_hash")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _get_latest_processed_timestamp(self, strategy_id: int) -> Optional[datetime]:
        db = self.session_factory()
        try:
            signal_row = (
                db.query(PolymarketCopySignalLog.source_timestamp)
                .filter(PolymarketCopySignalLog.strategy_id == strategy_id)
                .order_by(PolymarketCopySignalLog.source_timestamp.desc(), PolymarketCopySignalLog.id.desc())
                .first()
            )
            shadow_row = (
                db.query(PolymarketCopySourcePosition.last_source_activity_at)
                .filter(PolymarketCopySourcePosition.strategy_id == strategy_id)
                .order_by(PolymarketCopySourcePosition.last_source_activity_at.desc(), PolymarketCopySourcePosition.id.desc())
                .first()
            )
            timestamps = [row[0] for row in (signal_row, shadow_row) if row and row[0] is not None]
            return max(timestamps) if timestamps else None
        finally:
            db.close()

    def _list_signal_idempotency_keys(self, strategy_id: int, start_at: datetime) -> set[str]:
        db = self.session_factory()
        try:
            rows = (
                db.query(PolymarketCopySignalLog.idempotency_key)
                .filter(PolymarketCopySignalLog.strategy_id == strategy_id)
                .filter(PolymarketCopySignalLog.source_timestamp >= start_at)
                .all()
            )
            return {row[0] for row in rows}
        finally:
            db.close()

    @staticmethod
    def _estimate_avg_price(notional: float, size: float) -> Optional[float]:
        if size <= 0:
            return None
        return round(notional / size, 8)

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
        source_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
        follower_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
    ) -> PolymarketCopySimulationSignal:
        position_key = (
            trade.condition_id or trade.title or "unknown",
            trade.asset or "unknown",
            trade.outcome or "unknown",
        )
        source_state = source_positions.setdefault(
            position_key,
            {"size": 0.0, "notional": 0.0, "last_activity_at": None, "last_tx_hash": None},
        )
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
                follower_order_usdc = self._apply_max_limit(trade_usdc * strategy.copy_ratio, strategy.max_order_usdc)
                market_notional_after = float(follower_state["notional"]) + follower_order_usdc
                if follower_order_usdc < strategy.min_copy_order_usdc:
                    status = "skipped"
                    skip_reason = "below_min_copy_order"
                elif self._is_limit_exceeded(market_notional_after, strategy.max_market_exposure_usdc):
                    status = "skipped"
                    skip_reason = "market_exposure_limit"
                elif self._is_limit_exceeded(market_notional_after, strategy.max_position_notional_usdc):
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
        source_state["last_activity_at"] = trade.timestamp
        source_state["last_tx_hash"] = trade.transaction_hash
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
            source_trade_size=round(trade_size, 4),
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

    def _execute_live_signals(
        self,
        *,
        strategy: PolymarketCopyStrategyRead,
        signals: List[PolymarketCopySimulationSignal],
        follower_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        db = self.session_factory()
        try:
            account = self._validate_execution_account(db, strategy.execution_account_id, require_for_live=True)
        finally:
            db.close()

        adapter = create_adapter_for_account(account)
        if adapter is None:
            raise ValueError("Polymarket 执行适配器不可用")

        execution_results: Dict[str, Dict[str, Any]] = {}
        actual_follower_positions = deepcopy(follower_positions)
        halt_submission = False

        for signal in signals:
            idempotency_key = self._build_signal_idempotency_key(strategy.id, signal)
            if signal.status != "executed":
                execution_results[idempotency_key] = {"execution_status": "skipped_simulation"}
                continue
            if halt_submission:
                execution_results[idempotency_key] = {
                    "execution_status": "skipped_after_failure",
                    "execution_error": "同一轮询周期内前序 live 下单失败，后续信号已停止提交",
                }
                continue

            order_request = self._build_live_order_request(signal)
            if order_request is None:
                execution_results[idempotency_key] = {
                    "execution_status": "invalid_order",
                    "execution_error": "缺少有效价格、数量或 token_id，无法提交 live 订单",
                }
                halt_submission = True
                continue

            try:
                receipt = adapter.place_order(**order_request)
                execution_results[idempotency_key] = {
                    "execution_status": "submitted",
                    "order_id": receipt.get("order_id"),
                    "order_status": receipt.get("status"),
                    "order_response": receipt.get("response") or {},
                    "executed_at": datetime.utcnow(),
                }
                self._apply_live_follower_fill(actual_follower_positions, signal)
            except Exception as exc:
                execution_results[idempotency_key] = {
                    "execution_status": "failed",
                    "execution_error": str(exc),
                }
                halt_submission = True

        return execution_results, actual_follower_positions

    @staticmethod
    def _build_live_order_request(signal: PolymarketCopySimulationSignal) -> Optional[Dict[str, Any]]:
        token_id = str(signal.asset or "").strip()
        side = str(signal.side or "").upper()
        if not token_id or side not in {"BUY", "SELL"}:
            return None

        source_size = float(signal.source_trade_size or 0.0)
        source_notional = float(signal.source_trade_usdc or 0.0)
        price = source_notional / source_size if source_size > 0 else 0.0
        if price <= 0:
            return None

        if side == "BUY":
            size = float(signal.follower_order_usdc or 0.0) / price
        else:
            size = max(float(signal.follower_position_before or 0.0) - float(signal.follower_position_after or 0.0), 0.0)

        if size <= 0:
            return None

        return {
            "token_id": token_id,
            "side": side,
            "price": round(price, 8),
            "size": round(size, 8),
        }

    @staticmethod
    def _apply_live_follower_fill(
        follower_positions: Dict[Tuple[str, str, str], Dict[str, Any]],
        signal: PolymarketCopySimulationSignal,
    ) -> None:
        position_key = (
            signal.condition_id or signal.title or "unknown",
            signal.asset or "unknown",
            signal.outcome or "unknown",
        )
        state = follower_positions.setdefault(position_key, {"size": 0.0, "notional": 0.0})
        state["size"] = float(signal.follower_position_after or 0.0)
        if str(signal.side or "").upper() == "BUY":
            state["notional"] = max(0.0, float(state.get("notional") or 0.0) + float(signal.follower_order_usdc or 0.0))
        else:
            state["notional"] = max(0.0, float(state.get("notional") or 0.0) - float(signal.follower_order_usdc or 0.0))

    def _cancel_pending_live_orders(self, strategy_id: int, account: Account) -> int:
        adapter = create_adapter_for_account(account)
        if adapter is None:
            raise ValueError("Polymarket 执行适配器不可用")

        db = self.session_factory()
        try:
            rows = (
                db.query(PolymarketCopySignalLog)
                .filter(PolymarketCopySignalLog.strategy_id == strategy_id)
                .filter(PolymarketCopySignalLog.live_order_id.isnot(None))
                .filter(PolymarketCopySignalLog.live_execution_status == "submitted")
                .filter(PolymarketCopySignalLog.live_canceled_at.is_(None))
                .all()
            )
            canceled = 0
            for row in rows:
                try:
                    receipt = adapter.cancel_order(str(row.live_order_id))
                    row.live_execution_status = "canceled"
                    row.live_order_status = receipt.get("status")
                    row.live_canceled_at = datetime.utcnow()
                    row.live_cancel_response = receipt.get("response") or {}
                    row.live_cancel_error = None
                    canceled += 1
                except Exception as exc:
                    row.live_cancel_error = str(exc)
            db.commit()
            return canceled
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _to_preflight_check(name: str, payload: Dict[str, Any]) -> PolymarketLivePreflightCheck:
        return PolymarketLivePreflightCheck(
            name=name,
            endpoint=str(payload.get("endpoint") or ""),
            ok=bool(payload.get("ok")),
            status_code=int(payload.get("status_code") or 0),
            code=payload.get("code"),
            message=payload.get("message"),
            hint=payload.get("hint"),
        )

    def _extract_preflight_checks(self, connectivity: Dict[str, Any]) -> List[PolymarketLivePreflightCheck]:
        checks_payload = connectivity.get("checks") or []
        if checks_payload:
            return [
                self._to_preflight_check(str(item.get("scope") or f"check_{index}"), item)
                for index, item in enumerate(checks_payload, start=1)
            ]

        fallback_checks = []
        for name, payload in (("spot_account", connectivity.get("spot_account")), ("futures_account", connectivity.get("futures_account"))):
            if payload:
                fallback_checks.append(self._to_preflight_check(name, payload))
        return fallback_checks

    @staticmethod
    def _to_strategy_read(row: PolymarketCopyStrategy, execution_account: Optional[Account] = None) -> PolymarketCopyStrategyRead:
        return PolymarketCopyStrategyRead.model_validate(
            {
                **row.to_dict(),
                "execution_account_name": execution_account.name if execution_account else None,
                "execution_account_exchange": execution_account.exchange if execution_account else None,
                "allowed_markets": row.allowed_markets or [],
                "blocked_markets": row.blocked_markets or [],
            }
        )


polymarket_copy_service = PolymarketCopyService()