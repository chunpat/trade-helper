import axios from 'axios'

const ACCESS_TOKEN_KEY = 'token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const TOKEN_EXPIRES_AT_KEY = 'token_expires_at'
const AUTH_STORAGE_EVENT = 'auth-storage-changed'
const REFRESH_THRESHOLD_MS = 90 * 1000


function notifyAuthChanged(detail) {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_STORAGE_EVENT, { detail }))
  }
}


export function getStoredAuthState() {
  const tokenExpiresAt = Number(localStorage.getItem(TOKEN_EXPIRES_AT_KEY) || 0)
  return {
    token: localStorage.getItem(ACCESS_TOKEN_KEY) || null,
    refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY) || null,
    tokenExpiresAt: Number.isFinite(tokenExpiresAt) && tokenExpiresAt > 0 ? tokenExpiresAt : null
  }
}


export function saveAuthTokens(authPayload) {
  const tokenExpiresAt = Date.now() + (authPayload.expires_in * 1000)
  localStorage.setItem(ACCESS_TOKEN_KEY, authPayload.access_token)
  localStorage.setItem(REFRESH_TOKEN_KEY, authPayload.refresh_token)
  localStorage.setItem(TOKEN_EXPIRES_AT_KEY, String(tokenExpiresAt))

  const authState = {
    token: authPayload.access_token,
    refreshToken: authPayload.refresh_token,
    tokenExpiresAt
  }
  notifyAuthChanged(authState)
  return authState
}


export function clearAuthStorage() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(TOKEN_EXPIRES_AT_KEY)
  notifyAuthChanged({ token: null, refreshToken: null, tokenExpiresAt: null })
}


export function getAuthStorageEventName() {
  return AUTH_STORAGE_EVENT
}


function shouldSkipRefresh(config) {
  const requestUrl = config?.url || ''
  return Boolean(
    config?.skipAuthRefresh ||
    requestUrl.includes('/auth/token') ||
    requestUrl.includes('/auth/register') ||
    requestUrl.includes('/auth/refresh')
  )
}


function shouldRefreshBeforeRequest() {
  const { token, refreshToken, tokenExpiresAt } = getStoredAuthState()
  if (!refreshToken) {
    return false
  }
  if (!token || !tokenExpiresAt) {
    return true
  }
  return tokenExpiresAt - Date.now() <= REFRESH_THRESHOLD_MS
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8029/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

let refreshPromise = null


async function performTokenRefresh() {
  const { refreshToken } = getStoredAuthState()
  if (!refreshToken) {
    throw new Error('Missing refresh token')
  }

  const data = await api.post(
    '/auth/refresh',
    { refresh_token: refreshToken },
    { skipAuthRefresh: true, skipAuthHeader: true }
  )
  saveAuthTokens(data)
  return data
}


export async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = performTokenRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

// Request interceptor
api.interceptors.request.use(
  async config => {
    if (!shouldSkipRefresh(config) && shouldRefreshBeforeRequest()) {
      try {
        await refreshAccessToken()
      } catch (_) {
        clearAuthStorage()
      }
    }

    const token = getStoredAuthState().token
    if (token && !config.skipAuthHeader) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  response => response.data,
  async error => {
    const originalRequest = error.config || {}
    if (error.response?.status === 401 && !shouldSkipRefresh(originalRequest) && !originalRequest._retry) {
      originalRequest._retry = true
      try {
        await refreshAccessToken()
        const token = getStoredAuthState().token
        if (token) {
          originalRequest.headers = originalRequest.headers || {}
          originalRequest.headers['Authorization'] = `Bearer ${token}`
        }
        return api(originalRequest)
      } catch (refreshError) {
        clearAuthStorage()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        return Promise.reject(refreshError)
      }
    }

    if (error.response?.status === 401) {
      clearAuthStorage()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export const riskControl = {
  // Account related
  getAccounts() {
    return api.get('/risk-control/accounts/')
  },
  createAccount(data) {
    return api.post('/risk-control/accounts/', data)
  },
  updateAccount(accountId, data) {
    return api.put(`/risk-control/accounts/${accountId}`, data)
  },
  deleteAccount(accountId) {
    return api.delete(`/risk-control/accounts/${accountId}`)
  },
  testAccountConnectivity(accountId) {
    return api.get(`/risk-control/accounts/${accountId}/connectivity`)
  },
  getRiskConfig(accountId) {
    return api.get(`/risk-control/accounts/${accountId}/risk-config`)
  },
  updateRiskConfig(accountId, data) {
    return api.put(`/risk-control/accounts/${accountId}/risk-config`, data)
  },

  // Position related
  getPositions(params) {
    return api.get('/risk-control/positions/', { params })
  },
  checkPositionRisk(params) {
    return api.post('/risk-control/check-position-risk', params)
  },
  createPosition(data) {
    return api.post('/risk-control/positions/', data)
  },
  updatePosition(positionId, data) {
    return api.patch(`/risk-control/positions/${positionId}`, data)
  },

  // Risk alerts
  getRiskAlerts(params) {
    return api.get('/risk-control/alerts/', { params })
  },
  createRiskAlert(data) {
    return api.post('/risk-control/alerts/', data)
  },
  resolveAlert(alertId, notes) {
    return api.put(`/risk-control/alerts/${alertId}/resolve`, { is_resolved: true, resolution_notes: notes })
  },

  // Dashboard data
  getAccountRiskSummary(accountId) {
    return api.get(`/risk-control/accounts/${accountId}/risk-summary`)
  },

  // Sync endpoints
  syncPositions() {
    return api.post('/risk-control/positions/sync')
  },
  syncAccountPositions(accountId) {
    return api.post(`/risk-control/accounts/${accountId}/positions/sync`)
  },
  
  // History
  getTransactionHistory(params) {
    return api.get('/risk-control/history/transactions', { params })
  },
  getTransactionReviewSummary(params) {
    return api.get('/risk-control/history/transactions/summary', { params })
  },
  getTransactionReviewTimeline(params) {
    return api.get('/risk-control/history/transactions/timeline', { params })
  },
  getCompletedTrades(params) {
    return api.get('/risk-control/history/completed-trades', { params })
  },
  getOpenTrades(params) {
    return api.get('/risk-control/history/open-trades', { params })
  },
  getCompletedTradeSummary(params) {
    return api.get('/risk-control/history/completed-trades/summary', { params })
  },
  getCompletedTradeTimeline(params) {
    return api.get('/risk-control/history/completed-trades/timeline', { params })
  },
  getDailyTradeReview(params) {
    return api.get('/risk-control/history/daily-reviews', { params })
  },
  saveDailyTradeReview(data) {
    return api.put('/risk-control/history/daily-reviews', data)
  },
  listRecentDailyTradeReviews(params) {
    return api.get('/risk-control/history/daily-reviews/recent', { params })
  },
  startAccountHistorySync(accountId, days = 90) {
    return api.post(`/risk-control/accounts/${accountId}/sync-history/start`, null, { params: { days } })
  },
  getAccountHistorySyncStatus(accountId) {
    return api.get(`/risk-control/accounts/${accountId}/sync-history/status`)
  },
  syncAccountHistory(accountId, days = 90) {
    return api.post(`/risk-control/accounts/${accountId}/sync-history`, null, { params: { days } })
  },

  // Auth endpoints
  registerUser(data) {
    return api.post('/auth/register', data)
  },
  login(data) {
    return api.post('/auth/token', data, { skipAuthRefresh: true, skipAuthHeader: true })
  },
  refreshToken(data) {
    return api.post('/auth/refresh', data, { skipAuthRefresh: true, skipAuthHeader: true })
  },
  logout(data) {
    return api.post('/auth/logout', data, { skipAuthRefresh: true, skipAuthHeader: true })
  },
  getMe() {
    return api.get('/auth/me')
  },
  
  // Position analysis
  getPositionAnalysis(params) {
    return api.get('/risk-control/positions/analysis', { params })
  },

  // Order risk check
  checkOrderRisk(params) {
    return api.post('/risk-control/check-order-risk', params)
  }
}

export const marketInsight = {
  getDashboard(params) {
    return api.get('/market-insight/dashboard', { params })
  },
  getAnomalies(params) {
    return api.get('/market-insight/anomalies', { params })
  },
  getAnomalyDetail(eventId) {
    return api.get(`/market-insight/anomalies/${eventId}`)
  },
  scanAnomalies(limit = 10) {
    return api.post('/market-insight/anomalies/scan', null, { params: { limit } })
  },
  getKlines(params) {
    return api.get('/market-insight/klines', { params })
  },
  getPatterns(params) {
    return api.get('/market-insight/patterns', { params })
  },
  scanPatterns(params) {
    return api.get('/market-insight/patterns/scan', { params })
  }
}

export const dashboard = {
  getSummary() {
    return api.get('/dashboard/summary')
  },
  getPositionChart(timeRange) {
    return api.get('/dashboard/charts/position', { params: { time_range: timeRange } })
  },
  getEquityChart(timeRange) {
    return api.get('/dashboard/charts/equity', { params: { time_range: timeRange } })
  },
  getRiskChart() {
    return api.get('/dashboard/charts/risk')
  },
  getRecentAlerts() {
    return api.get('/dashboard/alerts')
  }
}

export default {
  riskControl,
  dashboard,
  marketInsight
}
