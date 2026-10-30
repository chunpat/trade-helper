<template>
  <el-card shadow="hover" class="rsi-card">
    <template #header>
      <div class="rsi-header">
        <div>
          <strong>1 小时 RSI 背离 · {{ radar.preset_label }}筛选</strong>
          <p>独立扫描币安所有 24H 成交额 ≥ 1 亿 USDT 的活跃加密永续合约，不限前 30，展示近 24 小时确认的信号</p>
        </div>
        <div class="rsi-actions">
          <insight-notification-toggle event="rsi_divergence" />
          <el-button :loading="loading" size="small" @click="refresh">刷新背离</el-button>
        </div>
      </div>
    </template>

    <div class="rsi-strength">
      <span>筛选强度</span>
      <el-radio-group v-model="preset" :disabled="loading" size="small" @change="changePreset">
        <el-radio-button v-for="item in RSI_PRESET_OPTIONS" :key="item.key" :label="item.key">{{ item.label }}</el-radio-button>
      </el-radio-group>
      <span class="rsi-meta">本页强度保存在当前浏览器；钉钉通知强度在“通知设置”中单独保存。</span>
    </div>
    <el-alert class="rsi-method" type="info" :closable="false">
      <template #title>
        RSI({{ radar.rsi_period }}) · 收盘价 · Wilder 平滑 · 拐点左右各 {{ radar.pivot_right }} 根 · 相邻同类拐点间隔 {{ radar.min_bars }}–{{ radar.max_bars }} 根
      </template>
      价格创新高/新低幅度 ≥ {{ radar.min_price_change_percent }}%，RSI 反向变化 ≥ {{ radar.min_rsi_change }} 点；
      顶背离前一个 RSI 拐点 ≥ {{ radar.overbought }}，底背离前一个 RSI 拐点 ≤ {{ radar.oversold }}。
      允许价格与 RSI 拐点前后错开 {{ radar.price_pivot_tolerance }} 根 K 线，按实际价格拐点重验方向和幅度。
      两者均须完成右侧 {{ radar.pivot_right }} 根收盘确认；价格拐点晚一根时，确认也顺延一小时。
    </el-alert>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="rsi-method" />
    <el-alert v-if="radar.failed_count" :title="`${radar.failed_count} 个合约行情暂不可用，本轮结果不完整，下次刷新会重试。`" type="warning" :closable="false" class="rsi-method" />

    <el-radio-group v-model="direction" size="small" class="rsi-filters">
      <el-radio-button label="all">全部（{{ radar.signals.length }}）</el-radio-button>
      <el-radio-button label="bullish">底背离（{{ count('bullish') }}）</el-radio-button>
      <el-radio-button label="bearish">顶背离（{{ count('bearish') }}）</el-radio-button>
    </el-radio-group>

    <el-table v-loading="loading" :data="visibleSignals" stripe size="small">
      <el-table-column label="合约" min-width="130">
        <template #default="{ row }">
          <el-button link type="primary" @click="openChart(row)">{{ row.symbol.replace(/USDT$/, '/USDT') }}</el-button>
        </template>
      </el-table-column>
      <el-table-column label="信号" width="100">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'bullish' ? 'success' : 'danger'">{{ row.label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="价格拐点（前 → 后）" min-width="190" align="right">
        <template #default="{ row }">{{ price(row.previous.price) }} → {{ price(row.current.price) }}</template>
      </el-table-column>
      <el-table-column label="RSI 拐点（前 → 后）" min-width="165" align="right">
        <template #default="{ row }">{{ row.previous.rsi.toFixed(2) }} → {{ row.current.rsi.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="背离幅度" min-width="155" align="right">
        <template #default="{ row }">
          <div>价格 {{ (Math.abs(row.current.price - row.previous.price) / row.previous.price * 100).toFixed(2) }}%</div>
          <div>RSI {{ Math.abs(row.current.rsi - row.previous.rsi).toFixed(2) }} 点</div>
        </template>
      </el-table-column>
      <el-table-column label="最新小时收盘价" min-width="140" align="right">
        <template #default="{ row }">{{ price(row.last_close) }}</template>
      </el-table-column>
      <el-table-column label="最新 RSI" width="100" align="right">
        <template #default="{ row }">{{ row.last_rsi.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="后拐点时间" min-width="175">
        <template #default="{ row }">
          <div>RSI：{{ formatTime(row.current.time) }}</div>
          <div>价格：{{ formatTime(row.current.price_time ?? row.current.time) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="确认时间" min-width="150">
        <template #default="{ row }">{{ formatTime(row.confirmed_at) }}</template>
      </el-table-column>
      <el-table-column label="图表" width="90" fixed="right">
        <template #default="{ row }"><el-button link type="primary" @click="openChart(row)">查看连线</el-button></template>
      </el-table-column>
      <template #empty><el-empty :description="error ? '行情加载失败，请重试' : '近 24 小时没有符合条件的已确认背离'" :image-size="64" /></template>
    </el-table>
    <div class="rsi-meta">
      成功分析 {{ radar.scanned_count }} 个合约 · 更新：{{ formatTime(radar.timestamp) }} · 每分钟检查（行情缓存最长 5 分钟，整点失效）
    </div>

    <el-dialog v-model="chartVisible" :title="`${selected?.symbol || ''} · 1 小时 RSI ${selected?.label || '背离'}`" width="94%" destroy-on-close @opened="renderChart" @closed="disposeChart">
      <p v-if="selected" class="chart-caption">
        价格与 RSI 连线分别对应各自历史拐点，可前后相差一根；信号于 {{ formatTime(selected.confirmed_at) }} 才确认。图表仅含已收盘 K 线。
      </p>
      <el-alert v-if="chartError" :title="chartError" type="error" :closable="false" />
      <div ref="chartElement" v-loading="chartLoading" class="rsi-chart" />
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useStore } from 'vuex'
import * as echarts from 'echarts'
import { marketInsight } from '@/api'
import InsightNotificationToggle from '@/components/InsightNotificationToggle.vue'
import { RSI_PRESET_OPTIONS } from '@/constants/rsiPresets'
import { resolveDisplayTimezone } from '@/utils/datetime'

const emit = defineEmits(['loading-change'])
const store = useStore()
const preset = ref('strict')
const radar = ref({
  signals: [], scanned_count: 0, failed_count: 0, timestamp: null,
  preset: 'strict', preset_label: '严格',
  rsi_period: 14, pivot_right: 5, min_bars: 10, max_bars: 60,
  min_price_change_percent: 0.5, min_rsi_change: 5, overbought: 70, oversold: 30, price_pivot_tolerance: 1
})
const loading = ref(false)
const error = ref('')
const direction = ref('all')
const chartVisible = ref(false)
const chartLoading = ref(false)
const chartError = ref('')
const chartElement = ref(null)
const selected = ref(null)
let detail = null
let chart = null
let timer = null
let requestId = 0
let disposed = false

const visibleSignals = computed(() => radar.value.signals.filter(row => direction.value === 'all' || row.direction === direction.value))
const count = value => radar.value.signals.filter(row => row.direction === value).length
const price = value => Number(value).toLocaleString('en-US', { maximumSignificantDigits: 8 })
const formatTime = value => value ? new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  timeZone: resolveDisplayTimezone(store.getters.displayTimezone)
}).format(new Date(value)) : '-'

async function refresh() {
  if (loading.value || disposed) return
  loading.value = true
  emit('loading-change', true)
  try {
    const data = await marketInsight.getRsiDivergence(preset.value)
    if (disposed) return
    radar.value = data
    if (store.state.currentUser?.id) {
      try { window.localStorage.setItem(`rsi.preset.${store.state.currentUser.id}`, preset.value) } catch (_) { /* 浏览器可能禁用存储 */ }
    }
    error.value = ''
  } catch (_) {
    preset.value = radar.value.preset
    if (!disposed) error.value = radar.value.timestamp
      ? 'RSI 背离刷新失败，当前显示上次结果，请检查更新时间后重试。'
      : 'RSI 背离行情暂不可用，请稍后重试。'
  } finally {
    loading.value = false
    if (!disposed) emit('loading-change', false)
  }
}

function changePreset() {
  chartVisible.value = false
  disposeChart()
  refresh()
}

async function openChart(signal) {
  const id = ++requestId
  selected.value = signal
  detail = null
  chart?.clear()
  chartError.value = ''
  chartVisible.value = true
  chartLoading.value = true
  try {
    const data = await marketInsight.getRsiDivergenceDetail(signal.symbol, radar.value.preset)
    if (id !== requestId || disposed || !chartVisible.value) return
    detail = data
    await nextTick()
    renderChart()
  } catch (_) {
    if (id === requestId && !disposed) chartError.value = '图表加载失败，请关闭后重新打开。'
  } finally {
    if (id === requestId) chartLoading.value = false
  }
}

function renderChart() {
  if (!chartVisible.value || !chartElement.value || !detail || disposed) return
  if (!chart) chart = echarts.init(chartElement.value)
  const candles = detail.candles
  const signal = selected.value
  const times = candles.map(item => String(item.time))
  const color = signal.direction === 'bullish' ? '#12b76a' : '#f04438'
  const line = field => [[signal.previous, signal.current].map(point => ({
    coord: [String(field === 'price' ? (point.price_time ?? point.time) : point.time), point[field]]
  }))]
  const startIndex = Math.max(0, candles.findIndex(item => item.time === signal.previous.time) - 15)
  const endIndex = Math.min(candles.length - 1, candles.findIndex(item => item.time === signal.current.time) + 20)
  const markLine = field => ({
    silent: true, symbol: ['circle', 'circle'], label: { show: false },
    lineStyle: { color, width: 3, type: 'solid' }, data: line(field)
  })
  chart.setOption({
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [{ left: 80, right: 30, top: 25, height: '50%' }, { left: 80, right: 30, top: '65%', height: '23%' }],
    xAxis: [0, 1].map(index => ({
      type: 'category', data: times, gridIndex: index,
      axisLabel: { show: index === 1, formatter: value => formatTime(Number(value)) },
      axisPointer: { label: { formatter: params => formatTime(Number(params.value)) } }
    })),
    yAxis: [
      { scale: true, gridIndex: 0, name: '价格', splitLine: { lineStyle: { color: '#edf0f5' } } },
      { min: 0, max: 100, gridIndex: 1, name: 'RSI(14)', splitLine: { lineStyle: { color: '#edf0f5' } } }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], startValue: times[startIndex], endValue: times[endIndex] },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 20, labelFormatter: (_, value) => formatTime(Number(value)) }
    ],
    series: [
      { name: '小时K线', type: 'candlestick', data: candles.map(item => [item.open, item.close, item.low, item.high]),
        itemStyle: { color: '#12b76a', color0: '#f04438', borderColor: '#12b76a', borderColor0: '#f04438' },
        markLine: markLine('price') },
      { name: 'RSI(14)', type: 'line', xAxisIndex: 1, yAxisIndex: 1,
        data: candles.map(item => item.rsi == null ? null : Number(item.rsi.toFixed(2))), showSymbol: false,
        lineStyle: { color: '#7f56d9', width: 2 }, markLine: {
          ...markLine('rsi'), data: [...line('rsi'), ...[30, 70].map(value => ({
            yAxis: value, lineStyle: { color: '#98a2b3', width: 1, type: 'dashed' }
          }))]
        } }
    ]
  }, true)
  chart.resize()
}

function resizeChart() { chart?.resize() }
function disposeChart() {
  requestId += 1
  chart?.dispose()
  chart = null
  detail = null
}

defineExpose({ refresh })
onMounted(() => {
  try {
    const saved = window.localStorage.getItem(`rsi.preset.${store.state.currentUser?.id}`)
    if (RSI_PRESET_OPTIONS.some(item => item.key === saved)) preset.value = saved
  } catch (_) { /* 浏览器可能禁用存储 */ }
  refresh()
  timer = window.setInterval(refresh, 60000)
  window.addEventListener('resize', resizeChart)
})
onUnmounted(() => {
  disposed = true
  window.clearInterval(timer)
  window.removeEventListener('resize', resizeChart)
  disposeChart()
})
</script>

<style scoped>
.rsi-card { margin-bottom: 18px; border-radius: 12px; border-top: 3px solid #7f56d9; }
.rsi-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.rsi-header strong { font-size: 16px; }
.rsi-actions, .rsi-strength { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.rsi-strength { margin-bottom: 14px; }
.rsi-header p, .rsi-meta, .chart-caption { color: #667085; font-size: 12px; line-height: 1.7; }
.rsi-header p { margin: 5px 0 0; }
.rsi-method, .rsi-filters { margin-bottom: 14px; }
.rsi-meta { margin-top: 12px; }
.rsi-chart { width: 100%; height: 540px; }
@media (max-width: 768px) {
  .rsi-header { align-items: flex-start; flex-direction: column; }
}
</style>
