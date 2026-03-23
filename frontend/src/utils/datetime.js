export const DISPLAY_TIMEZONE_STORAGE_KEY = 'display.timezone'

export const DISPLAY_TIMEZONE_OPTIONS = [
  { label: '跟随系统', value: 'system' },
  { label: '北京时间 (UTC+8)', value: 'Asia/Shanghai' },
  { label: 'UTC', value: 'UTC' },
  { label: '伦敦时间', value: 'Europe/London' },
  { label: '纽约时间', value: 'America/New_York' }
]

const ISO_WITHOUT_TIMEZONE_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/

export function getStoredDisplayTimezone() {
  if (typeof window === 'undefined') {
    return 'system'
  }
  return window.localStorage.getItem(DISPLAY_TIMEZONE_STORAGE_KEY) || 'system'
}

export function setStoredDisplayTimezone(timezone) {
  if (typeof window === 'undefined') {
    return
  }

  const normalizedTimezone = timezone || 'system'
  window.localStorage.setItem(DISPLAY_TIMEZONE_STORAGE_KEY, normalizedTimezone)
}

export function resolveDisplayTimezone(timezone = getStoredDisplayTimezone()) {
  if (!timezone || timezone === 'system') {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  }
  return timezone
}

export function getDisplayTimezoneLabel(timezone = getStoredDisplayTimezone()) {
  const normalizedTimezone = timezone || 'system'
  const matchedOption = DISPLAY_TIMEZONE_OPTIONS.find(option => option.value === normalizedTimezone)
  if (matchedOption) {
    return matchedOption.label
  }
  return normalizedTimezone
}

export function getDisplayTimezoneOffsetLabel(timezone = getStoredDisplayTimezone()) {
  const resolvedTimezone = resolveDisplayTimezone(timezone)

  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: resolvedTimezone,
      timeZoneName: 'shortOffset'
    }).formatToParts(new Date())
    const timeZoneNamePart = parts.find(part => part.type === 'timeZoneName')
    if (timeZoneNamePart?.value) {
      return timeZoneNamePart.value.replace('GMT', 'UTC')
    }
  } catch (_error) {
    // Ignore and use fallback below.
  }

  const knownOffsets = {
    'Asia/Shanghai': 'UTC+8',
    UTC: 'UTC+0',
    'Europe/London': 'UTC+0/UTC+1',
    'America/New_York': 'UTC-5/UTC-4'
  }
  return knownOffsets[resolvedTimezone] || resolvedTimezone
}

export function parseBackendDateTime(rawValue) {
  if (!rawValue) {
    return null
  }
  if (rawValue instanceof Date) {
    return Number.isNaN(rawValue.getTime()) ? null : rawValue
  }
  if (typeof rawValue === 'number') {
    const date = new Date(rawValue)
    return Number.isNaN(date.getTime()) ? null : date
  }

  const stringValue = String(rawValue).trim()
  if (!stringValue) {
    return null
  }

  const normalizedValue = ISO_WITHOUT_TIMEZONE_PATTERN.test(stringValue)
    ? `${stringValue}Z`
    : stringValue

  const date = new Date(normalizedValue)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(rawValue, timezone = getStoredDisplayTimezone(), overrides = {}) {
  const date = parseBackendDateTime(rawValue)
  if (!date) {
    return rawValue || '-'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: overrides.second || undefined,
    hour12: false,
    timeZone: resolveDisplayTimezone(timezone),
    ...overrides
  }).format(date)
}

export function formatShortDate(rawValue, timezone = getStoredDisplayTimezone()) {
  const date = parseBackendDateTime(rawValue)
  if (!date) {
    return rawValue || '--'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    timeZone: resolveDisplayTimezone(timezone)
  }).format(date)
}

export function formatCurrentDateTime(timezone = getStoredDisplayTimezone()) {
  return formatDateTime(new Date(), timezone, { second: '2-digit' })
}