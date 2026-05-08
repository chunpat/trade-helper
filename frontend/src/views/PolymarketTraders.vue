<template>
  <div class="polymarket-traders-page">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">Polymarket Copy Trading</p>
        <h1>交易员池与候选缓存</h1>
        <p class="hero-copy">
          后端会周期抓取候选交易员并缓存分析结果。这里可以切换榜单池、查看缓存状态、强制刷新，以及进入独立详情页查看更完整的可跟单画像。
        </p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" :icon="Refresh" :loading="refreshingPool" @click="refreshCurrentPool">
          强制刷新当前池
        </el-button>
        <el-button plain :loading="loadingStatus" @click="loadCacheStatus">
          刷新缓存状态
        </el-button>
      </div>
    </section>

    <el-row :gutter="16" class="status-grid">
      <el-col :xs="24" :md="14">
        <el-card shadow="hover" class="control-card">
          <template #header>
            <div class="card-header">
              <span>候选池参数</span>
              <el-tag size="small" type="info">读缓存优先</el-tag>
            </div>
          </template>
          <el-form label-position="top" class="pool-form">
            <el-row :gutter="12">
              <el-col :xs="24" :sm="12" :md="6">
                <el-form-item label="分类">
                  <el-select v-model="filters.category" style="width: 100%">
                    <el-option v-for="option in categoryOptions" :key="option" :label="option" :value="option" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12" :md="6">
                <el-form-item label="周期">
                  <el-select v-model="filters.timePeriod" style="width: 100%">
                    <el-option v-for="option in timePeriodOptions" :key="option" :label="option" :value="option" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12" :md="6">
                <el-form-item label="排序">
                  <el-select v-model="filters.orderBy" style="width: 100%">
                    <el-option v-for="option in orderByOptions" :key="option" :label="option" :value="option" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12" :md="6">
                <el-form-item label="数量">
                  <el-input-number v-model="filters.limit" :min="5" :max="50" :step="5" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="12">
              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="最小近30天成交额 (USDC)">
                  <el-input-number
                    v-model="filters.minVolumeUsd"
                    :min="0"
                    :step="500"
                    :controls-position="'right'"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="最小可跟单评分">
                  <el-input-number
                    v-model="filters.minFollowabilityScore"
                    :min="0"
                    :max="100"
                    :step="5"
                    :controls-position="'right'"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="最小近30天已实现收益 (USDC)">
                  <el-input-number
                    v-model="filters.minRealizedPnlUsd"
                    :step="100"
                    :controls-position="'right'"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item label="手工钱包分析（可选）">
              <el-input
                v-model="filters.wallets"
                type="textarea"
                :rows="2"
                placeholder="输入一个或多个钱包地址，逗号分隔；填写后将直接走实时分析，不读候选池缓存"
              />
            </el-form-item>

            <div class="pool-form-actions">
              <el-button type="primary" :loading="loadingTraders" @click="loadTraders()">加载交易员池</el-button>
              <el-button @click="resetBaseFilters">恢复默认基础筛选</el-button>
              <el-button @click="resetWallets">清空钱包筛选</el-button>
            </div>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="10">
        <el-card shadow="hover" class="status-card">
          <template #header>
            <div class="card-header">
              <span>缓存任务状态</span>
              <el-tag :type="cacheStatus.running ? 'success' : 'danger'" size="small">
                {{ cacheStatus.running ? '运行中' : '已停止' }}
              </el-tag>
            </div>
          </template>

          <div class="status-metrics">
            <div class="metric-item">
              <span class="metric-label">后台刷新间隔</span>
              <strong>{{ cacheStatus.interval_seconds || '-' }} 秒</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">缓存 TTL</span>
              <strong>{{ cacheStatus.ttl_seconds || '-' }} 秒</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">默认池数量</span>
              <strong>{{ cacheStatus.default_pools?.length || 0 }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">已缓存池数量</span>
              <strong>{{ cacheStatus.pools?.length || 0 }}</strong>
            </div>
          </div>

          <div v-if="currentPoolStatus" class="current-pool-box">
            <div class="current-pool-title">当前池</div>
            <div class="current-pool-meta">{{ currentPoolStatus.cache_key }}</div>
            <div class="current-pool-row">
              <span>最近刷新</span>
              <strong>{{ formatDateTime(currentPoolStatus.last_refresh_at) }}</strong>
            </div>
            <div class="current-pool-row">
              <span>过期时间</span>
              <strong>{{ formatDateTime(currentPoolStatus.expires_at) }}</strong>
            </div>
            <div class="current-pool-row">
              <span>状态</span>
              <el-tag :type="currentPoolStatus.is_stale ? 'warning' : 'success'" size="small">
                {{ currentPoolStatus.is_stale ? '已过期' : '可用' }}
              </el-tag>
            </div>
            <div class="current-pool-row">
              <span>候选数量</span>
              <strong>{{ currentPoolStatus.trader_count }}</strong>
            </div>
            <div v-if="currentPoolStatus.last_error" class="error-note">
              最近错误：{{ currentPoolStatus.last_error }}
            </div>
          </div>
          <el-empty v-else description="当前参数对应的缓存池还没有生成" :image-size="72" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" class="pool-list-card">
      <template #header>
        <div class="card-header">
          <span>缓存池列表</span>
          <el-tag size="small" type="info">{{ cacheStatus.pools?.length || 0 }} 个缓存池</el-tag>
        </div>
      </template>
      <el-table :data="cacheStatus.pools || []" size="small" max-height="280">
        <el-table-column prop="cache_key" label="缓存键" min-width="220" />
        <el-table-column prop="trader_count" label="候选数" width="90" align="right" />
        <el-table-column label="最后刷新" min-width="160">
          <template #default="scope">
            {{ formatDateTime(scope.row.last_refresh_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.is_stale ? 'warning' : 'success'" size="small">
              {{ scope.row.is_stale ? '已过期' : '可用' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="hover" class="trader-table-card">
      <template #header>
        <div class="card-header">
          <span>交易员候选池</span>
          <div class="header-right-actions">
            <el-tag size="small" type="info">{{ filteredTraders.length }} / {{ traders.length }} 位交易员</el-tag>
            <el-switch v-model="filters.useCache" active-text="优先读缓存" inactive-text="实时拉取" />
          </div>
        </div>
      </template>

      <el-table :data="filteredTraders" stripe v-loading="loadingTraders" class="trader-table">
        <el-table-column label="交易员" min-width="220">
          <template #default="scope">
            <div class="trader-cell">
              <el-avatar :size="40" :src="scope.row.profile_image || undefined">
                {{ getAvatarFallback(scope.row) }}
              </el-avatar>
              <div>
                <div class="trader-name-row">
                  <strong>{{ scope.row.name || scope.row.pseudonym || shortenWallet(scope.row.wallet_address) }}</strong>
                  <el-tag v-if="scope.row.verified_badge" size="small" type="success">认证</el-tag>
                </div>
                <div class="trader-wallet">{{ shortenWallet(scope.row.wallet_address) }}</div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="榜单" width="130">
          <template #default="scope">
            <div v-if="scope.row.leaderboard">
              <div>#{{ scope.row.leaderboard.rank || '-' }}</div>
              <div class="minor-text">{{ scope.row.leaderboard.time_period || filters.timePeriod }}</div>
            </div>
            <span v-else class="minor-text">自定义</span>
          </template>
        </el-table-column>

        <el-table-column label="近30天成交" width="140" align="right">
          <template #default="scope">
            {{ scope.row.trade_count_30d }} 笔
          </template>
        </el-table-column>

        <el-table-column label="近30天成交额" width="160" align="right">
          <template #default="scope">
            {{ formatMoney(scope.row.volume_usdc_30d) }}
          </template>
        </el-table-column>

        <el-table-column label="近30天已实现收益" width="170" align="right">
          <template #default="scope">
            <span
              :class="[
                'pnl-value',
                Number(scope.row.realized_pnl_30d || 0) > 0 ? 'positive' : '',
                Number(scope.row.realized_pnl_30d || 0) < 0 ? 'negative' : ''
              ]"
            >
              {{ formatMoney(scope.row.realized_pnl_30d) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="平仓胜率" width="120" align="right">
          <template #default="scope">
            {{ formatWinRate(scope.row.win_rate_30d) }}
          </template>
        </el-table-column>

        <el-table-column label="交易风格" width="120">
          <template #default="scope">
            <el-tag :type="getStyleTagType(scope.row.trader_style)" size="small">
              {{ formatTraderStyle(scope.row.trader_style) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="可跟单评分" width="180">
          <template #default="scope">
            <div class="score-cell">
              <el-progress
                :percentage="Math.round(scope.row.followability.score)"
                :stroke-width="10"
                :show-text="false"
                :color="getFollowabilityColor(scope.row.followability.score)"
              />
              <div class="score-meta">
                <strong>{{ scope.row.followability.score.toFixed(0) }}</strong>
                <span>{{ formatVerdict(scope.row.followability.verdict) }}</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="机器人风险" width="110">
          <template #default="scope">
            <el-tag :type="scope.row.followability.likely_bot ? 'danger' : 'success'" size="small">
              {{ scope.row.followability.likely_bot ? '疑似机器人' : '偏人工' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="120" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="openTraderDetail(scope.row)">进入详情页</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { polymarket } from '@/api'
import { formatDateTime as formatDisplayDateTime } from '@/utils/datetime'
import {
  formatPolymarketMoney,
  formatPolymarketNumber,
  formatPolymarketPercent,
  formatPolymarketTraderStyle,
  formatPolymarketVerdict,
  formatPolymarketWinRate,
  getPolymarketAvatarFallback,
  getPolymarketFollowabilityColor,
  getPolymarketStyleTagType,
  shortenPolymarketWallet
} from '@/utils/polymarket'

const categoryOptions = ['OVERALL', 'POLITICS', 'SPORTS', 'CRYPTO', 'CULTURE', 'MENTIONS', 'WEATHER', 'ECONOMICS', 'TECH', 'FINANCE']
const timePeriodOptions = ['DAY', 'WEEK', 'MONTH', 'ALL']
const orderByOptions = ['PNL', 'VOL']
const DEFAULT_MIN_VOLUME_USD = 1000
const DEFAULT_MIN_FOLLOWABILITY_SCORE = 60
const DEFAULT_MIN_REALIZED_PNL_USD = 0

export default {
  name: 'PolymarketTraders',
  components: {
    Refresh
  },
  setup() {
    const router = useRouter()
    const loadingTraders = ref(false)
    const loadingStatus = ref(false)
    const refreshingPool = ref(false)
    const traders = ref([])
    const cacheStatus = reactive({
      running: false,
      interval_seconds: 0,
      ttl_seconds: 0,
      default_pools: [],
      pools: []
    })
    const filters = reactive({
      category: 'OVERALL',
      timePeriod: 'WEEK',
      orderBy: 'PNL',
      limit: 20,
      minVolumeUsd: DEFAULT_MIN_VOLUME_USD,
      minFollowabilityScore: DEFAULT_MIN_FOLLOWABILITY_SCORE,
      minRealizedPnlUsd: DEFAULT_MIN_REALIZED_PNL_USD,
      wallets: '',
      useCache: true
    })

    const currentCacheKey = computed(() => `${filters.category}:${filters.timePeriod}:${filters.orderBy}:${filters.limit}`)
    const filteredTraders = computed(() => {
      const volumeThreshold = Number(filters.minVolumeUsd || 0)
      const scoreThreshold = Number(filters.minFollowabilityScore || 0)
      const pnlThreshold = Number(filters.minRealizedPnlUsd || 0)
      return traders.value.filter(item => {
        const volume = Number(item.volume_usdc_30d || 0)
        const score = Number(item.followability?.score || 0)
        const realizedPnl = Number(item.realized_pnl_30d || 0)
        return volume >= volumeThreshold && score >= scoreThreshold && realizedPnl >= pnlThreshold
      })
    })
    const currentPoolStatus = computed(() => {
      return (cacheStatus.pools || []).find(item => item.cache_key === currentCacheKey.value) || null
    })

    const syncCacheStatus = data => {
      cacheStatus.running = data?.running || false
      cacheStatus.interval_seconds = data?.interval_seconds || 0
      cacheStatus.ttl_seconds = data?.ttl_seconds || 0
      cacheStatus.default_pools = data?.default_pools || []
      cacheStatus.pools = data?.pools || []
    }

    const loadCacheStatus = async () => {
      loadingStatus.value = true
      try {
        const data = await polymarket.getTraderCacheStatus()
        syncCacheStatus(data)
      } catch (error) {
        console.error('Failed to load polymarket cache status:', error)
        ElMessage.error('读取 Polymarket 缓存状态失败')
      } finally {
        loadingStatus.value = false
      }
    }

    const loadTraders = async (extra = {}) => {
      loadingTraders.value = true
      try {
        const params = {
          category: filters.category,
          time_period: filters.timePeriod,
          order_by: filters.orderBy,
          limit: filters.limit,
          use_cache: filters.useCache,
          ...extra
        }
        if (filters.wallets.trim()) {
          params.wallets = filters.wallets.trim()
        }
        const data = await polymarket.listTraders(params)
        traders.value = data || []
      } catch (error) {
        console.error('Failed to load polymarket traders:', error)
        ElMessage.error('加载 Polymarket 交易员池失败')
      } finally {
        loadingTraders.value = false
      }
    }

    const refreshCurrentPool = async () => {
      refreshingPool.value = true
      try {
        await polymarket.refreshTraderCache({
          category: filters.category,
          time_period: filters.timePeriod,
          order_by: filters.orderBy,
          limit: filters.limit
        })
        ElMessage.success('当前候选池已刷新')
        await Promise.all([
          loadCacheStatus(),
          loadTraders({ force_refresh: true })
        ])
      } catch (error) {
        console.error('Failed to refresh trader pool cache:', error)
        ElMessage.error('刷新候选池缓存失败')
      } finally {
        refreshingPool.value = false
      }
    }

    const openTraderDetail = row => {
      router.push({
        name: 'PolymarketTraderDetail',
        params: { wallet: row.wallet_address }
      })
    }

    const resetWallets = () => {
      filters.wallets = ''
    }

    const resetBaseFilters = () => {
      filters.minVolumeUsd = DEFAULT_MIN_VOLUME_USD
      filters.minFollowabilityScore = DEFAULT_MIN_FOLLOWABILITY_SCORE
      filters.minRealizedPnlUsd = DEFAULT_MIN_REALIZED_PNL_USD
    }

    const formatDateTime = value => {
      if (!value) {
        return '-'
      }
      return formatDisplayDateTime(value)
    }

    onMounted(async () => {
      await Promise.all([
        loadCacheStatus(),
        loadTraders()
      ])
    })

    return {
      categoryOptions,
      timePeriodOptions,
      orderByOptions,
      loadingTraders,
      loadingStatus,
      refreshingPool,
      traders,
      filteredTraders,
      cacheStatus,
      filters,
      currentPoolStatus,
      loadCacheStatus,
      loadTraders,
      refreshCurrentPool,
      openTraderDetail,
      resetWallets,
      resetBaseFilters,
      formatDateTime,
      formatMoney: formatPolymarketMoney,
      formatPercent: formatPolymarketPercent,
      formatWinRate: formatPolymarketWinRate,
      formatNumber: formatPolymarketNumber,
      formatVerdict: formatPolymarketVerdict,
      formatTraderStyle: formatPolymarketTraderStyle,
      getStyleTagType: getPolymarketStyleTagType,
      getFollowabilityColor: getPolymarketFollowabilityColor,
      shortenWallet: shortenPolymarketWallet,
      getAvatarFallback: getPolymarketAvatarFallback,
      Refresh
    }
  }
}
</script>

<style scoped>
.polymarket-traders-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 32px;
  border-radius: 24px;
  color: #f8fafc;
  background:
    radial-gradient(circle at top right, rgba(110, 231, 183, 0.35), transparent 30%),
    linear-gradient(135deg, #0f172a 0%, #13314a 52%, #0f766e 100%);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.22);
}

.eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.72);
}

.hero-panel h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.1;
}

.hero-copy {
  max-width: 760px;
  margin: 12px 0 0;
  font-size: 14px;
  line-height: 1.7;
  color: rgba(226, 232, 240, 0.86);
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.status-grid {
  width: 100%;
}

.pool-form-actions,
.header-right-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pool-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.status-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.metric-item {
  padding: 14px 16px;
  border-radius: 16px;
  background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.metric-item strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
  color: #0f172a;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
}

.current-pool-box {
  margin-top: 16px;
  padding: 18px;
  border-radius: 18px;
  background: #0f172a;
  color: #e2e8f0;
}

.current-pool-title {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(148, 163, 184, 0.88);
}

.current-pool-meta {
  margin-top: 8px;
  word-break: break-all;
  font-family: Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.current-pool-row {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;
}

.error-note {
  margin-top: 14px;
  color: #fca5a5;
  font-size: 12px;
  line-height: 1.6;
}

.trader-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.trader-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.trader-wallet,
.minor-text {
  font-size: 12px;
  color: #64748b;
}

.pnl-value.positive {
  color: #15803d;
}

.pnl-value.negative {
  color: #b91c1c;
}

.score-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.score-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: #475569;
}

@media (max-width: 960px) {
  .hero-panel {
    flex-direction: column;
  }

  .hero-actions,
  .pool-form-actions,
  .header-right-actions {
    flex-wrap: wrap;
  }
  .status-metrics {
    grid-template-columns: 1fr;
  }
}
</style>