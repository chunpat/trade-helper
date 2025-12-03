from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models.risk_control import Account, RiskConfig, Position, RiskAlert, RiskLevelEnum, OrderLog

class RiskControlService:
    def __init__(self, db: Session):
        self.db = db

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
        pnl_ratio = (position.current_price - position.entry_price) / position.entry_price
        position_value = position.size * position.current_price

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
        position.unrealized_pnl = (current_price - position.entry_price) * position.size

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
                position_value = position.size * position.current_price
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
