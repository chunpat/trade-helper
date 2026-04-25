from types import SimpleNamespace

from app.models.risk_control import RiskLevelEnum
from app.services.position_sync import PositionSyncService
from app.services.risk_control_service import RiskControlService


def test_calculate_unrealized_pnl_amount_for_long_position():
    amount = RiskControlService.calculate_unrealized_pnl_amount(
        entry_price=100.0,
        current_price=110.0,
        size=2.0,
        position_side='LONG',
    )

    assert amount == 20.0


def test_calculate_unrealized_pnl_amount_for_short_position():
    loss_amount = RiskControlService.calculate_unrealized_pnl_amount(
        entry_price=100.0,
        current_price=110.0,
        size=2.0,
        position_side='SHORT',
    )
    profit_amount = RiskControlService.calculate_unrealized_pnl_amount(
        entry_price=100.0,
        current_price=90.0,
        size=2.0,
        position_side='SHORT',
    )

    assert loss_amount == -20.0
    assert profit_amount == 20.0


def test_calculate_risk_level_respects_short_position_direction():
    service = RiskControlService(db=None)
    risk_config = SimpleNamespace(risk_ratio_threshold=0.05, max_position_value=1000.0)
    position = SimpleNamespace(
        current_price=110.0,
        entry_price=100.0,
        size=2.0,
        position_side='SHORT',
    )

    level = service.calculate_risk_level(position, risk_config)

    assert level == RiskLevelEnum.CRITICAL


def test_position_sync_normalizes_binance_both_side_using_position_amount():
    assert PositionSyncService.normalize_position_side('BOTH', 3.0) == 'LONG'
    assert PositionSyncService.normalize_position_side('BOTH', -3.0) == 'SHORT'
    assert PositionSyncService.normalize_position_side('BOTH', 0.0) == 'NET'