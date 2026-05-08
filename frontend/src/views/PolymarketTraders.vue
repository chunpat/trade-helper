<template>
  <div class="polymarket-traders-page">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">Polymarket Copy Trading</p>
        <h1>交易员池与候选缓存</h1>
        <p class="hero-copy">
          后端会周期抓取候选交易员并缓存分析结果。这里可以切换榜单池、查看缓存状态、强制刷新，以及展开单个交易员的可跟单画像。
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
                  <el-input-number v-model="filters.limit" :min="5" :max="20" :step="5" style="width: 100%" />
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
            <el-tag size="small" type="info">{{ traders.length }} 位交易员</el-tag>
            <el-switch v-model="filters.useCache" active-text="优先读缓存" inactive-text="实时拉取" />
          </div>
        </div>
      </template>

      <el-table :data="traders" stripe v-loading="loadingTraders" class="trader-table">
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
            <el-button link type="primary" @click="openTraderDetail(scope.row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="detailVisible" size="58%" :with-header="false" destroy-on-close>
      <div v-if="detailProfile" class="detail-drawer">
        <div class="detail-hero">
          <div class="detail-identity">
            <el-avatar :size="56" :src="detailProfile.profile_image || undefined">
              {{ getAvatarFallback(detailProfile) }}
            </el-avatar>
            <div>
              <div class="detail-title-row">
                <h2>{{ detailProfile.name || detailProfile.pseudonym || shortenWallet(detailProfile.wallet_address) }}</h2>
                <el-tag v-if="detailProfile.verified_badge" type="success">认证</el-tag>
              </div>
              <div class="detail-wallet">{{ detailProfile.wallet_address }}</div>
              <p v-if="detailProfile.bio" class="detail-bio">{{ detailProfile.bio }}</p>
            </div>
          </div>
          <el-button :icon="Refresh" :loading="loadingDetail" @click="reloadDetail">刷新详情</el-button>
        </div>

        <el-row :gutter="12" class="detail-stats">
          <el-col :xs="12" :md="6">
            <div class="detail-stat-card">
              <span class="label">近30天成交</span>
              <strong>{{ detailProfile.trade_count_30d }}</strong>
            </div>
          </el-col>
          <el-col :xs="12" :md="6">
            <div class="detail-stat-card">
              <span class="label">近30天成交额</span>
              <strong>{{ formatMoney(detailProfile.volume_usdc_30d) }}</strong>
            </div>
          </el-col>
          <el-col :xs="12" :md="6">
            <div class="detail-stat-card">
              <span class="label">已实现收益</span>
              <strong>{{ detailProfile.realized_pnl_30d == null ? '-' : formatMoney(detailProfile.realized_pnl_30d) }}</strong>
            </div>
          </el-col>
          <el-col :xs="12" :md="6">
            <div class="detail-stat-card">
              <span class="label">平仓胜率</span>
              <strong>{{ formatWinRate(detailProfile.win_rate_30d) }}</strong>
            </div>
          </el-col>
        </el-row>

        <el-row :gutter="16" class="detail-panels">
          <el-col :xs="24" :lg="10">
            <el-card shadow="never" class="detail-card accent-card">
              <template #header>
                <div class="card-header">
                  <span>跟单评估</span>
                  <el-tag :type="detailProfile.followability.likely_bot ? 'danger' : 'primary'" size="small">
                    {{ formatVerdict(detailProfile.followability.verdict) }}
                  </el-tag>
                </div>
              </template>
              <div class="big-score">{{ detailProfile.followability.score.toFixed(0) }}</div>
              <div class="big-score-label">可跟单评分</div>
              <div class="followability-grid">
                <div>
                  <span>成交间隔中位数</span>
                  <strong>{{ formatSeconds(detailProfile.followability.median_trade_interval_seconds) }}</strong>
                </div>
                <div>
                  <span>每小时成交</span>
                  <strong>{{ formatNumber(detailProfile.followability.trades_per_hour_30d) }}</strong>
                </div>
                <div>
                  <span>平均单笔金额</span>
                  <strong>{{ formatMoney(detailProfile.followability.avg_trade_size_usdc_30d) }}</strong>
                </div>
                <div>
                  <span>头部市场集中度</span>
                  <strong>{{ formatPercent(detailProfile.followability.top_market_share_30d) }}</strong>
                </div>
              </div>
              <div class="reason-list">
                <div v-for="reason in detailProfile.followability.reasons" :key="reason" class="reason-item">
                  {{ reason }}
                </div>
              </div>
              <div v-if="detailProfile.followability.bot_reasons?.length" class="bot-reasons">
                <div class="bot-reason-title">机器人判定原因</div>
                <div v-for="reason in detailProfile.followability.bot_reasons" :key="reason" class="reason-item danger">
                  {{ reason }}
                </div>
              </div>
            </el-card>
          </el-col>

          <el-col :xs="24" :lg="14">
            <el-card shadow="never" class="detail-card">
              <template #header>
                <div class="card-header">
                  <span>当前持仓</span>
                  <el-tag size="small" type="info">{{ detailProfile.current_positions.length }}</el-tag>
                </div>
              </template>
              <el-table :data="detailProfile.current_positions" size="small" max-height="220">
                <el-table-column prop="title" label="市场" min-width="180" />
                <el-table-column prop="outcome" label="方向" width="90" />
                <el-table-column label="当前价值" width="120" align="right">
                  <template #default="scope">{{ formatMoney(scope.row.current_value) }}</template>
                </el-table-column>
                <el-table-column label="收益率" width="100" align="right">
                  <template #default="scope">{{ formatPercent(scope.row.percent_pnl, 2) }}</template>
                </el-table-column>
              </el-table>
            </el-card>

            <el-card shadow="never" class="detail-card">
              <template #header>
                <div class="card-header">
                  <span>近期活动</span>
                  <el-tag size="small">{{ detailProfile.recent_activities.length }}</el-tag>
                </div>
              </template>
              <el-table :data="detailProfile.recent_activities" size="small" max-height="260">
                <el-table-column prop="activity_type" label="类型" width="90" />
                <el-table-column prop="title" label="市场" min-width="180" />
                <el-table-column prop="side" label="方向" width="80" />
                <el-table-column label="金额" width="100" align="right">
                  <template #default="scope">{{ formatMoney(scope.row.usdc_size) }}</template>
                </el-table-column>
                <el-table-column label="时间" min-width="160">
                  <template #default="scope">{{ formatDateTime(scope.row.timestamp) }}</template>
                </el-table-column>
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </div>
      <div v-else class="detail-loading">
        <el-skeleton :rows="8" animated />
      </div>
    </el-drawer>
  </div>
</template>

<script>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { polymarket } from '@/api'
import { formatDateTime as formatDisplayDateTime } from '@/utils/datetime'

const categoryOptions = ['OVERALL', 'POLITICS', 'SPORTS', 'CRYPTO', 'CULTURE', 'MENTIONS', 'WEATHER', 'ECONOMICS', 'TECH', 'FINANCE']
const timePeriodOptions = ['DAY', 'WEEK', 'MONTH', 'ALL']
const orderByOptions = ['PNL', 'VOL']

export default {
  name: 'PolymarketTraders',
  components: {
    Refresh
  },
  setup() {
    const loadingTraders = ref(false)
    const loadingStatus = ref(false)
    const refreshingPool = ref(false)
    const loadingDetail = ref(false)
    const detailVisible = ref(false)
    const traders = ref([])
    const detailProfile = ref(null)
    const selectedWallet = ref('')
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
      limit: 10,
      wallets: '',
      useCache: true
    })

    const currentCacheKey = computed(() => `${filters.category}:${filters.timePeriod}:${filters.orderBy}:${filters.limit}`)
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

    const openTraderDetail = async row => {
      selectedWallet.value = row.wallet_address
      detailVisible.value = true
      detailProfile.value = null
      await loadTraderDetail(row.wallet_address)
    }

    const loadTraderDetail = async wallet => {
      loadingDetail.value = true
      try {
        detailProfile.value = await polymarket.getTraderProfile(wallet)
      } catch (error) {
        console.error('Failed to load trader detail:', error)
        ElMessage.error('加载交易员详情失败')
      } finally {
        loadingDetail.value = false
      }
    }

    const reloadDetail = async () => {
      if (!selectedWallet.value) {
        return
      }
      await loadTraderDetail(selectedWallet.value)
    }

    const resetWallets = () => {
      filters.wallets = ''
    }

    const formatDateTime = value => {
      if (!value) {
        return '-'
      }
      return formatDisplayDateTime(value)
    }

    const formatMoney = value => {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '-'
      }
      const numeric = Number(value)
      if (Math.abs(numeric) >= 1000000) {
        return `$${(numeric / 1000000).toFixed(2)}M`
      }
      if (Math.abs(numeric) >= 1000) {
        return `$${(numeric / 1000).toFixed(1)}K`
      }
      return `$${numeric.toFixed(2)}`
    }

    const formatPercent = (value, digits = 1) => {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '-'
      }
      return `${Number(value).toFixed(digits)}%`
    }

    const formatWinRate = value => {
      if (value === null || value === undefined) {
        return '-'
      }
      const numeric = Number(value)
      return numeric <= 1 ? `${(numeric * 100).toFixed(1)}%` : `${numeric.toFixed(1)}%`
    }

    const formatNumber = value => {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '-'
      }
      return Number(value).toFixed(2)
    }

    const formatSeconds = value => {
      if (value === null || value === undefined) {
        return '-'
      }
      const numeric = Number(value)
      if (numeric < 60) {
        return `${numeric.toFixed(0)} 秒`
      }
      if (numeric < 3600) {
        return `${(numeric / 60).toFixed(1)} 分钟`
      }
      return `${(numeric / 3600).toFixed(1)} 小时`
    }

    const formatVerdict = verdict => {
      return {
        candidate: '优先候选',
        watchlist: '观察名单',
        cautious: '谨慎跟随',
        avoid: '不建议跟随'
      }[verdict] || verdict || '-'
    }

    const formatTraderStyle = style => {
      return {
        discretionary: '主观交易',
        high_frequency: '高频风格',
        specialist: '单题材聚焦',
        broad_portfolio: '广覆盖组合'
      }[style] || style || '未知'
    }

    const getStyleTagType = style => {
      return {
        discretionary: 'success',
        high_frequency: 'warning',
        specialist: 'primary',
        broad_portfolio: 'info'
      }[style] || 'info'
    }

    const getFollowabilityColor = score => {
      if (score >= 75) {
        return '#16a34a'
      }
      if (score >= 55) {
        return '#f59e0b'
      }
      return '#ef4444'
    }

    const shortenWallet = wallet => {
      if (!wallet) {
        return '-'
      }
      return `${wallet.slice(0, 6)}...${wallet.slice(-4)}`
    }

    const getAvatarFallback = row => {
      const source = row?.name || row?.pseudonym || row?.wallet_address || 'PM'
      return source.slice(0, 2).toUpperCase()
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
      loadingDetail,
      detailVisible,
      traders,
      detailProfile,
      cacheStatus,
      filters,
      currentPoolStatus,
      loadCacheStatus,
      loadTraders,
      refreshCurrentPool,
      openTraderDetail,
      reloadDetail,
      resetWallets,
      formatDateTime,
      formatMoney,
      formatPercent,
      formatWinRate,
      formatNumber,
      formatSeconds,
      formatVerdict,
      formatTraderStyle,
      getStyleTagType,
      getFollowabilityColor,
      shortenWallet,
      getAvatarFallback,
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

.status-grid,
.detail-stats,
.detail-panels {
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

.metric-item,
.detail-stat-card {
  padding: 14px 16px;
  border-radius: 16px;
  background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.metric-item strong,
.detail-stat-card strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
  color: #0f172a;
}

.metric-label,
.detail-stat-card .label {
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

.current-pool-meta,
.detail-wallet {
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

.trader-cell,
.detail-identity,
.detail-title-row {
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

.detail-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.detail-title-row h2 {
  margin: 0;
  font-size: 26px;
  color: #0f172a;
}

.detail-bio {
  margin: 8px 0 0;
  color: #475569;
  line-height: 1.7;
}

.detail-card {
  border-radius: 20px;
}

.accent-card {
  background: linear-gradient(180deg, #f8fafc 0%, #eff6ff 100%);
}

.big-score {
  font-size: 52px;
  line-height: 1;
  font-weight: 700;
  color: #0f172a;
}

.big-score-label {
  margin-top: 6px;
  color: #475569;
  font-size: 13px;
}

.followability-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.followability-grid div {
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.78);
}

.followability-grid span {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.followability-grid strong {
  display: block;
  margin-top: 4px;
  font-size: 16px;
}

.reason-list,
.bot-reasons {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reason-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.04);
  color: #334155;
  line-height: 1.6;
  font-size: 13px;
}

.reason-item.danger,
.bot-reason-title {
  color: #b91c1c;
}

.detail-loading {
  padding: 24px;
}

@media (max-width: 960px) {
  .hero-panel,
  .detail-hero {
    flex-direction: column;
  }

  .hero-actions,
  .pool-form-actions,
  .header-right-actions {
    flex-wrap: wrap;
  }

  .status-metrics,
  .followability-grid {
    grid-template-columns: 1fr;
  }
}
</style>