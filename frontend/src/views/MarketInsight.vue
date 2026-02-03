<template>
  <div class="market-insight">
    <el-page-header @back="$router.back()" :content="pageTitle" class="page-header" />
    
    <!-- 市场总览 -->
    <el-card class="overview-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>市场总览</span>
          <el-button 
            :icon="Refresh" 
            circle 
            size="small" 
            @click="refreshData"
            :loading="loading"
          />
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">24H总成交量</div>
            <div class="stat-value">${{ formatNumber(overview.total_volume_24h) }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">总市值</div>
            <div class="stat-value">${{ formatNumber(overview.total_market_cap) }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">BTC市值占比</div>
            <div class="stat-value">{{ overview.btc_dominance?.toFixed(2) }}%</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">活跃币种</div>
            <div class="stat-value">{{ overview.active_cryptocurrencies }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- GPT-5.1 AI 分析 -->
    <el-card v-if="aiAnalysis" class="ai-analysis-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>🤖 GPT-5.1 深度市场解析</span>
          <el-tag size="small" type="success" effect="dark">AI Powered</el-tag>
        </div>
      </template>
      <div class="ai-content" v-html="renderMarkdown(aiAnalysis)"></div>
    </el-card>

    <!-- K 线图 -->
    <el-card class="kline-card" shadow="hover">
      <KlineChart :symbol="currentChartSymbol" />
    </el-card>

    <!-- 交易信号 -->
    <el-card v-if="signals.length > 0" class="signals-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>🎯 交易信号</span>
          <el-tag size="small" type="info">基于市场情绪和价格分析</el-tag>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col 
          v-for="signal in signals" 
          :key="signal.symbol"
          :xs="24" :sm="12" :md="8"
        >
          <div class="signal-item" :class="`signal-${signal.signal_type}`">
            <div class="signal-header">
              <span class="signal-symbol">{{ formatSymbol(signal.symbol) }}</span>
              <el-tag 
                :type="getSignalTagType(signal.signal_type)"
                size="small"
              >
                {{ getSignalLabel(signal.signal_type) }}
              </el-tag>
            </div>
            <el-progress 
              :percentage="signal.strength" 
              :color="getSignalColor(signal.signal_type)"
              :show-text="false"
            />
            <div class="signal-strength">信号强度: {{ signal.strength.toFixed(0) }}</div>
            <div class="signal-reasons">
              <div v-for="(reason, idx) in signal.reasons" :key="idx" class="reason">
                • {{ reason }}
              </div>
            </div>
            <div v-if="signal.suggested_entry" class="signal-prices">
              <div class="price-item">
                <span class="label">入场:</span>
                <span class="value">${{ signal.suggested_entry.toFixed(2) }}</span>
              </div>
              <div class="price-item">
                <span class="label">止损:</span>
                <span class="value danger">${{ signal.suggested_stop_loss?.toFixed(2) }}</span>
              </div>
              <div class="price-item">
                <span class="label">止盈:</span>
                <span class="value success">${{ signal.suggested_take_profit?.toFixed(2) }}</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 市场情绪 & 宏观 -->
    <el-row :gutter="16" class="sentiment-rankings">
      <!-- 恐惧贪婪指数 -->
      <el-col :xs="24" :md="12">
        <el-card class="sentiment-macro-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>😱 恐惧与贪婪指数</span>
              <el-tag v-if="fearGreedIndex" :type="getFngTagType(fearGreedIndex.value_classification)">
                {{ fearGreedIndex.value_classification }} ({{ fearGreedIndex.value }})
              </el-tag>
            </div>
          </template>
          <div class="fng-container">
            <div class="fng-gauge">
              <div class="fng-value" :style="{ color: getFngColor(fearGreedIndex?.value) }">
                {{ fearGreedIndex?.value || '--' }}
              </div>
              <div class="fng-label">当前指数</div>
            </div>
            <div class="fng-history">
              <div v-for="(item, idx) in fearGreedHistory.slice(0, 5)" :key="idx" class="history-item">
                <span class="date">{{ item.timestamp }}</span>
                <span class="val" :style="{ color: getFngColor(item.value) }">{{ item.value }}</span>
                <span class="desc">{{ item.value_classification }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 彩虹图价格带 -->
      <el-col :xs="24" :md="12">
        <el-card class="sentiment-macro-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>🌈 BTC 彩虹图指标</span>
              <el-tag v-if="btcCurrentPrice" type="info" size="small">
                BTC: ${{ formatNumber(btcCurrentPrice) }}
              </el-tag>
            </div>
          </template>
          <div class="rainbow-visual-container">
            <div class="rainbow-bar">
              <div 
                v-for="band in [...rainbowBands].reverse()" 
                :key="band.name" 
                class="bar-segment"
                :style="{ backgroundColor: band.color, flex: 1 }"
                :title="band.name"
              ></div>
              <div 
                v-if="rainbowIndicatorPos >= 0" 
                class="price-indicator" 
                :style="{ left: rainbowIndicatorPos + '%' }"
              >
                <div class="indicator-arrow"></div>
                <div class="indicator-label">当前价</div>
              </div>
            </div>
            <div class="rainbow-bands-list">
              <div 
                v-for="band in rainbowBands" 
                :key="band.name" 
                class="rainbow-band"
                :style="{ backgroundColor: band.color + '22', borderLeft: '4px solid ' + band.color }"
              >
                <span class="band-name">{{ band.name }}</span>
                <span class="band-price">${{ formatNumber(band.price) }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 市场情绪细节 -->
    <el-card class="sentiment-card" shadow="hover">
      <template #header>
        <span>💭 合约市场统计</span>
      </template>
      <el-row :gutter="16">
        <el-col 
          v-for="item in sentiment" 
          :key="item.symbol"
          :xs="24" :sm="12" :md="8"
        >
          <div class="sentiment-item">
            <div class="sentiment-header">
              <span class="symbol">{{ formatSymbol(item.symbol) }}</span>
              <el-tag 
                :type="getSentimentTagType(item.sentiment_score)"
                size="small"
              >
                {{ getSentimentLabel(item.sentiment_score) }}
              </el-tag>
            </div>
            <div class="sentiment-data">
              <div class="data-row">
                <span class="label">资金费率:</span>
                <span :class="getFundingRateClass(item.funding_rate)">
                  {{ (item.funding_rate * 100).toFixed(4) }}%
                </span>
              </div>
              <div class="data-row">
                <span class="label">多空比:</span>
                <span :class="getLongShortRatioClass(item.long_short_ratio)">
                  {{ item.long_short_ratio?.toFixed(2) }}
                </span>
              </div>
              <div class="data-row" v-if="item.open_interest">
                <span class="label">未平仓合约:</span>
                <span>{{ formatNumber(item.open_interest) }}</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 排行榜 -->
    <el-row :gutter="16" class="rankings">
      <!-- 涨幅榜 -->
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>
            <span>📈 合约涨幅榜 (24H)</span>
          </template>
          <el-table 
            :data="topGainers" 
            :show-header="false" 
            size="small"
            @row-click="selectSymbol"
            row-class-name="clickable-row"
          >
            <el-table-column width="150">
              <template #default="{ row }">
                <span class="symbol-name">{{ formatSymbol(row.symbol) }}</span>
              </template>
            </el-table-column>
            <el-table-column align="right">
              <template #default="{ row }">
                <span class="price">${{ row.last_price.toFixed(row.last_price < 1 ? 4 : 2) }}</span>
              </template>
            </el-table-column>
            <el-table-column width="100" align="right">
              <template #default="{ row }">
                <el-tag type="success" size="small">
                  +{{ row.price_change_percent_24h.toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 跌幅榜 -->
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>
            <span>📉 合约跌幅榜 (24H)</span>
          </template>
          <el-table 
            :data="topLosers" 
            :show-header="false" 
            size="small"
            @row-click="selectSymbol"
            row-class-name="clickable-row"
          >
            <el-table-column width="150">
              <template #default="{ row }">
                <span class="symbol-name">{{ formatSymbol(row.symbol) }}</span>
              </template>
            </el-table-column>
            <el-table-column align="right">
              <template #default="{ row }">
                <span class="price">${{ row.last_price.toFixed(row.last_price < 1 ? 4 : 2) }}</span>
              </template>
            </el-table-column>
            <el-table-column width="100" align="right">
              <template #default="{ row }">
                <el-tag type="danger" size="small">
                  {{ row.price_change_percent_24h.toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 成交量榜 -->
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>
            <span>💰 合约成交量榜</span>
          </template>
          <el-table 
            :data="topVolume" 
            :show-header="false" 
            size="small"
            @row-click="selectSymbol"
            row-class-name="clickable-row"
          >
            <el-table-column width="150">
              <template #default="{ row }">
                <span class="symbol-name">{{ formatSymbol(row.symbol) }}</span>
              </template>
            </el-table-column>
            <el-table-column align="right">
              <template #default="{ row }">
                <span class="volume">${{ formatNumber(row.volume_24h) }}</span>
              </template>
            </el-table-column>
            <el-table-column width="100" align="right">
              <template #default="{ row }">
                <el-tag 
                  :type="row.price_change_percent_24h > 0 ? 'success' : 'danger'" 
                  size="small"
                >
                  {{ row.price_change_percent_24h > 0 ? '+' : '' }}{{ row.price_change_percent_24h.toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 自选币种 -->
    <el-card v-if="watchlist.length > 0" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>⭐ 自选币种</span>
          <el-button size="small" @click="showWatchlistDialog = true">
            管理自选
          </el-button>
        </div>
      </template>
      <el-table 
        :data="watchlist" 
        stripe
        @row-click="selectSymbol"
        row-class-name="clickable-row"
      >
        <el-table-column label="币种" width="120">
          <template #default="{ row }">
            <strong>{{ formatSymbol(row.symbol) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="最新价" align="right">
          <template #default="{ row }">
            ${{ row.last_price.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="24H涨跌" align="right">
          <template #default="{ row }">
            <el-tag 
              :type="row.price_change_percent_24h > 0 ? 'success' : 'danger'"
              size="small"
            >
              {{ row.price_change_percent_24h > 0 ? '+' : '' }}{{ row.price_change_percent_24h.toFixed(2) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="24H最高" align="right">
          <template #default="{ row }">
            ${{ row.high_24h.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="24H最低" align="right">
          <template #default="{ row }">
            ${{ row.low_24h.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="24H成交量" align="right">
          <template #default="{ row }">
            ${{ formatNumber(row.volume_24h) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 管理自选对话框 -->
    <el-dialog 
      v-model="showWatchlistDialog" 
      title="管理自选币种"
      width="500px"
    >
      <el-input
        v-model="newWatchSymbol"
        placeholder="输入币种符号，如: BTCUSDT"
        @keyup.enter="addToWatchlist"
      >
        <template #append>
          <el-button @click="addToWatchlist">添加</el-button>
        </template>
      </el-input>
      <div class="watchlist-items">
        <el-tag
          v-for="symbol in userWatchlist"
          :key="symbol"
          closable
          @close="removeFromWatchlist(symbol)"
          style="margin: 5px"
        >
          {{ formatSymbol(symbol) }}
        </el-tag>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { marketInsight } from '@/api'
import { ElMessage } from 'element-plus'
import KlineChart from '@/components/KlineChart.vue'

const pageTitle = ref('市场洞察')
const loading = ref(false)

// 数据
const overview = ref({})
const topGainers = ref([])
const topLosers = ref([])
const topVolume = ref([])
const watchlist = ref([])
const sentiment = ref([])
const fearGreedIndex = ref(null)
const fearGreedHistory = ref([])
const rainbowBands = ref([])
const signals = ref([])
const aiAnalysis = ref('')
const currentChartSymbol = ref('BTCUSDT')

// 计算当前 BTC 在彩虹图中的位置
const btcCurrentPrice = computed(() => {
  const btcInWatch = watchlist.value.find(i => i.symbol === 'BTCUSDT')
  if (btcInWatch) return btcInWatch.last_price
  return 0
})

const rainbowIndicatorPos = computed(() => {
  if (!btcCurrentPrice.value || rainbowBands.value.length === 0) return -1
  
  const price = btcCurrentPrice.value
  const bands = [...rainbowBands.value].reverse() // 从低价到高价排序
  
  const minPrice = bands[0].price * 0.8
  const maxPrice = bands[bands.length - 1].price * 1.2
  
  if (price <= minPrice) return 0
  if (price >= maxPrice) return 100
  
  // 简单的对数比例计算（彩虹图是基于对数增长的）
  const pos = (Math.log10(price) - Math.log10(minPrice)) / (Math.log10(maxPrice) - Math.log10(minPrice))
  return pos * 100
})

// 自选管理
const showWatchlistDialog = ref(false)
const newWatchSymbol = ref('')
const userWatchlist = ref(['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT'])

// 自动刷新定时器
let refreshTimer = null

onMounted(() => {
  loadData()
  // 每30秒自动刷新
  refreshTimer = setInterval(() => {
    loadData(true)
  }, 30000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})

async function loadData(silent = false) {
  if (!silent) {
    loading.value = true
  }
  
  try {
    const watchlistParam = userWatchlist.value.join(',')
    const response = await marketInsight.getDashboard({ watchlist: watchlistParam })
    
    overview.value = response.overview
    topGainers.value = response.top_gainers
    topLosers.value = response.top_losers
    topVolume.value = response.top_volume
    watchlist.value = response.watchlist
    sentiment.value = response.sentiment
    fearGreedIndex.value = response.fear_greed_index
    fearGreedHistory.value = response.fear_greed_history
    rainbowBands.value = response.rainbow_bands
    signals.value = response.signals
    aiAnalysis.value = response.ai_analysis
    
    if (!silent) {
      ElMessage.success('数据加载成功')
    }
  } catch (error) {
    console.error('Failed to load market insight data:', error)
    if (!silent) {
      ElMessage.error('数据加载失败')
    }
  } finally {
    loading.value = false
  }
}

function refreshData() {
  loadData()
}

function selectSymbol(row) {
  currentChartSymbol.value = row.symbol
  ElMessage.info(`切换行情至: ${formatSymbol(row.symbol)}`)
  // 滚动到 K 线图位置
  const el = document.querySelector('.kline-card')
  if (el) {
    el.scrollIntoView({ behavior: 'smooth' })
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  // 极简 Markdown 转换
  return text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*)\*/gim, '<em>$1</em>')
    .replace(/\n/gim, '<br>')
}

function formatSymbol(symbol) {
  return symbol.replace('USDT', '')
}

function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B'
  if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M'
  if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K'
  return num.toFixed(2)
}

function getSentimentLabel(score) {
  const labels = {
    extreme_fear: '极度恐慌',
    fear: '恐慌',
    neutral: '中性',
    greed: '贪婪',
    extreme_greed: '极度贪婪'
  }
  return labels[score] || '未知'
}

function getSentimentTagType(score) {
  const types = {
    extreme_fear: 'danger',
    fear: 'warning',
    neutral: 'info',
    greed: 'success',
    extreme_greed: 'success'
  }
  return types[score] || 'info'
}

function getFundingRateClass(rate) {
  if (!rate) return ''
  return rate > 0 ? 'positive' : 'negative'
}

function getLongShortRatioClass(ratio) {
  if (!ratio) return ''
  return ratio > 1 ? 'positive' : 'negative'
}

function getSignalLabel(type) {
  const labels = {
    long: '做多',
    short: '做空',
    neutral: '观望'
  }
  return labels[type] || type
}

function getSignalTagType(type) {
  const types = {
    long: 'success',
    short: 'danger',
    neutral: 'info'
  }
  return types[type] || 'info'
}

function getSignalColor(type) {
  const colors = {
    long: '#67C23A',
    short: '#F56C6C',
    neutral: '#909399'
  }
  return colors[type] || '#909399'
}

function getFngTagType(label) {
  if (!label) return 'info'
  const l = label.toLowerCase()
  if (l.includes('extreme greed')) return 'success'
  if (l.includes('greed')) return 'warning'
  if (l.includes('fear')) return 'danger'
  return 'info'
}

function getFngColor(val) {
  if (!val) return '#909399'
  if (val >= 75) return '#67C23A' // Extreme Greed
  if (val >= 55) return '#E6A23C' // Greed
  if (val >= 45) return '#909399' // Neutral
  if (val >= 25) return '#F56C6C' // Fear
  return '#FF0000' // Extreme Fear
}

function addToWatchlist() {
  const symbol = newWatchSymbol.value.trim().toUpperCase()
  if (!symbol) {
    ElMessage.warning('请输入币种符号')
    return
  }
  
  if (userWatchlist.value.includes(symbol)) {
    ElMessage.warning('该币种已在自选列表中')
    return
  }
  
  userWatchlist.value.push(symbol)
  newWatchSymbol.value = ''
  ElMessage.success('添加成功')
  loadData(true)
}

function removeFromWatchlist(symbol) {
  const index = userWatchlist.value.indexOf(symbol)
  if (index > -1) {
    userWatchlist.value.splice(index, 1)
    ElMessage.success('移除成功')
    loadData(true)
  }
}
</script>

<style scoped>
.market-insight {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.overview-card {
  margin-bottom: 20px;
}

.kline-card {
  margin-bottom: 20px;
  padding: 0;
}

.ai-analysis-card {
  margin-bottom: 20px;
  background-color: #f0f9eb;
  border-left: 5px solid #67c23a;
}

.ai-content {
  line-height: 1.6;
  color: #606266;
  font-size: 15px;
}

.ai-content h3 {
  margin-top: 0;
  color: #303133;
}

.stat-item {
  text-align: center;
  padding: 10px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

.signals-card {
  margin-bottom: 20px;
}

.signal-item {
  padding: 15px;
  border-radius: 8px;
  background: #f5f7fa;
  height: 100%;
}

.signal-item.signal-long {
  border-left: 4px solid #67C23A;
}

.signal-item.signal-short {
  border-left: 4px solid #F56C6C;
}

.signal-item.signal-neutral {
  border-left: 4px solid #909399;
}

.signal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.signal-symbol {
  font-size: 16px;
  font-weight: bold;
}

.signal-strength {
  margin: 10px 0;
  font-size: 12px;
  color: #606266;
}

.signal-reasons {
  margin: 10px 0;
  font-size: 13px;
  color: #606266;
}

.reason {
  margin: 5px 0;
}

.signal-prices {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #dcdfe6;
}

.price-item {
  display: flex;
  justify-content: space-between;
  margin: 5px 0;
  font-size: 13px;
}

.price-item .label {
  color: #909399;
}

.price-item .value.success {
  color: #67C23A;
  font-weight: bold;
}

.price-item .value.danger {
  color: #F56C6C;
  font-weight: bold;
}

.sentiment-card {
  margin-bottom: 20px;
}

.sentiment-item {
  padding: 15px;
  border-radius: 8px;
  background: #f5f7fa;
}

.sentiment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.sentiment-header .symbol {
  font-size: 16px;
  font-weight: bold;
}

.sentiment-data .data-row {
  display: flex;
  justify-content: space-between;
  margin: 8px 0;
  font-size: 14px;
}

.sentiment-data .label {
  color: #909399;
}

.positive {
  color: #67C23A;
  font-weight: bold;
}

.negative {
  color: #F56C6C;
  font-weight: bold;
}

.rankings {
  margin-bottom: 20px;
}

.sentiment-rankings {
  margin-bottom: 20px;
}

.sentiment-macro-card {
  height: 100%;
}

.fng-container {
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 10px 0;
}

.fng-gauge {
  text-align: center;
}

.fng-value {
  font-size: 48px;
  font-weight: bold;
}

.fng-label {
  color: #909399;
  font-size: 14px;
}

.fng-history {
  border-left: 1px solid #EBEEF5;
  padding-left: 20px;
}

.history-item {
  display: flex;
  justify-content: space-between;
  width: 200px;
  margin-bottom: 8px;
  font-size: 13px;
}

.history-item .date { color: #909399; }
.history-item .val { font-weight: bold; width: 30px; text-align: right; }
.history-item .desc { width: 100px; text-align: right; }

.rainbow-visual-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.rainbow-bar {
  height: 12px;
  display: flex;
  position: relative;
  border-radius: 6px;
  overflow: visible;
  margin: 30px 10px 10px 10px;
}

.bar-segment:first-child { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
.bar-segment:last-child { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }

.price-indicator {
  position: absolute;
  top: -25px;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  z-index: 10;
  transition: left 0.5s ease;
}

.indicator-arrow {
  width: 0;
  height: 0;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 8px solid #303133;
  margin-top: 2px;
}

.indicator-label {
  background: #303133;
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  white-space: nowrap;
}

.rainbow-bands-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rainbow-band {
  display: flex;
  justify-content: space-between;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 13px;
}

.band-name { font-weight: 500; }
.band-price { font-family: monospace; }

.symbol-name {
  font-weight: bold;
  color: #303133;
}

.clickable-row {
  cursor: pointer;
  transition: background-color 0.2s;
}

.clickable-row:hover {
  background-color: #f5f7fa !important;
}

.price {
  color: #606266;
}

.volume {
  color: #606266;
  font-size: 13px;
}

.watchlist-items {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #dcdfe6;
}
</style>
