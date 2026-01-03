import axios from 'axios'

const api = axios.create({
  baseURL: process.env.VUE_APP_API_URL || 'http://localhost:8029/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
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
  error => {
    if (error.response) {
      if (error.response.status === 401) {
        // Handle unauthorized access
        localStorage.removeItem('token')
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
  syncAccountHistory(accountId) {
    return api.post(`/risk-control/accounts/${accountId}/sync-history`)
  },

  // Auth endpoints
  registerUser(data) {
    return api.post('/auth/register', data)
  },
  login(data) {
    return api.post('/auth/token', data)
  },
  getMe() {
    return api.get('/auth/me')
  },
  
  // Order risk check
  checkOrderRisk(params) {
    return api.post('/risk-control/check-order-risk', params)
  }
}

export const dashboard = {
  getSummary() {
    return api.get('/dashboard/summary')
  },
  getPositionChart(timeRange) {
    return api.get('/dashboard/charts/position', { params: { time_range: timeRange } })
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
  dashboard
}
