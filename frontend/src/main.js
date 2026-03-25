import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import store from './store'
import { getStoredAuthState } from './api'
import { startWebSocket } from './services/wsClient'

// Create Vue app
const app = createApp(App)

// Register Element Plus icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// Use plugins
app.use(ElementPlus)
app.use(store)
app.use(router)

// try to populate current user if auth state exists
const authState = getStoredAuthState()
if (authState.token || authState.refreshToken) {
  // fetch current user into store (best-effort)
  store.dispatch('fetchCurrentUser').catch(() => {})
}

// start websocket connection to receive real-time updates
startWebSocket(store)

// Global error handler
app.config.errorHandler = (err, vm, info) => {
  console.error('Global error:', err)
  console.error('Error Info:', info)
}

// Mount app
app.mount('#app')
