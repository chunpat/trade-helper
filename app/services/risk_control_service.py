from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models.risk_control import Account, RiskConfig, Position, RiskAlert, RiskLevelEnum, OrderLog

class RiskControlService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def normalize_position_side(position_side: Optional[str]) -> str:
        return (position_side or "LONG").strip().upper()

    @classmethod
    def calculate_unrealized_pnl_amount(
        cls,
        entry_price: Optional[float],
        current_price: Optional[float],
        size: Optional[float],
        position_side: Optional[str] = None,
    ) -> float:
        if not entry_price or current_price is None or size is None:
            return 0.0

        quantity = abs(size)
        side = cls.normalize_position_side(position_side)
        if side == 'SHORT':
            return (entry_price - current_price) * quantity
        return (current_price - entry_price) * quantity

    @classmethod
    def calculate_unrealized_pnl_ratio(
        cls,
        entry_price: Optional[float],
        current_price: Optional[float],
        position_side: Optional[str] = None,
    ) -> float:
        if not entry_price or current_price is None:
            return 0.0

        side = cls.normalize_position_side(position_side)
        if side == 'SHORT':
            return (entry_price - current_price) / entry_price
        return (current_price - entry_price) / entry_price

    def check_position_risk(self, account_id: int, symbol: str, size: float, leverage: float) -> Dict:
        """检查持仓风险"""
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return {"passed": False, "reason": "Account not found"}

        risk_config = self.db.query(RiskConfig).filter(
            RiskConfig.account_id == account_id,
            RiskConfig.is_active == True
        ).first()

        if not risk_config:
            return {"passed": False, "reason": "Risk configuration not found"}

        # 检查杠杆倍数
        if leverage > risk_config.max_leverage:
            return {
                "passed": False,
                "reason": f"Leverage {leverage}x exceeds maximum allowed {risk_config.max_leverage}x"
            }

        # 计算持仓价值
        position_value = size * leverage
        if position_value > risk_config.max_position_value:
            return {
                "passed": False,
                "reason": f"Position value {position_value} exceeds maximum allowed {risk_config.max_position_value}"
            }

        return {"passed": True}

    def check_order_risk(self, account_id: int, symbol: str, size: float, price: float) -> Dict:
        """检查订单风险"""
        risk_config = self.db.query(RiskConfig).filter(
            RiskConfig.account_id == account_id,
            RiskConfig.is_active == True
        ).first()

        if not risk_config:
            return {"passed": False, "reason": "Risk configuration not found"}

        # 检查订单大小
        if size > risk_config.max_single_order:
            return {
                "passed": False,
                "reason": f"Order size {size} exceeds maximum allowed {risk_config.max_single_order}"
            }

        # 检查订单频率
        recent_orders = self.db.query(OrderLog).filter(
            OrderLog.account_id == account_id,
            OrderLog.created_at >= datetime.utcnow() - timedelta(minutes=1)
        ).count()

        if recent_orders >= risk_config.order_frequency_limit:
            return {
                "passed": False,
                "reason": f"Order frequency exceeds limit of {risk_config.order_frequency_limit} per minute"
            }

        return {"passed": True}

    def calculate_risk_level(self, position: Position, risk_config: RiskConfig) -> RiskLevelEnum:
        """计算风险等级"""
        if not position.current_price or not position.entry_price:
            return RiskLevelEnum.MEDIUM

        # 计算未实现盈亏率
        pnl_ratio = self.calculate_unrealized_pnl_ratio(
            entry_price=position.entry_price,
            current_price=position.current_price,
            position_side=getattr(position, 'position_side', None),
        )
        position_value = abs(position.size) * position.current_price

        if pnl_ratio <= -risk_config.risk_ratio_threshold:
            return RiskLevelEnum.CRITICAL
        elif position_value >= risk_config.max_position_value * 0.9:
            return RiskLevelEnum.HIGH
        elif position_value >= risk_config.max_position_value * 0.7:
            return RiskLevelEnum.MEDIUM
        else:
            return RiskLevelEnum.LOW

    def create_risk_alert(self, account_id: int, alert_type: str, risk_level: RiskLevelEnum, 
                         message: str, details: Optional[Dict] = None) -> RiskAlert:
        """创建风险预警"""
        alert = RiskAlert(
            account_id=account_id,
            alert_type=alert_type,
            risk_level=risk_level,
            message=message,
            details=details
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def log_order(self, account_id: int, order_data: Dict, 
                 risk_check_result: Dict, exchange_response: Optional[Dict] = None) -> OrderLog:
        """记录订单信息"""
        order_log = OrderLog(
            account_id=account_id,
            order_id=order_data.get("order_id"),
            symbol=order_data.get("symbol"),
            order_type=order_data.get("type"),
            side=order_data.get("side"),
            price=order_data.get("price"),
            size=order_data.get("size"),
            status=order_data.get("status", "CREATED"),
            risk_check_passed=risk_check_result.get("passed", False),
            risk_check_details=risk_check_result,
            exchange_response=exchange_response
        )
        self.db.add(order_log)
        self.db.commit()
        self.db.refresh(order_log)
        return order_log

    def update_position(self, position_id: int, current_price: float) -> Position:
        """更新持仓信息"""
        position = self.db.query(Position).filter(Position.id == position_id).first()
        if not position:
            return None

        position.current_price = current_price
        position.unrealized_pnl = self.calculate_unrealized_pnl_amount(
            entry_price=position.entry_price,
            current_price=current_price,
            size=position.size,
            position_side=getattr(position, 'position_side', None),
        )

        # 更新风险等级
        risk_config = self.db.query(RiskConfig).filter(
            RiskConfig.account_id == position.account_id,
            RiskConfig.is_active == True
        ).first()
        
        if risk_config:
            position.risk_level = self.calculate_risk_level(position, risk_config)

        self.db.commit()
        self.db.refresh(position)
        return position

    def get_account_risk_summary(self, account_id: int) -> Dict:
        """获取账户风险概览"""
        positions = self.db.query(Position).filter(
            Position.account_id == account_id,
            Position.is_active == True
        ).all()

        total_position_value = 0
        total_unrealized_pnl = 0
        risk_levels = []

        for position in positions:
            if position.current_price:
                position_value = abs(position.size) * position.current_price
                total_position_value += position_value
                total_unrealized_pnl += position.unrealized_pnl or 0
                risk_levels.append(position.risk_level)

        highest_risk = max(risk_levels, default=RiskLevelEnum.LOW)

        return {
            "total_position_value": total_position_value,
            "total_unrealized_pnl": total_unrealized_pnl,
            "highest_risk_level": highest_risk.value,
            "active_positions_count": len(positions),
            "risk_level_distribution": {level: risk_levels.count(level) for level in RiskLevelEnum}
        }

    def analyze_positions(self, account_id: Optional[int] = None, symbol: Optional[str] = None) -> Dict:
        """分析当前持仓并给出问题建议"""
        query = self.db.query(Position).filter(Position.is_active == True)
        if account_id is not None:
            query = query.filter(Position.account_id == account_id)
        if symbol:
            normalized = (symbol or "").strip().upper()
            if normalized:
                query = query.filter(Position.symbol == normalized)

        positions = query.all()
        if not positions:
            return {
                "account_id": account_id,
                "account_name": None,
                "overall_risk_level": "low",
                "total_position_value": 0.0,
                "total_margin": 0.0,
                "total_unrealized_pnl": 0.0,
                "account_equity": None,
                "position_count": 0,
                "issues": [],
            }

        account_ids = list({p.account_id for p in positions})
        accounts_map = {
            a.id: a for a in self.db.query(Account).filter(Account.id.in_(account_ids)).all()
        }
        configs_map = {
            c.account_id: c
            for c in self.db.query(RiskConfig).filter(
                RiskConfig.account_id.in_(account_ids),
                RiskConfig.is_active == True,
            ).all()
        }

        issues = []
        total_position_value = 0.0
        total_margin = 0.0
        total_unrealized_pnl = 0.0
        direction_counts = {"LONG": 0, "SHORT": 0}
        now = datetime.utcnow()
        overall_severity_score = 0

        for pos in positions:
            size = abs(float(pos.size or 0))
            current_price = float(pos.current_price or 0)
            leverage = float(pos.leverage or 1)
            position_value = size * current_price if current_price else 0
            margin = position_value / leverage if leverage > 0 else position_value
            total_position_value += position_value
            total_margin += margin
            total_unrealized_pnl += float(pos.unrealized_pnl or 0)

            side = self.normalize_position_side(getattr(pos, 'position_side', None))
            if side in direction_counts:
                direction_counts[side] += 1

            account = accounts_map.get(pos.account_id)
            config = configs_map.get(pos.account_id)
            account_equity = float(account.total_equity or 0) if account else 0

            # 1. 高杠杆检查
            max_leverage = float(config.max_leverage) if config else 10.0
            if leverage > max_leverage:
                issues.append({
                    "severity": "high",
                    "issue_type": "high_leverage",
                    "title": f"{pos.symbol} 杠杆过高",
                    "description": f"{pos.symbol} 当前杠杆 {leverage}x，超过风控上限 {max_leverage}x",
                    "involved_symbols": [pos.symbol],
                    "suggestion": f"建议降低杠杆至 {max_leverage}x 以下，或减少仓位规模",
                })
                overall_severity_score = max(overall_severity_score, 3)
            elif leverage > 10:
                issues.append({
                    "severity": "medium",
                    "issue_type": "high_leverage",
                    "title": f"{pos.symbol} 杠杆偏高",
                    "description": f"{pos.symbol} 当前杠杆 {leverage}x，超过 10x 建议值",
                    "involved_symbols": [pos.symbol],
                    "suggestion": "高杠杆会放大亏损风险，建议控制在 10x 以内",
                })
                overall_severity_score = max(overall_severity_score, 2)

            # 2. 浮亏检查
            pnl_ratio = self.calculate_unrealized_pnl_ratio(
                entry_price=float(pos.entry_price or 0),
                current_price=current_price,
                position_side=getattr(pos, 'position_side', None),
            )
            if pnl_ratio < -0.2:
                issues.append({
                    "severity": "high",
                    "issue_type": "large_unrealized_loss",
                    "title": f"{pos.symbol} 浮亏过大",
                    "description": f"{pos.symbol} 当前浮亏率 {round(pnl_ratio * 100, 1)}%，已超过 20%",
                    "involved_symbols": [pos.symbol],
                    "suggestion": "建议评估是否止损平仓，避免亏损进一步扩大",
                })
                overall_severity_score = max(overall_severity_score, 3)
            elif pnl_ratio < -0.1:
                issues.append({
                    "severity": "medium",
                    "issue_type": "large_unrealized_loss",
                    "title": f"{pos.symbol} 浮亏偏高",
                    "description": f"{pos.symbol} 当前浮亏率 {round(pnl_ratio * 100, 1)}%，超过 10%",
                    "involved_symbols": [pos.symbol],
                    "suggestion": "密切关注行情变化，考虑设置止损",
                })
                overall_severity_score = max(overall_severity_score, 2)

            # 3. 仓位占权益比检查
            if account_equity > 0 and margin > 0:
                margin_ratio = margin / account_equity
                if margin_ratio > 0.5:
                    issues.append({
                        "severity": "high",
                        "issue_type": "large_position_size",
                        "title": f"{pos.symbol} 仓位占比过大",
                        "description": f"{pos.symbol} 保证金占账户权益 {round(margin_ratio * 100, 1)}%，超过 50%",
                        "involved_symbols": [pos.symbol],
                        "suggestion": "单一仓位占比过高，建议分散风险或减仓",
                    })
                    overall_severity_score = max(overall_severity_score, 3)
                elif margin_ratio > 0.3:
                    issues.append({
                        "severity": "medium",
                        "issue_type": "large_position_size",
                        "title": f"{pos.symbol} 仓位占比偏高",
                        "description": f"{pos.symbol} 保证金占账户权益 {round(margin_ratio * 100, 1)}%，超过 30%",
                        "involved_symbols": [pos.symbol],
                        "suggestion": "关注仓位集中度，避免过度集中在单一币种",
                    })
                    overall_severity_score = max(overall_severity_score, 2)

            # 4. 强平风险检查
            liquidation_price = float(pos.liquidation_price or 0)
            if liquidation_price > 0 and current_price > 0:
                if side == "LONG":
                    liq_distance = (current_price - liquidation_price) / current_price
                else:
                    liq_distance = (liquidation_price - current_price) / current_price
                if liq_distance < 0.05:
                    issues.append({
                        "severity": "critical",
                        "issue_type": "liquidation_risk",
                        "title": f"{pos.symbol} 强平风险",
                        "description": f"{pos.symbol} 当前价距强平价仅 {round(liq_distance * 100, 1)}%，极端行情下可能触发强平",
                        "involved_symbols": [pos.symbol],
                        "suggestion": "立即追加保证金或降低仓位，将强平距离拉到安全范围（>10%）",
                    })
                    overall_severity_score = max(overall_severity_score, 4)
                elif liq_distance < 0.1:
                    issues.append({
                        "severity": "medium",
                        "issue_type": "liquidation_risk",
                        "title": f"{pos.symbol} 强平距离偏近",
                        "description": f"{pos.symbol} 当前价距强平价 {round(liq_distance * 100, 1)}%，安全余量有限",
                        "involved_symbols": [pos.symbol],
                        "suggestion": "建议追加保证金或设置止损，防止突发行情触发强平",
                    })
                    overall_severity_score = max(overall_severity_score, 2)

        # 5. 方向集中度检查（跨币种）
        for side, count in direction_counts.items():
            if count >= 3:
                direction_label = "做多" if side == "LONG" else "做空"
                issues.append({
                    "severity": "medium",
                    "issue_type": "concentration_risk",
                    "title": f"同一方向持仓集中 ({direction_label} × {count})",
                    "description": f"当前有 {count} 个{direction_label}持仓，方向过于集中，系统性风险较高",
                    "involved_symbols": [
                        p.symbol for p in positions
                        if self.normalize_position_side(getattr(p, 'position_side', None)) == side
                    ],
                    "suggestion": "建议分散方向，适当配置反向头寸对冲系统性风险",
                })
                overall_severity_score = max(overall_severity_score, 2)

        # 6. 整体风险敞口检查
        if account_equity > 0 and total_position_value > 0:
            exposure_ratio = total_position_value / account_equity
            if exposure_ratio > 5:
                issues.append({
                    "severity": "high",
                    "issue_type": "high_risk_exposure",
                    "title": "整体风险敞口过高",
                    "description": f"总持仓价值/账户权益 = {round(exposure_ratio, 1)}x，远超安全范围",
                    "involved_symbols": [p.symbol for p in positions],
                    "suggestion": "大幅降低总仓位，将敞口控制在 2-3x 以内",
                })
                overall_severity_score = max(overall_severity_score, 3)
            elif exposure_ratio > 3:
                issues.append({
                    "severity": "medium",
                    "issue_type": "high_risk_exposure",
                    "title": "整体风险敞口偏高",
                    "description": f"总持仓价值/账户权益 = {round(exposure_ratio, 1)}x，超过 3x 建议值",
                    "involved_symbols": [p.symbol for p in positions],
                    "suggestion": "适当降低仓位或追加保证金，建议控制在 3x 以内",
                })
                overall_severity_score = max(overall_severity_score, 2)

        # Sort issues by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        issues.sort(key=lambda i: severity_order.get(i["severity"], 99))

        overall_risk_level = (
            "critical" if overall_severity_score >= 4
            else "high" if overall_severity_score >= 3
            else "medium" if overall_severity_score >= 2
            else "low"
        )

        if account_id is not None:
            account = accounts_map.get(account_id)
            account_name = account.name if account else None
            account_equity_val = float(account.total_equity or 0) if account else None
        else:
            account_name = None
            account_equity_val = sum(
                float(a.total_equity or 0) for a in accounts_map.values()
            ) if accounts_map else None

        return {
            "account_id": account_id,
            "account_name": account_name,
            "overall_risk_level": overall_risk_level,
            "total_position_value": round(total_position_value, 2),
            "total_margin": round(total_margin, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "account_equity": round(account_equity_val, 2) if account_equity_val else None,
            "position_count": len(positions),
            "issues": issues,
        }
