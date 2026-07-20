"""市场洞察告警组合阈值预设。"""
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class MarketAlertPreset:
    key: str
    label: str
    description: str
    radar_params: Dict[str, Any]
    min_score: float
    cooldown_minutes: int


MARKET_ALERT_PRESETS = {
    "high_frequency": MarketAlertPreset(
        key="high_frequency",
        label="高频灵敏",
        description="更早捕捉短周期放量，信号更多，适合高频观察和快速确认。",
        radar_params={
            "limit": 20,
            "volume_ratio_min": 1.2,
            "resistance_hours": 24,
            "exclude_recent_hours": 1,
            "volatility_days": 3,
            "noise_multiplier": 0.2,
            "min_breakout_percent": 0.04,
            "max_24h_change": 20,
        },
        min_score=45.0,
        cooldown_minutes=15,
    ),
    "balanced": MarketAlertPreset(
        key="balanced",
        label="均衡",
        description="兼顾触发速度和信号质量，适合作为日常默认预警。",
        radar_params={
            "limit": 15,
            "volume_ratio_min": 1.3,
            "resistance_hours": 48,
            "exclude_recent_hours": 3,
            "volatility_days": 7,
            "noise_multiplier": 0.35,
            "min_breakout_percent": 0.08,
            "max_24h_change": 15,
        },
        min_score=60.0,
        cooldown_minutes=60,
    ),
    "strict": MarketAlertPreset(
        key="strict",
        label="严格确认",
        description="要求更强量能和更深突破，信号较少，适合降低噪声。",
        radar_params={
            "limit": 10,
            "volume_ratio_min": 1.8,
            "resistance_hours": 72,
            "exclude_recent_hours": 4,
            "volatility_days": 10,
            "noise_multiplier": 0.55,
            "min_breakout_percent": 0.15,
            "max_24h_change": 12,
        },
        min_score=75.0,
        cooldown_minutes=180,
    ),
}


def get_market_alert_preset(key: str) -> MarketAlertPreset:
    return MARKET_ALERT_PRESETS.get(key, MARKET_ALERT_PRESETS["balanced"])
