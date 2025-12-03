import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/dashboard'
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue')
  },
  {
    path: '/accounts',
    name: 'Accounts',
    component: () => import('../views/Accounts.vue')
  },
  {
    path: '/positions',
    name: 'Positions',
    component: () => import('../views/Positions.vue')
  },
  {
    path: '/risk-alerts',
    name: 'RiskAlerts',
    component: () => import('../views/RiskAlerts.vue')
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/Settings.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
