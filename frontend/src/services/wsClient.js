import { getAuthStorageEventName, getStoredAuthState, refreshAccessToken } from '../api'

let ws = null
let reconnectTimer = null
let storeRef = null
let listening = false
let connectionVersion = 0

function getWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/ws`
}

export function startWebSocket(store) {
  storeRef = store
  if (!listening) {
    window.addEventListener(getAuthStorageEventName(), restartConnection)
    listening = true
  }
  restartConnection()
}

function restartConnection() {
  connectionVersion += 1
  clearTimeout(reconnectTimer)
  reconnectTimer = null
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  if (getStoredAuthState().token) connect(connectionVersion)
}

async function connect(version) {
  try {
    const auth = getStoredAuthState()
    if (!auth.token || version !== connectionVersion) return
    if (auth.refreshToken && auth.tokenExpiresAt <= Date.now() + 90000) {
      await refreshAccessToken()
      // 刷新成功会触发登录状态事件，由新连接接手。
      return
    }
    const socket = new WebSocket(getWsUrl())
    ws = socket
    socket.onopen = () => {
      if (version !== connectionVersion) return socket.close()
      socket.send(JSON.stringify({ type: 'auth', token: auth.token }))
    }
    socket.onmessage = (event) => {
      if (version !== connectionVersion) return
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'position_update' && payload.data && storeRef) {
          storeRef.commit('UPDATE_POSITION', payload.data)
        }
      } catch (error) {
        console.error('实时消息解析失败', error)
      }
    }
    socket.onclose = () => scheduleReconnect(version)
    socket.onerror = () => socket.close()
  } catch (error) {
    console.error('实时连接失败', error)
    scheduleReconnect(version)
  }
}

function scheduleReconnect(version) {
  if (version !== connectionVersion || !getStoredAuthState().token) return
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(() => connect(version), 2000)
}

export function stopWebSocket() {
  window.removeEventListener(getAuthStorageEventName(), restartConnection)
  listening = false
  connectionVersion += 1
  clearTimeout(reconnectTimer)
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
}
