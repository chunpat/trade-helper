export function formatPolymarketMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  const numeric = Number(value)
  if (Math.abs(numeric) >= 1000000) {
    return `$${(numeric / 1000000).toFixed(2)}M`
  }
  if (Math.abs(numeric) >= 1000) {
    return `$${(numeric / 1000).toFixed(1)}K`
  }
  return `$${numeric.toFixed(2)}`
}

export function formatPolymarketPercent(value, digits = 1, ratioMode = false) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  const numeric = Number(value)
  const displayValue = ratioMode && Math.abs(numeric) <= 1 ? numeric * 100 : numeric
  return `${displayValue.toFixed(digits)}%`
}

export function formatPolymarketWinRate(value) {
  return formatPolymarketPercent(value, 1, true)
}

export function formatPolymarketNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  return Number(value).toFixed(digits)
}

export function formatPolymarketSeconds(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  const numeric = Number(value)
  if (numeric < 60) {
    return `${numeric.toFixed(0)} 秒`
  }
  if (numeric < 3600) {
    return `${(numeric / 60).toFixed(1)} 分钟`
  }
  return `${(numeric / 3600).toFixed(1)} 小时`
}

export function formatPolymarketVerdict(verdict) {
  return {
    candidate: '优先候选',
    watchlist: '观察名单',
    cautious: '谨慎跟随',
    avoid: '不建议跟随'
  }[verdict] || verdict || '-'
}

export function formatPolymarketTraderStyle(style) {
  return {
    discretionary: '主观交易',
    high_frequency: '高频风格',
    active_systematic: '活跃量化',
    specialist: '单题材聚焦',
    broad_portfolio: '广覆盖组合'
  }[style] || style || '未知'
}

export function getPolymarketStyleTagType(style) {
  return {
    discretionary: 'success',
    high_frequency: 'warning',
    active_systematic: 'warning',
    specialist: 'primary',
    broad_portfolio: 'info'
  }[style] || 'info'
}

export function getPolymarketFollowabilityColor(score) {
  if (Number(score) >= 75) {
    return '#16a34a'
  }
  if (Number(score) >= 55) {
    return '#f59e0b'
  }
  return '#ef4444'
}

export function shortenPolymarketWallet(wallet) {
  if (!wallet) {
    return '-'
  }
  return `${wallet.slice(0, 6)}...${wallet.slice(-4)}`
}

export function getPolymarketAvatarFallback(row) {
  const source = row?.name || row?.pseudonym || row?.wallet_address || 'PM'
  return source.slice(0, 2).toUpperCase()
}