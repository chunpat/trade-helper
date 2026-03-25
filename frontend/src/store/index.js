import { createStore } from 'vuex'
import { clearAuthStorage, getAuthStorageEventName, getStoredAuthState, riskControl, saveAuthTokens } from '../api'
import { getStoredDisplayTimezone, setStoredDisplayTimezone } from '../utils/datetime'

const storedAuthState = getStoredAuthState()

const store = createStore({
  state: {
    token: storedAuthState.token,
    refreshToken: storedAuthState.refreshToken,
    tokenExpiresAt: storedAuthState.tokenExpiresAt,
    displayTimezone: getStoredDisplayTimezone(),
    currentUser: null,
    accounts: [],
    positions: [],
    alerts: [],
    riskConfigs: {},
    dashboardData: {
      totalPositionValue: 0,
      positionValueStatus: 'normal',
      dayChange: 0,
      activeAlerts: 0,
      alertStatus: 'normal',
      highRiskAlerts: 0,
      mediumRiskAlerts: 0,
      dailyPnL: 0,
      pnlStatus: 'normal',
      pnlRatio: 0,
      activeAccounts: 0,
      normalAccounts: 0,
      abnormalAccounts: 0
    }
  },

  mutations: {
    SET_AUTH_STATE(state, authState) {
      state.token = authState?.token || null
      state.refreshToken = authState?.refreshToken || null
      state.tokenExpiresAt = authState?.tokenExpiresAt || null
    },
    SET_DISPLAY_TIMEZONE(state, timezone) {
      state.displayTimezone = timezone || 'system'
    },
    SET_CURRENT_USER(state, user) {
      state.currentUser = user
    },
    SET_ACCOUNTS(state, accounts) {
      state.accounts = accounts
    },
    SET_POSITIONS(state, positions) {
      state.positions = positions
    },
    SET_ALERTS(state, alerts) {
      state.alerts = alerts
    },
    SET_RISK_CONFIG(state, { accountId, config }) {
      state.riskConfigs[accountId] = config
    },
    UPDATE_DASHBOARD_DATA(state, data) {
      state.dashboardData = { ...state.dashboardData, ...data }
    },
    UPDATE_ALERT(state, updatedAlert) {
      const index = state.alerts.findIndex(alert => alert.id === updatedAlert.id)
      if (index !== -1) {
        state.alerts.splice(index, 1, updatedAlert)
      }
    }
    ,
    UPDATE_POSITION(state, updatedPosition) {
      const idx = state.positions.findIndex(p => p.id === updatedPosition.id)
      
      // If position is no longer active, remove it from the list
      if (updatedPosition.is_active === false) {
        if (idx !== -1) {
          state.positions.splice(idx, 1)
        }
        return
      }

      if (idx !== -1) {
        // merge the updated fields into existing position
        state.positions.splice(idx, 1, { ...state.positions[idx], ...updatedPosition })
      } else {
        // if not found and is active, push to list
        if (updatedPosition.is_active !== false) {
          state.positions.push(updatedPosition)
        }
      }
    }
  },

  actions: {
    setDisplayTimezone({ commit }, timezone) {
      setStoredDisplayTimezone(timezone)
      commit('SET_DISPLAY_TIMEZONE', timezone)
    },
    // Auth actions
    async login({ commit }, { username, password }) {
      try {
        const data = await riskControl.login({ username, password })
        commit('SET_AUTH_STATE', saveAuthTokens(data))
        // optionally fetch current user
        // we don't have an endpoint returning me yet (me exists), but we can call it
        try {
          const me = await riskControl.getMe()
          commit('SET_CURRENT_USER', me)
        } catch (e) {
          // ignore
        }
        return data
      } catch (e) {
        throw e
      }
    },
    async logout({ commit, state }) {
      if (state.refreshToken) {
        try {
          await riskControl.logout({ refresh_token: state.refreshToken })
        } catch (_) {
          // ignore logout failures and clear local auth state regardless
        }
      }

      clearAuthStorage()
      commit('SET_AUTH_STATE', { token: null, refreshToken: null, tokenExpiresAt: null })
      commit('SET_CURRENT_USER', null)
    },
    async fetchCurrentUser({ commit, state }) {
      const authState = state.token || state.refreshToken ? state : getStoredAuthState()
      if (!authState.token && !authState.refreshToken) return null
      try {
        const me = await riskControl.getMe()
        commit('SET_CURRENT_USER', me)
        return me
      } catch (e) {
        // token invalid or other issue - clear token
        clearAuthStorage()
        commit('SET_AUTH_STATE', { token: null, refreshToken: null, tokenExpiresAt: null })
        commit('SET_CURRENT_USER', null)
        return null
      }
    },
    async register({ dispatch }, { username, password }) {
      await riskControl.registerUser({ username, password })
      // auto-login after register
      return dispatch('login', { username, password })
    },
    // Account actions
    async fetchAccounts({ commit }) {
      try {
        const accounts = await riskControl.getAccounts()
        commit('SET_ACCOUNTS', accounts)
        return accounts
      } catch (error) {
        console.error('Failed to fetch accounts:', error)
        throw error
      }
    },

    async createAccount({ dispatch }, accountData) {
      try {
        const account = await riskControl.createAccount(accountData)
        await dispatch('fetchAccounts')
        return account
      } catch (error) {
        console.error('Failed to create account:', error)
        throw error
      }
    },

    // Risk config actions
    async fetchRiskConfig({ commit }, accountId) {
      try {
        const config = await riskControl.getRiskConfig(accountId)
        commit('SET_RISK_CONFIG', { accountId, config })
        return config
      } catch (error) {
        console.error('Failed to fetch risk config:', error)
        throw error
      }
    },

    async updateRiskConfig({ commit }, { accountId, configData }) {
      try {
        const config = await riskControl.updateRiskConfig(accountId, configData)
        commit('SET_RISK_CONFIG', { accountId, config })
        return config
      } catch (error) {
        console.error('Failed to update risk config:', error)
        throw error
      }
    },

    // Position actions
    async fetchPositions({ commit }, params) {
      try {
        const positions = await riskControl.getPositions(params)
        commit('SET_POSITIONS', positions)
        return positions
      } catch (error) {
        console.error('Failed to fetch positions:', error)
        throw error
      }
    },
    async triggerSyncPositions({ dispatch }) {
      try {
        await riskControl.syncPositions()
        // wait shortly then refresh positions and accounts
        await dispatch('fetchPositions')
        await dispatch('fetchAccounts')
      } catch (error) {
        console.error('Failed to sync positions:', error)
        throw error
      }
    },

    async triggerAccountSync({ dispatch }, accountId) {
      try {
        await riskControl.syncAccountPositions(accountId)
        // refresh positions for that account
        await dispatch('fetchPositions', { account_id: accountId })
      } catch (error) {
        console.error('Failed to sync account positions:', error)
        throw error
      }
    },
    async checkPositionRisk(_, params) {
      try {
        return await riskControl.checkPositionRisk(params)
      } catch (error) {
        console.error('Failed to check position risk:', error)
        throw error
      }
    },

    async createPosition({ dispatch }, positionData) {
      try {
        const position = await riskControl.createPosition(positionData)
        await dispatch('fetchPositions')
        return position
      } catch (error) {
        console.error('Failed to create position:', error)
        throw error
      }
    },

    // Alert actions
    async fetchAlerts({ commit }, params) {
      try {
        const alerts = await riskControl.getRiskAlerts(params)
        commit('SET_ALERTS', alerts)
        return alerts
      } catch (error) {
        console.error('Failed to fetch alerts:', error)
        throw error
      }
    },

    async resolveAlert({ commit }, { alertId, notes }) {
      try {
        const updatedAlert = await riskControl.resolveAlert(alertId, notes)
        commit('UPDATE_ALERT', updatedAlert)
        return updatedAlert
      } catch (error) {
        console.error('Failed to resolve alert:', error)
        throw error
      }
    },

    // Dashboard actions
    async fetchDashboardData({ commit }, accountId) {
      try {
        const summaryData = await riskControl.getAccountRiskSummary(accountId)
        commit('UPDATE_DASHBOARD_DATA', summaryData)
        return summaryData
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error)
        throw error
      }
    },

    // Order risk check
    async checkOrderRisk(_, params) {
      try {
        return await riskControl.checkOrderRisk(params)
      } catch (error) {
        console.error('Failed to check order risk:', error)
        throw error
      }
    }
  },

  getters: {
    displayTimezone: (state) => state.displayTimezone,
    getAccountById: (state) => (id) => {
      return state.accounts.find(account => account.id === id)
    },
    getRiskConfigByAccountId: (state) => (accountId) => {
      return state.riskConfigs[accountId]
    },
    activeAlerts: (state) => {
      return state.alerts.filter(alert => !alert.is_resolved)
    },
    alertsByRiskLevel: (state) => (riskLevel) => {
      return state.alerts.filter(alert => alert.risk_level === riskLevel)
    },
    dashboardMetrics: (state) => {
      return state.dashboardData
    }
  }
})

if (typeof window !== 'undefined') {
  window.addEventListener(getAuthStorageEventName(), event => {
    store.commit('SET_AUTH_STATE', event.detail || getStoredAuthState())
  })
}

export default store
