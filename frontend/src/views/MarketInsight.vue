<template>
  <div class="momentum-page">
    <el-page-header @back="$router.back()" content="市场洞察 · 短线量价雷达" class="page-header" />

    <el-card shadow="never" class="intro-card">
      <div class="intro-row">
        <div>
          <h2>只抓刚开始放量的山寨币</h2>
          <p>短周期上涨只作为候选；必须放量突破前48小时压力位，并超过币种自身波动噪声，才触发预警。</p>
        </div>
        <div class="intro-actions">
          <el-tag type="warning" effect="plain">不追 24H 榜一</el-tag>
          <el-button :icon="Refresh" :loading="loading || marketCapLoading" type="primary" @click="refreshAll">刷新</el-button>
        </div>
      </div>
      <div class="scan-meta">
        <span>本轮分析 {{ scannedCount }} 个高流动性合约</span>
        <span>更新时间：{{ formatTime(updatedAt) }}</span>
        <span>每 30 秒自动刷新</span>
      </div>
    </el-card>

    <el-card shadow="never" class="method-card">
      <template #header>
        <div class="card-header">
          <div>
            <strong>计算方法与雷达参数</strong>
            <p>参数会保存在当前浏览器，并直接参与后端筛选计算</p>
          </div>
          <div class="settings-actions">
            <el-button size="small" @click="resetSettings">恢复默认</el-button>
            <el-button size="small" type="primary" @click="applySettings">应用参数</el-button>
          </div>
        </div>
      </template>

      <el-alert type="info" :closable="false" show-icon class="formula-alert">
        <template #title>
          实现波动率 = 1小时对数收益率的标准差 × √(周期小时数) × 100%。压力/支撑取指定回看窗口内的最高/最低价，并排除最近若干小时。有效突破阈值 = max（最小突破幅度，5分钟预期波动 × 噪声倍数）。
        </template>
      </el-alert>

      <div class="radar-presets">
        <span class="preset-label">组合阈值预设</span>
        <el-radio-group :model-value="activeRadarPreset" @change="applyRadarPreset">
          <el-radio-button
            v-for="preset in radarPresetOptions"
            :key="preset.key"
            :label="preset.key"
          >
            {{ preset.label }}
          </el-radio-button>
        </el-radio-group>
        <span class="preset-hint">
          {{ activeRadarPresetConfig?.description || '当前参数为自定义组合' }}
        </span>
        <span class="preset-scope">本页预设仅影响当前浏览器；钉钉后台告警请在“风控配置”中选择并保存。</span>
      </div>

      <el-form :inline="true" label-position="top" class="settings-form">
        <el-form-item label="最小量比">
          <el-input-number v-model="radarSettings.volume_ratio_min" :min="1" :max="5" :step="0.1" :precision="1" />
        </el-form-item>
        <el-form-item label="压力位回看（小时）">
          <el-input-number v-model="radarSettings.resistance_hours" :min="12" :max="168" :step="12" />
        </el-form-item>
        <el-form-item label="排除最近（小时）">
          <el-input-number v-model="radarSettings.exclude_recent_hours" :min="1" :max="12" :step="1" />
        </el-form-item>
        <el-form-item label="波动率周期（天）">
          <el-input-number v-model="radarSettings.volatility_days" :min="3" :max="14" :step="1" />
        </el-form-item>
        <el-form-item label="噪声倍数">
          <el-input-number v-model="radarSettings.noise_multiplier" :min="0.1" :max="1.5" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="最小突破幅度（%）">
          <el-input-number v-model="radarSettings.min_breakout_percent" :min="0.01" :max="2" :step="0.01" :precision="2" />
        </el-form-item>
        <el-form-item label="24H最大涨幅（%）">
          <el-input-number v-model="radarSettings.max_24h_change" :min="3" :max="30" :step="1" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="18" class="radar-grid">
      <el-col :xs="24" :xl="12">
        <el-card shadow="hover" class="radar-card five-minute">
          <template #header>
            <div class="card-header">
              <div>
                <strong>⚡ 5 分钟放量启动</strong>
                <p>5m上涨 + 放量 + 压力位有效突破</p>
              </div>
              <el-tag type="danger" effect="dark">更快 · 更敏感</el-tag>
            </div>
          </template>
          <signal-table :rows="fiveMinute" period="5m" />
        </el-card>
      </el-col>

      <el-col :xs="24" :xl="12">
        <el-card shadow="hover" class="radar-card fifteen-minute">
          <template #header>
            <div class="card-header">
              <div>
                <strong>🚀 15 分钟量价确认</strong>
                <p>15m趋势确认 + 放量 + 压力位有效突破</p>
              </div>
              <el-tag type="success" effect="dark">更稳 · 已确认</el-tag>
            </div>
          </template>
          <signal-table :rows="fifteenMinute" period="15m" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" class="market-cap-card">
      <template #header>
        <div class="card-header">
          <div>
            <strong>🌐 市值头部币种波动率</strong>
            <p>按全球市值排序，使用最近7天小时价格计算实现波动率</p>
          </div>
          <el-select v-model="marketCapLimit" size="small" class="rank-select">
            <el-option label="市值 Top 20" :value="20" />
            <el-option label="市值 Top 30" :value="30" />
          </el-select>
        </div>
      </template>
      <el-table v-loading="marketCapLoading" :data="visibleMarketCapItems" stripe size="small">
        <el-table-column prop="rank" label="排名" width="70" />
        <el-table-column label="币种" min-width="150">
          <template #default="{ row }">
            <strong class="symbol">{{ row.symbol }}</strong>
            <span class="coin-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="现价" min-width="120" align="right">
          <template #default="{ row }">${{ formatPrice(row.last_price) }}</template>
        </el-table-column>
        <el-table-column label="市值" min-width="130" align="right">
          <template #default="{ row }">{{ formatVolume(row.market_cap) }}</template>
        </el-table-column>
        <el-table-column label="24H涨幅" min-width="110" align="right">
          <template #default="{ row }">
            <el-tag :type="row.price_change_percent_24h >= 0 ? 'success' : 'danger'" size="small">
              {{ row.price_change_percent_24h >= 0 ? '+' : '' }}{{ Number(row.price_change_percent_24h).toFixed(2) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="7日波动率" min-width="120" align="right">
          <template #default="{ row }">
            <strong :class="volatilityClass(row.volatility_7d)">{{ Number(row.volatility_7d).toFixed(2) }}%</strong>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="市值波动率数据暂不可用" :image-size="64" />
        </template>
      </el-table>
      <div class="cap-updated">更新时间：{{ formatTime(marketCapUpdatedAt) }} · 每5分钟刷新</div>
    </el-card>

    <el-alert
      title="量价启动只是观察信号，不是开仓指令。优先等回踩承接，避免在单根放量阳线末端追入。"
      type="warning"
      :closable="false"
      show-icon
      class="risk-alert"
    />
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, onUnmounted, ref } from 'vue'
import { ElEmpty, ElMessage, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useStore } from 'vuex'
import { marketInsight } from '@/api'
import {
  MARKET_ALERT_PRESETS,
  MARKET_ALERT_PRESET_OPTIONS,
} from '@/constants/marketAlertPresets'
import { parseBackendDateTime, resolveDisplayTimezone } from '@/utils/datetime'

const store = useStore()
const loading = ref(false)
const fiveMinute = ref([])
const fifteenMinute = ref([])
const scannedCount = ref(0)
const updatedAt = ref('')
const marketCapLoading = ref(false)
const marketCapItems = ref([])
const marketCapLimit = ref(30)
const marketCapUpdatedAt = ref('')
const RADAR_SETTINGS_KEY = 'market-insight-radar-settings'
const radarPresetOptions = MARKET_ALERT_PRESET_OPTIONS
const defaultRadarSettings = {
  ...MARKET_ALERT_PRESETS.balanced.radarSettings
}

const loadSavedRadarSettings = () => {
  try {
    const saved = JSON.parse(window.localStorage.getItem(RADAR_SETTINGS_KEY) || '{}')
    return { ...defaultRadarSettings, ...saved }
  } catch (_) {
    return { ...defaultRadarSettings }
  }
}

const radarSettings = ref(loadSavedRadarSettings())
let refreshTimer = null
let marketCapTimer = null

const visibleMarketCapItems = computed(() => marketCapItems.value.slice(0, marketCapLimit.value))
const displayTimezone = computed(() => store.getters.displayTimezone)
const activeRadarPreset = computed(() => {
  const matched = radarPresetOptions.find((preset) => (
    Object.entries(preset.radarSettings).every(
      ([key, value]) => Number(radarSettings.value[key]) === Number(value)
    )
  ))
  return matched?.key || ''
})
const activeRadarPresetConfig = computed(() => (
  MARKET_ALERT_PRESETS[activeRadarPreset.value] || null
))

const formatSymbol = (symbol) => String(symbol || '').replace(/USDT$/, '/USDT')

const formatPrice = (value) => {
  const price = Number(value || 0)
  if (price < 0.01) return price.toFixed(6)
  if (price < 1) return price.toFixed(4)
  return price.toFixed(2)
}

const formatVolume = (value) => {
  const amount = Number(value || 0)
  if (amount >= 1e9) return `$${(amount / 1e9).toFixed(2)}B`
  if (amount >= 1e6) return `$${(amount / 1e6).toFixed(1)}M`
  if (amount >= 1e3) return `$${(amount / 1e3).toFixed(1)}K`
  return `$${amount.toFixed(0)}`
}

const formatTime = (value) => {
  const date = parseBackendDateTime(value)
  if (!date) return '-'

  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: resolveDisplayTimezone(displayTimezone.value)
  }).format(date)
}

const scoreTagType = (score) => {
  if (score >= 75) return 'danger'
  if (score >= 55) return 'warning'
  return 'info'
}

const volatilityClass = (value) => {
  const volatility = Number(value || 0)
  if (volatility >= 25) return 'volatility-high'
  if (volatility >= 12) return 'volatility-medium'
  return 'volatility-low'
}

const SignalTable = defineComponent({
  name: 'SignalTable',
  props: {
    rows: { type: Array, default: () => [] },
    period: { type: String, required: true }
  },
  setup(props) {
    const cell = (renderer) => ({ row }) => renderer(row)
    return () => h(ElTable, {
      data: props.rows,
      stripe: true,
      size: 'small',
      class: 'signal-table'
    }, {
      default: () => [
        h(ElTableColumn, { label: '币种', minWidth: 105, fixed: 'left' }, {
          default: cell((row) => h('strong', { class: 'symbol' }, formatSymbol(row.symbol)))
        }),
        h(ElTableColumn, { label: '现价', minWidth: 100, align: 'right' }, {
          default: cell((row) => `$${formatPrice(row.last_price)}`)
        }),
        h(ElTableColumn, { label: `${props.period}涨幅`, minWidth: 95, align: 'right' }, {
          default: cell((row) => h(ElTag, { type: 'success', size: 'small' }, () =>
            `+${Number(props.period === '5m' ? row.change_5m : row.change_15m).toFixed(2)}%`
          ))
        }),
        h(ElTableColumn, { label: `${props.period}量比`, minWidth: 90, align: 'right' }, {
          default: cell((row) => h('strong', { class: 'volume-ratio' },
            `${Number(props.period === '5m' ? row.volume_ratio_5m : row.volume_ratio_15m).toFixed(1)}x`
          ))
        }),
        h(ElTableColumn, { label: '24H涨幅', minWidth: 90, align: 'right' }, {
          default: cell((row) => `${Number(row.price_change_percent_24h) >= 0 ? '+' : ''}${Number(row.price_change_percent_24h).toFixed(2)}%`)
        }),
        h(ElTableColumn, { label: '24H成交额', minWidth: 100, align: 'right' }, {
          default: cell((row) => formatVolume(row.quote_volume_24h))
        }),
        h(ElTableColumn, { label: `${radarSettings.value.volatility_days}日波动率`, minWidth: 100, align: 'right' }, {
          default: cell((row) => `${Number(row.volatility_7d || 0).toFixed(1)}%`)
        }),
        h(ElTableColumn, { label: '压力位', minWidth: 105, align: 'right' }, {
          default: cell((row) => `$${formatPrice(row.resistance)}`)
        }),
        h(ElTableColumn, { label: '支撑位', minWidth: 105, align: 'right' }, {
          default: cell((row) => `$${formatPrice(row.support)}`)
        }),
        h(ElTableColumn, { label: '突破幅度', minWidth: 100, align: 'right' }, {
          default: cell((row) => h(ElTag, { type: 'danger', size: 'small' }, () =>
            `+${Number(row.breakout_percent || 0).toFixed(2)}%`
          ))
        }),
        h(ElTableColumn, { label: '启动分', minWidth: 80, align: 'right' }, {
          default: cell((row) => h(ElTag, { type: scoreTagType(row.score), effect: 'dark', size: 'small' }, () => String(Math.round(row.score))))
        })
      ],
      empty: () => h(ElEmpty, { description: '当前没有完成放量突破的标的', imageSize: 64 })
    })
  }
})

async function loadRadar(silent = true) {
  if (loading.value) return
  loading.value = true
  try {
    const data = await marketInsight.getMomentumRadar({
      limit: 15,
      ...radarSettings.value
    })
    fiveMinute.value = data.five_minute || []
    fifteenMinute.value = data.fifteen_minute || []
    scannedCount.value = data.scanned_count || 0
    updatedAt.value = data.timestamp || ''
    if (!silent) ElMessage.success('量价雷达已刷新')
  } catch (error) {
    console.error('Failed to load momentum radar:', error)
    if (!silent) ElMessage.error('量价雷达加载失败')
  } finally {
    loading.value = false
  }
}

async function loadMarketCap(silent = true) {
  if (marketCapLoading.value) return
  marketCapLoading.value = true
  try {
    const data = await marketInsight.getMarketCapVolatility({ limit: 30 })
    marketCapItems.value = data.items || []
    marketCapUpdatedAt.value = data.timestamp || ''
  } catch (error) {
    console.error('Failed to load market cap volatility:', error)
    if (!silent) ElMessage.error('市值波动率加载失败')
  } finally {
    marketCapLoading.value = false
  }
}

function refreshAll() {
  loadRadar(false)
  loadMarketCap(false)
}

function applySettings() {
  window.localStorage.setItem(RADAR_SETTINGS_KEY, JSON.stringify(radarSettings.value))
  loadRadar(false)
}

function applyRadarPreset(presetKey) {
  const preset = MARKET_ALERT_PRESETS[presetKey]
  if (!preset) return
  radarSettings.value = { ...preset.radarSettings }
  window.localStorage.setItem(RADAR_SETTINGS_KEY, JSON.stringify(radarSettings.value))
  loadRadar(false)
}

function resetSettings() {
  radarSettings.value = { ...defaultRadarSettings }
  window.localStorage.setItem(RADAR_SETTINGS_KEY, JSON.stringify(radarSettings.value))
  loadRadar(false)
}

onMounted(() => {
  loadRadar(true)
  loadMarketCap(true)
  refreshTimer = window.setInterval(() => loadRadar(true), 30000)
  marketCapTimer = window.setInterval(() => loadMarketCap(true), 300000)
})

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (marketCapTimer) window.clearInterval(marketCapTimer)
})
</script>

<style scoped>
.momentum-page {
  padding: 20px;
  min-height: 100%;
  background: #f5f7fa;
}

.page-header { margin-bottom: 18px; }
.intro-card { border-radius: 12px; }
.method-card { border-radius: 12px; margin-top: 18px; }
.intro-row, .card-header, .scan-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.intro-row h2 { margin: 0 0 8px; font-size: 21px; color: #172033; }
.intro-row p, .card-header p { margin: 0; color: #667085; font-size: 13px; }
.intro-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.scan-meta {
  justify-content: flex-start;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #eaecf0;
  color: #667085;
  font-size: 12px;
}
.radar-grid { margin-top: 18px; }
.radar-card { border-radius: 12px; margin-bottom: 18px; }
.five-minute { border-top: 3px solid #f04438; }
.fifteen-minute { border-top: 3px solid #12b76a; }
.card-header strong { display: block; margin-bottom: 5px; font-size: 16px; }
.symbol { color: #155eef; }
.volume-ratio { color: #d92d20; font-size: 15px; }
.risk-alert { margin-top: 2px; }
.settings-actions { display: flex; gap: 8px; }
.formula-alert { margin-bottom: 14px; }
.radar-presets {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
  padding: 12px;
  border-radius: 8px;
  background: #f8fafc;
}
.preset-label { color: #344054; font-size: 13px; font-weight: 600; }
.preset-hint { color: #667085; font-size: 12px; }
.preset-scope {
  flex-basis: 100%;
  color: #98a2b3;
  font-size: 12px;
}
.settings-form :deep(.el-form-item) { margin-right: 18px; margin-bottom: 8px; }
.settings-form :deep(.el-input-number) { width: 155px; }
.market-cap-card { border-radius: 12px; margin-bottom: 18px; }
.rank-select { width: 140px; }
.coin-name { margin-left: 8px; color: #667085; font-size: 12px; }
.cap-updated { margin-top: 12px; color: #98a2b3; font-size: 12px; text-align: right; }
.volatility-high { color: #d92d20; }
.volatility-medium { color: #dc6803; }
.volatility-low { color: #039855; }

@media (max-width: 768px) {
  .momentum-page { padding: 12px; }
  .intro-row { align-items: flex-start; flex-direction: column; }
  .intro-actions { width: 100%; justify-content: space-between; }
  .scan-meta { align-items: flex-start; flex-direction: column; gap: 5px; }
}
</style>
