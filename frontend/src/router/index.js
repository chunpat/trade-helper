import { createRouter, createWebHistory } from 'vue-router'
import { getStoredAuthState } from '../api'
import store from '../store'

const routes = [
  {
    path: '/',
    name: 'Landing',
    component: () => import('../views/Landing.vue'),
    meta: { layout: 'blank' }
  },
  {
    path: '/pricing',
    name: 'Pricing',
    component: () => import('../views/Pricing.vue'),
    meta: { layout: 'blank' }
  },
  {
    path: '/app',
    redirect: '/dashboard'
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/accounts',
    name: 'Accounts',
    component: () => import('../views/Accounts.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/positions',
    name: 'Positions',
    component: () => import('../views/Positions.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/trade-review',
    name: 'TradeReview',
    component: () => import('../views/TradeReview.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue')
  },
  {
    path: '/risk-alerts',
    name: 'RiskAlerts',
    component: () => import('../views/RiskAlerts.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/Settings.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/market-insight',
    name: 'MarketInsight',
    component: () => import('../views/MarketInsight.vue'),
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Global navigation guard for auth
router.beforeEach((to, from, next) => {
  const requiresAuth = to.matched.some(record => record.meta && record.meta.requiresAuth)
  const authState = getStoredAuthState()
  const token = store.state.token || authState.token || authState.refreshToken
  if (requiresAuth && !token) {
    return next({ name: 'Login' })
  }
  // if going to login page while already authenticated, redirect to positions
  if (to.name === 'Login' && token) {
    return next({ name: 'Positions' })
  }
  next()
})

export default router
