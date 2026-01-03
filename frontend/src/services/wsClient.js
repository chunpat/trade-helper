// Simple WebSocket client to receive real-time updates from backend

let ws = null
let reconnectTimeout = 2000
let storeRef = null

function getWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/ws`
}

export function startWebSocket(store) {
  storeRef = store
  connect()
}

function connect() {
  const url = getWsUrl()
  try {
    ws = new WebSocket(url)
  } catch (err) {
    console.error('WebSocket connection error', err)
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    console.info('WebSocket connected to', url)
    // you can send a hello if needed
    // ws.send(JSON.stringify({ type: 'hello', data: 'frontend' }))
  }

  ws.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data)
      if (payload.type === 'position_update' && payload.data) {
        const pos = payload.data
        // commit mutation to update single position
        if (storeRef) {
          storeRef.commit('UPDATE_POSITION', pos)
        }
      }
    } catch (err) {
      console.error('WebSocket message parse error', err)
    }
  }

  ws.onclose = (evt) => {
    console.warn('WebSocket closed, scheduling reconnect', evt.code)
    scheduleReconnect()
  }

  ws.onerror = (err) => {
    console.error('WebSocket error', err)
    try {
      ws.close()
    } catch (e) {
      // ignore
    }
  }
}

function scheduleReconnect() {
  setTimeout(() => {
    connect()
  }, reconnectTimeout)
}

export function stopWebSocket() {
  if (ws) {
    try {
      ws.close()
    } catch (e) {
      // ignore
    }
  }
  ws = null
}
