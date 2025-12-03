import { createStore } from 'vuex'
import { riskControl } from '../api'

export default createStore({
  state: {
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
  },

  actions: {
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
