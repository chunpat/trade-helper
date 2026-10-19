import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import axios from 'axios'
import { createServer } from 'vite'

let server
let auth
let store
let adapter

before(async () => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key)
  }
  globalThis.window = new EventTarget()
  window.localStorage = globalThis.localStorage
  window.location = { pathname: '/login' }
  axios.defaults.adapter = config => adapter(config)
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  auth = await server.ssrLoadModule('/src/api/index.js')
  store = (await server.ssrLoadModule('/src/store/index.js')).default
})

after(async () => {
  await server?.close()
})

function tokens(name) {
  return { access_token: `${name}-access`, refresh_token: `${name}-refresh`, expires_in: 1800 }
}

function pendingRequest() {
  let complete
  let started
  const ready = new Promise(resolve => { started = resolve })
  adapter = config => new Promise(resolve => {
    complete = data => resolve({ config, data, status: 200, headers: {} })
    started()
  })
  return { ready, finish: data => complete(data) }
}

test('退出后清空旧用户的所有业务数据', () => {
  auth.saveAuthTokens(tokens('admin'))
  store.commit('SET_CURRENT_USER', { username: 'admin' })
  store.commit('SET_ACCOUNTS', [{ id: 1 }])
  store.commit('SET_POSITIONS', [{ id: 1 }])
  store.commit('SET_ALERTS', [{ id: 1 }])
  store.commit('SET_RISK_CONFIG', { accountId: 1, config: { secret: true } })
  store.commit('UPDATE_DASHBOARD_DATA', { totalPositionValue: 1000 })
  auth.clearAuthStorage()
  assert.equal(store.state.currentUser, null)
  assert.equal(store.state.accounts.length, 0)
  assert.equal(store.state.positions.length, 0)
  assert.equal(store.state.alerts.length, 0)
  assert.equal(Object.keys(store.state.riskConfigs).length, 0)
  assert.equal(store.state.dashboardData.totalPositionValue, 0)
})

test('切换用户后丢弃旧账户列表响应', async () => {
  auth.saveAuthTokens(tokens('admin'))
  const request = pendingRequest()
  const result = store.dispatch('fetchAccounts')
  const rejected = assert.rejects(result, /登录用户已切换/)
  await request.ready
  auth.clearAuthStorage()
  auth.saveAuthTokens(tokens('alice'))
  request.finish([{ id: 1, name: 'admin' }])
  await rejected
  assert.equal(store.state.accounts.length, 0)
  assert.equal(auth.getStoredAuthState().token, 'alice-access')
})

test('旧刷新请求不能覆盖新账号的登录凭证', async () => {
  auth.saveAuthTokens(tokens('admin'))
  const request = pendingRequest()
  const result = auth.refreshAccessToken()
  const rejected = assert.rejects(result, /登录用户已切换/)
  await request.ready
  auth.clearAuthStorage()
  auth.saveAuthTokens(tokens('alice'))
  request.finish(tokens('admin-refreshed'))
  await rejected
  assert.equal(auth.getStoredAuthState().token, 'alice-access')
})

test('旧用户资料请求失败不能清掉新账号', async () => {
  auth.saveAuthTokens(tokens('admin'))
  const request = pendingRequest()
  const result = store.dispatch('fetchCurrentUser')
  await request.ready
  auth.clearAuthStorage()
  auth.saveAuthTokens(tokens('alice'))
  store.commit('SET_CURRENT_USER', { username: 'alice' })
  request.finish({ username: 'admin' })
  await result
  assert.equal(store.state.currentUser.username, 'alice')
  assert.equal(auth.getStoredAuthState().token, 'alice-access')
})

test('其他标签页切换账号会清空页面并重新加载', () => {
  let reloads = 0
  window.location.reload = () => { reloads += 1 }
  store.commit('SET_ACCOUNTS', [{ id: 1, name: 'admin' }])
  const event = new Event('storage')
  Object.assign(event, { key: 'token', oldValue: 'admin-access', newValue: 'alice-access' })
  window.dispatchEvent(event)
  assert.equal(store.state.accounts.length, 0)
  assert.equal(reloads, 1)
})
