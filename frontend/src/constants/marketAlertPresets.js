export const MARKET_ALERT_PRESETS = {
  high_frequency: {
    key: 'high_frequency',
    label: '高频灵敏',
    description: '更早捕捉短周期放量，信号更多，适合高频观察和快速确认。',
    minScore: 45,
    cooldownMinutes: 15,
    radarSettings: {
      volume_ratio_min: 1.2,
      resistance_hours: 24,
      exclude_recent_hours: 1,
      volatility_days: 3,
      noise_multiplier: 0.2,
      min_breakout_percent: 0.04,
      max_24h_change: 20
    }
  },
  balanced: {
    key: 'balanced',
    label: '均衡',
    description: '兼顾触发速度和信号质量，适合作为日常默认预警。',
    minScore: 60,
    cooldownMinutes: 60,
    radarSettings: {
      volume_ratio_min: 1.3,
      resistance_hours: 48,
      exclude_recent_hours: 3,
      volatility_days: 7,
      noise_multiplier: 0.35,
      min_breakout_percent: 0.08,
      max_24h_change: 15
    }
  },
  strict: {
    key: 'strict',
    label: '严格确认',
    description: '要求更强量能和更深突破，信号较少，适合降低噪声。',
    minScore: 75,
    cooldownMinutes: 180,
    radarSettings: {
      volume_ratio_min: 1.8,
      resistance_hours: 72,
      exclude_recent_hours: 4,
      volatility_days: 10,
      noise_multiplier: 0.55,
      min_breakout_percent: 0.15,
      max_24h_change: 12
    }
  }
}

export const MARKET_ALERT_PRESET_OPTIONS = Object.values(MARKET_ALERT_PRESETS)
