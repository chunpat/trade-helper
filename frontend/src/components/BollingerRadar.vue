<template>
  <el-card shadow="hover" class="boll-card">
    <template #header>
      <div class="boll-header">
        <div>
          <strong>BOLL 三周期轨外提醒</strong>
          <p>24H 成交额 ≥ 1 亿 USDT · 4h / 1h / 15m 全部高于上轨或全部低于下轨</p>
        </div>
        <el-button size="small" :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </template>
    <el-alert type="info" :closable="false" class="boll-note"
      title="BOLL(24,2)，每分钟检测一次，使用 15m、1h 和 4h 各自最新已收盘的 K 线。管理员可在“风控配置 → 钉钉通知”启用提醒，同币同方向冷却 60 分钟。" />
    <el-alert v-if="error" type="error" :closable="false" :title="error" class="boll-note" />
    <el-alert v-if="data.failed_count" type="warning" :closable="false"
      :title="`${data.failed_count} 个合约行情不完整，将在下次检查时重试。`" class="boll-note" />
    <el-table v-loading="loading" :data="data.signals" stripe size="small">
      <el-table-column prop="symbol" label="合约" min-width="130" />
      <el-table-column label="方向" min-width="130">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'above_upper' ? 'success' : 'danger'">
            {{ row.direction === 'above_upper' ? '全部高于上轨' : '全部低于下轨' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="24H 成交额" min-width="140" align="right">
        <template #default="{ row }">{{ (row.quote_volume_24h / 1e8).toFixed(2) }} 亿 USDT</template>
      </el-table-column>
      <el-table-column v-for="interval in intervals" :key="interval" :label="`${interval} 收盘价 / 轨道值`" min-width="200" align="right">
        <template #default="{ row }">
          <template v-for="band in row.bands.filter(item => item.interval === interval)" :key="band.interval">
            <div>{{ price(band.close) }} / {{ price(row.direction === 'above_upper' ? band.upper : band.lower) }}</div>
            <div class="boll-time">收盘于 {{ formatTime(band.closed_at) }}</div>
          </template>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :description="error ? '行情加载失败，请重试' : '本轮没有满足三个周期同向轨外条件的合约'" :image-size="64" />
      </template>
    </el-table>
    <p class="boll-meta">成功分析 {{ data.scanned_count }} 个达标合约 · 检查时间：{{ formatTime(data.timestamp) }} · 每分钟检测一次</p>
  </el-card>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useStore } from 'vuex'
import { marketInsight } from '@/api'
import { formatDateTime } from '@/utils/datetime'

const emit = defineEmits(['loading-change'])
const store = useStore()
const intervals = ['4h', '1h', '15m']
const data = ref({ signals: [], scanned_count: 0, failed_count: 0, timestamp: null })
const loading = ref(false)
const error = ref('')
let timer = null
let disposed = false
const price = value => Number(value).toLocaleString('en-US', { maximumSignificantDigits: 8 })
const formatTime = value => value ? formatDateTime(value, store.getters.displayTimezone) : '-'

async function refresh() {
  if (loading.value || disposed) return
  loading.value = true
  emit('loading-change', true)
  try {
    const result = await marketInsight.getBollingerRadar()
    if (disposed) return
    data.value = result
    error.value = ''
  } catch (_) {
    if (!disposed) error.value = data.value.timestamp
      ? 'BOLL 行情刷新失败，当前为上次结果，请注意检查时间。'
      : 'BOLL 行情暂不可用，请稍后重试。'
  } finally {
    loading.value = false
    if (!disposed) emit('loading-change', false)
  }
}

defineExpose({ refresh })
onMounted(() => {
  refresh()
  // 页面与后台均按一分钟频率检查，K线仍使用各周期已收盘数据。
  timer = window.setInterval(refresh, 60000)
})
onUnmounted(() => {
  disposed = true
  window.clearInterval(timer)
})
</script>

<style scoped>
.boll-card { margin-bottom: 18px; border-radius: 12px; border-top: 3px solid #409eff; }
.boll-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.boll-header strong { font-size: 16px; }
.boll-header p, .boll-meta, .boll-time { color: #667085; font-size: 12px; line-height: 1.7; }
.boll-header p { margin: 5px 0 0; }
.boll-note { margin-bottom: 14px; }
.boll-meta { margin: 12px 0 0; }
@media (max-width: 768px) { .boll-header { align-items: flex-start; flex-direction: column; } }
</style>
