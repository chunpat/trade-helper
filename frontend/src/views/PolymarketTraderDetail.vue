<template>
  <div class="polymarket-trader-detail-page">
    <el-page-header class="detail-header" @back="goBack">
      <template #content>
        <div class="header-content">
          <span class="header-title">交易员详情</span>
          <el-tag v-if="profile" :type="profile.followability.likely_bot ? 'danger' : 'success'" size="small">
            {{ profile.followability.likely_bot ? '疑似机器人' : '偏人工' }}
          </el-tag>
        </div>
      </template>
      <template #extra>
        <div class="header-actions">
          <el-button plain @click="refreshActivity({ forceRefresh: true })" :loading="loadingActivity">刷新活动</el-button>
          <el-button type="primary" :icon="Refresh" @click="loadProfile({ forceRefresh: true })" :loading="loadingProfile">刷新画像</el-button>
        </div>
      </template>
    </el-page-header>

    <el-skeleton v-if="loadingProfile && !profile" :rows="10" animated />

    <template v-else-if="profile">
      <section class="detail-hero">
        <div class="identity-block">
          <el-avatar :size="64" :src="profile.profile_image || undefined">
            {{ getAvatarFallback(profile) }}
          </el-avatar>
          <div>
            <div class="identity-title-row">
              <h1>{{ profile.name || profile.pseudonym || shortenWallet(profile.wallet_address) }}</h1>
              <el-tag v-if="profile.verified_badge" type="success">认证</el-tag>
              <el-tag v-if="profile.trader_style" :type="getStyleTagType(profile.trader_style)">
                {{ formatTraderStyle(profile.trader_style) }}
              </el-tag>
            </div>
            <div class="wallet-line">{{ profile.wallet_address }}</div>
            <p v-if="profile.bio" class="bio-text">{{ profile.bio }}</p>
          </div>
        </div>

        <div class="hero-score-card">
          <div class="score-label">可跟单评分</div>
          <div class="score-value">{{ profile.followability.score.toFixed(0) }}</div>
          <div class="score-verdict">{{ formatVerdict(profile.followability.verdict) }}</div>
          <el-progress
            :percentage="Math.round(profile.followability.score)"
            :show-text="false"
            :stroke-width="10"
            :color="getFollowabilityColor(profile.followability.score)"
          />
        </div>
      </section>

      <el-row :gutter="16" class="summary-grid">
        <el-col :xs="12" :md="6"><div class="metric-card"><span>近30天成交</span><strong>{{ profile.trade_count_30d }}</strong></div></el-col>
        <el-col :xs="12" :md="6"><div class="metric-card"><span>近30天成交额</span><strong>{{ formatMoney(profile.volume_usdc_30d) }}</strong></div></el-col>
        <el-col :xs="12" :md="6"><div class="metric-card"><span>平仓胜率</span><strong>{{ formatWinRate(profile.win_rate_30d) }}</strong></div></el-col>
        <el-col :xs="12" :md="6"><div class="metric-card"><span>已实现收益</span><strong>{{ formatMoney(profile.realized_pnl_30d) }}</strong></div></el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <el-card shadow="hover" class="detail-card">
            <template #header>
              <div class="card-header">
                <span>跟单评估</span>
                <el-tag :type="profile.followability.skip_recommended ? 'warning' : 'success'" size="small">
                  {{ profile.followability.skip_recommended ? '建议谨慎' : '可进入候选' }}
                </el-tag>
              </div>
            </template>
            <div class="mini-grid">
              <div><span>成交间隔中位数</span><strong>{{ formatSeconds(profile.followability.median_trade_interval_seconds) }}</strong></div>
              <div><span>每小时成交</span><strong>{{ formatNumber(profile.followability.trades_per_hour_30d) }}</strong></div>
              <div><span>平均单笔金额</span><strong>{{ formatMoney(profile.followability.avg_trade_size_usdc_30d) }}</strong></div>
              <div><span>头部市场集中度</span><strong>{{ formatPercent(profile.followability.top_market_share_30d, 1, true) }}</strong></div>
            </div>
            <div class="reason-list">
              <div v-for="reason in profile.followability.reasons" :key="reason" class="reason-item">{{ reason }}</div>
            </div>
            <div v-if="profile.followability.bot_reasons?.length" class="reason-group">
              <div class="group-title danger">机器人判定原因</div>
              <div v-for="reason in profile.followability.bot_reasons" :key="reason" class="reason-item danger">{{ reason }}</div>
            </div>
            <div v-if="profile.analysis_notes?.length" class="reason-group">
              <div class="group-title">画像备注</div>
              <div v-for="note in profile.analysis_notes" :key="note" class="reason-item">{{ note }}</div>
            </div>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="14">
          <el-card shadow="hover" class="detail-card chart-card">
            <template #header>
              <div class="card-header">
                <span>收益曲线</span>
                <el-tag size="small" type="info">基于 recent closed positions</el-tag>
              </div>
            </template>
            <div ref="pnlChartRef" class="chart-box"></div>
          </el-card>

          <el-card shadow="hover" class="detail-card chart-card">
            <template #header>
              <div class="card-header">
                <span>市场偏好</span>
                <div class="chart-controls">
                  <el-radio-group v-model="marketPreferenceMetric" size="small">
                    <el-radio-button label="count">次数</el-radio-button>
                    <el-radio-button label="volume">金额</el-radio-button>
                    <el-radio-button label="pnl">净收益</el-radio-button>
                  </el-radio-group>
                  <el-tag size="small" type="info">{{ marketPreferenceMetricTag }}</el-tag>
                </div>
              </div>
            </template>
            <div ref="marketPreferenceChartRef" class="chart-box"></div>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="hover" class="detail-card activity-card">
        <template #header>
          <div class="card-header activity-header">
            <span>历史活动筛选</span>
            <div class="activity-filters">
              <el-select v-model="activityFilters.viewMode" size="small" style="width: 120px">
                <el-option label="原始活动" value="raw" />
                <el-option label="聚合成交" value="grouped" />
              </el-select>
              <el-select v-model="activityFilters.hours" size="small" style="width: 110px" @change="refreshActivity">
                <el-option label="24 小时" :value="24" />
                <el-option label="72 小时" :value="72" />
                <el-option label="7 天" :value="168" />
                <el-option label="30 天" :value="720" />
              </el-select>
              <el-select v-model="activityFilters.limit" size="small" style="width: 100px" @change="refreshActivity">
                <el-option label="50 条" :value="50" />
                <el-option label="100 条" :value="100" />
                <el-option label="200 条" :value="200" />
              </el-select>
              <el-select v-model="activityFilters.type" size="small" style="width: 140px">
                <el-option label="全部类型" value="ALL" />
                <el-option label="只看 TRADE" value="TRADE" />
                <el-option label="只看 SPLIT" value="SPLIT" />
                <el-option label="只看 MERGE" value="MERGE" />
                <el-option label="只看 REDEEM" value="REDEEM" />
              </el-select>
            </div>
          </div>
        </template>

        <div v-if="activityFilters.viewMode === 'grouped'" class="aggregation-note">
          聚合成交视图会优先合并同一 transaction hash；如果同一订单被拆成多笔撮合成交，则会继续按市场、方向、结果、资产、价格和短时间窗口近似聚合。
        </div>

        <div class="activity-summary-row">
          <div class="activity-summary-card">
            <span>原始 TRADE 中位间隔</span>
            <strong>{{ formatSeconds(rawTradeMedianIntervalSeconds) }}</strong>
          </div>
          <div class="activity-summary-card">
            <span>聚合后中位间隔</span>
            <strong>{{ formatSeconds(groupedTradeMedianIntervalSeconds) }}</strong>
          </div>
          <div class="activity-summary-card">
            <span>聚合减少记录</span>
            <strong>{{ groupedReductionCount }}</strong>
          </div>
        </div>

        <el-table :data="displayActivities" v-loading="loadingActivity" size="small" max-height="360">
          <el-table-column :prop="activityFilters.viewMode === 'grouped' ? 'display_type' : 'activity_type'" label="类型" width="90" />
          <el-table-column prop="title" label="市场" min-width="220" />
          <el-table-column prop="outcome" label="结果" width="90" />
          <el-table-column prop="side" label="方向" width="80" />
          <el-table-column v-if="activityFilters.viewMode === 'grouped'" label="聚合笔数" width="90" align="right">
            <template #default="scope">{{ scope.row.group_count }}</template>
          </el-table-column>
          <el-table-column label="金额" width="110" align="right">
            <template #default="scope">{{ formatMoney(scope.row.usdc_size) }}</template>
          </el-table-column>
          <el-table-column label="价格" width="90" align="right">
            <template #default="scope">{{ formatNumber(scope.row.price, 3) }}</template>
          </el-table-column>
          <el-table-column label="时间" min-width="170">
            <template #default="scope">
              <span v-if="activityFilters.viewMode === 'grouped' && scope.row.time_end && scope.row.time_end !== scope.row.timestamp">
                {{ formatDateTime(scope.row.timestamp) }} - {{ formatDateTime(scope.row.time_end) }}
              </span>
              <span v-else>{{ formatDateTime(scope.row.timestamp) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="12">
          <el-card shadow="hover" class="detail-card">
            <template #header>
              <div class="card-header">
                <span>当前持仓</span>
                <el-tag size="small">{{ profile.current_positions.length }}</el-tag>
              </div>
            </template>
            <el-table :data="profile.current_positions" size="small" max-height="280">
              <el-table-column prop="title" label="市场" min-width="200" />
              <el-table-column prop="outcome" label="方向" width="90" />
              <el-table-column label="当前价值" width="110" align="right">
                <template #default="scope">{{ formatMoney(scope.row.current_value) }}</template>
              </el-table-column>
              <el-table-column label="收益率" width="90" align="right">
                <template #default="scope">{{ formatPercent(scope.row.percent_pnl, 2) }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="12">
          <el-card shadow="hover" class="detail-card">
            <template #header>
              <div class="card-header">
                <span>近期平仓</span>
                <el-tag size="small">{{ profile.recent_closed_positions.length }}</el-tag>
              </div>
            </template>
            <el-table :data="profile.recent_closed_positions" size="small" max-height="280">
              <el-table-column prop="title" label="市场" min-width="200" />
              <el-table-column prop="outcome" label="结果" width="90" />
              <el-table-column label="已实现收益" width="120" align="right">
                <template #default="scope">
                  <span :class="Number(scope.row.realized_pnl || 0) >= 0 ? 'positive' : 'negative'">
                    {{ formatMoney(scope.row.realized_pnl) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="时间" min-width="150">
                <template #default="scope">{{ formatDateTime(scope.row.timestamp) }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import echarts from '@/lib/echarts'
import { polymarket } from '@/api'
import { formatDateTime as formatDisplayDateTime } from '@/utils/datetime'
import {
  formatPolymarketMoney,
  formatPolymarketNumber,
  formatPolymarketPercent,
  formatPolymarketSeconds,
  formatPolymarketTraderStyle,
  formatPolymarketVerdict,
  formatPolymarketWinRate,
  getPolymarketAvatarFallback,
  getPolymarketFollowabilityColor,
  getPolymarketStyleTagType,
  shortenPolymarketWallet
} from '@/utils/polymarket'

export default {
  name: 'PolymarketTraderDetail',
  components: {
    Refresh
  },
  setup() {
    const route = useRoute()
    const router = useRouter()
    const loadingProfile = ref(false)
    const loadingActivity = ref(false)
    const profile = ref(null)
    const activities = ref([])
    const pnlChartRef = ref(null)
    const marketPreferenceChartRef = ref(null)
    const marketPreferenceMetric = ref('count')
    const activityFilters = reactive({
      hours: 168,
      limit: 100,
      type: 'ALL',
      viewMode: 'raw'
    })

    let pnlChartInstance = null
    let marketPreferenceChartInstance = null

    const walletAddress = computed(() => route.params.wallet)

    const filteredActivities = computed(() => {
      if (activityFilters.type === 'ALL') {
        return activities.value
      }
      return activities.value.filter(item => item.activity_type === activityFilters.type)
    })

    const TRADE_GROUP_WINDOW_SECONDS = 8
    const TRADE_GROUP_PRICE_TOLERANCE = 0.01

    const buildGroupedActivitySeed = item => ({
      ...item,
      display_type: item.activity_type === 'TRADE' ? 'TRADE*' : item.activity_type,
      group_count: 0,
      time_end: item.timestamp,
      aggregated_volume: 0,
      weighted_price_sum: 0,
      weighted_price_base: 0
    })

    const mergeActivityIntoGroup = (group, item) => {
      group.group_count += 1

      const tradeAmount = Number(item.usdc_size || 0)
      group.aggregated_volume += tradeAmount
      if (item.price !== null && item.price !== undefined && tradeAmount > 0) {
        group.weighted_price_sum += Number(item.price) * tradeAmount
        group.weighted_price_base += tradeAmount
      }

      if (item.timestamp && (!group.timestamp || new Date(item.timestamp) < new Date(group.timestamp))) {
        group.timestamp = item.timestamp
      }
      if (item.timestamp && (!group.time_end || new Date(item.timestamp) > new Date(group.time_end))) {
        group.time_end = item.timestamp
      }
      if (tradeAmount > 0) {
        group.usdc_size = Number(group.aggregated_volume.toFixed(2))
      }
      if (group.weighted_price_base > 0) {
        group.price = Number((group.weighted_price_sum / group.weighted_price_base).toFixed(4))
      }
    }

    const buildTradeSignature = item => ([
      item.condition_id || item.title || 'unknown',
      item.asset || 'unknown',
      item.side || 'NA',
      item.outcome || 'NA'
    ].join('|'))

    const canMergeTradeIntoGroup = (group, item) => {
      if (group.activity_type !== 'TRADE' || item.activity_type !== 'TRADE') {
        return false
      }
      if (buildTradeSignature(group) !== buildTradeSignature(item)) {
        return false
      }

      const groupHash = group.transaction_hash || ''
      const itemHash = item.transaction_hash || ''
      if (groupHash && itemHash && groupHash === itemHash) {
        return true
      }

      const groupEndTime = group.time_end ? new Date(group.time_end).getTime() : new Date(group.timestamp).getTime()
      const itemTime = item.timestamp ? new Date(item.timestamp).getTime() : 0
      if (!groupEndTime || !itemTime) {
        return false
      }

      const timeGapSeconds = Math.abs(itemTime - groupEndTime) / 1000
      if (timeGapSeconds > TRADE_GROUP_WINDOW_SECONDS) {
        return false
      }

      const groupPrice = Number(group.price)
      const itemPrice = Number(item.price)
      if (Number.isFinite(groupPrice) && Number.isFinite(itemPrice)) {
        if (Math.abs(groupPrice - itemPrice) > TRADE_GROUP_PRICE_TOLERANCE) {
          return false
        }
      }

      return true
    }

    const groupedActivities = computed(() => {
      const exactGroups = new Map()
      const latestTradeGroupsBySignature = new Map()
      const groupedRows = []

      ;[...filteredActivities.value]
        .sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp))
        .forEach(item => {
          if (item.activity_type === 'TRADE') {
            const signature = buildTradeSignature(item)
            const existingTradeGroup = latestTradeGroupsBySignature.get(signature)
            if (existingTradeGroup && canMergeTradeIntoGroup(existingTradeGroup, item)) {
              mergeActivityIntoGroup(existingTradeGroup, item)
              return
            }

            const tradeGroup = buildGroupedActivitySeed(item)
            mergeActivityIntoGroup(tradeGroup, item)
            latestTradeGroupsBySignature.set(signature, tradeGroup)
            groupedRows.push(tradeGroup)
            return
          }

          const timestampValue = item.timestamp ? new Date(item.timestamp).getTime() : 0
          const groupingKey = `${item.activity_type}:${item.transaction_hash || timestampValue}:${item.condition_id || item.title || 'unknown'}`
          if (!exactGroups.has(groupingKey)) {
            const group = buildGroupedActivitySeed(item)
            exactGroups.set(groupingKey, group)
            groupedRows.push(group)
          }

          mergeActivityIntoGroup(exactGroups.get(groupingKey), item)
        })

      return groupedRows.sort((left, right) => new Date(right.timestamp) - new Date(left.timestamp))
    })

    const displayActivities = computed(() => {
      if (activityFilters.viewMode === 'grouped') {
        return groupedActivities.value
      }
      return filteredActivities.value
    })

    const calculateMedianIntervalSeconds = rows => {
      const timestamps = [...new Set(
        rows
          .map(item => item?.timestamp ? Math.floor(new Date(item.timestamp).getTime() / 1000) : null)
          .filter(value => value !== null)
      )].sort((left, right) => left - right)

      if (timestamps.length < 2) {
        return null
      }

      const gaps = []
      for (let index = 1; index < timestamps.length; index += 1) {
        const gap = timestamps[index] - timestamps[index - 1]
        if (gap >= 0) {
          gaps.push(gap)
        }
      }

      if (!gaps.length) {
        return null
      }

      const sortedGaps = [...gaps].sort((left, right) => left - right)
      const middleIndex = Math.floor(sortedGaps.length / 2)
      if (sortedGaps.length % 2 === 1) {
        return sortedGaps[middleIndex]
      }
      return Number(((sortedGaps[middleIndex - 1] + sortedGaps[middleIndex]) / 2).toFixed(2))
    }

    const rawTradeMedianIntervalSeconds = computed(() => {
      return calculateMedianIntervalSeconds(filteredActivities.value.filter(item => item.activity_type === 'TRADE'))
    })

    const groupedTradeMedianIntervalSeconds = computed(() => {
      return calculateMedianIntervalSeconds(groupedActivities.value.filter(item => item.activity_type === 'TRADE'))
    })

    const groupedReductionCount = computed(() => {
      const rawTradeCount = filteredActivities.value.filter(item => item.activity_type === 'TRADE').length
      const groupedTradeCount = groupedActivities.value.filter(item => item.activity_type === 'TRADE').length
      return Math.max(0, rawTradeCount - groupedTradeCount)
    })

    const pnlSeries = computed(() => {
      const rows = [...(profile.value?.recent_closed_positions || [])]
        .filter(item => item.timestamp)
        .sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp))

      let cumulative = 0
      return rows.map(item => {
        cumulative += Number(item.realized_pnl || 0)
        return {
          label: formatDisplayDateTime(item.timestamp),
          value: Number(cumulative.toFixed(2))
        }
      })
    })

    const activityMarketAggregates = computed(() => {
      const aggregates = {}
      filteredActivities.value
        .filter(item => item.activity_type === 'TRADE')
        .forEach(item => {
          const key = item.title || item.slug || item.condition_id || '未知市场'
          if (!aggregates[key]) {
            aggregates[key] = { name: key, count: 0, volume: 0 }
          }
          aggregates[key].count += 1
          aggregates[key].volume += Number(item.usdc_size || 0)
        })

      return Object.values(aggregates)
    })

    const pnlMarketAggregates = computed(() => {
      const aggregates = {}
      ;(profile.value?.recent_closed_positions || []).forEach(item => {
        const key = item.title || item.slug || item.condition_id || '未知市场'
        if (!aggregates[key]) {
          aggregates[key] = { name: key, pnl: 0 }
        }
        aggregates[key].pnl += Number(item.realized_pnl || 0)
      })

      return Object.values(aggregates)
    })

    const marketPreferenceMetricTag = computed(() => {
      return {
        count: '按近期活动次数聚合',
        volume: '按近期成交金额聚合',
        pnl: '按近期平仓净收益聚合'
      }[marketPreferenceMetric.value]
    })

    const marketPreferenceSeries = computed(() => {
      if (marketPreferenceMetric.value === 'pnl') {
        return pnlMarketAggregates.value
          .sort((left, right) => Math.abs(right.pnl) - Math.abs(left.pnl))
          .slice(0, 8)
          .map(item => ({ name: item.name, value: Number(item.pnl.toFixed(2)) }))
      }

      const field = marketPreferenceMetric.value === 'volume' ? 'volume' : 'count'
      return activityMarketAggregates.value
        .sort((left, right) => right[field] - left[field])
        .slice(0, 8)
        .map(item => ({
          name: item.name,
          value: Number((field === 'volume' ? item.volume : item.count).toFixed?.(2) || item[field])
        }))
    })

    const formatMarketPreferenceValue = value => {
      if (marketPreferenceMetric.value === 'count') {
        return `${Number(value).toFixed(0)} 次`
      }
      return formatPolymarketMoney(value)
    }

    const ensureCharts = () => {
      if (!pnlChartInstance && pnlChartRef.value) {
        pnlChartInstance = echarts.init(pnlChartRef.value)
      }
      if (!marketPreferenceChartInstance && marketPreferenceChartRef.value) {
        marketPreferenceChartInstance = echarts.init(marketPreferenceChartRef.value)
      }
    }

    const renderCharts = async () => {
      await nextTick()
      ensureCharts()
      if (pnlChartInstance) {
        pnlChartInstance.setOption({
          tooltip: { trigger: 'axis' },
          grid: { left: 16, right: 16, top: 20, bottom: 40, containLabel: true },
          xAxis: {
            type: 'category',
            data: pnlSeries.value.map(item => item.label),
            axisLabel: { color: '#64748b', hideOverlap: true }
          },
          yAxis: {
            type: 'value',
            axisLabel: { color: '#64748b' },
            splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.18)' } }
          },
          series: [{
            type: 'line',
            smooth: true,
            data: pnlSeries.value.map(item => item.value),
            areaStyle: { color: 'rgba(59, 130, 246, 0.14)' },
            lineStyle: { width: 3, color: '#2563eb' },
            showSymbol: pnlSeries.value.length <= 8,
            itemStyle: { color: '#2563eb' }
          }]
        })
      }
      if (marketPreferenceChartInstance) {
        const hasMarketPreferenceData = marketPreferenceSeries.value.length > 0
        marketPreferenceChartInstance.setOption({
          tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            valueFormatter: value => formatMarketPreferenceValue(value)
          },
          grid: { left: 16, right: 32, top: 20, bottom: 20, containLabel: true },
          xAxis: {
            type: 'value',
            axisLabel: {
              color: '#64748b',
              formatter: value => {
                if (marketPreferenceMetric.value === 'count') {
                  return `${Number(value).toFixed(0)}`
                }
                return formatPolymarketMoney(value)
              }
            },
            splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.18)' } }
          },
          yAxis: {
            type: 'category',
            data: marketPreferenceSeries.value.map(item => item.name),
            axisLabel: {
              color: '#475569',
              width: 180,
              overflow: 'truncate'
            }
          },
          graphic: hasMarketPreferenceData
            ? []
            : [{
                type: 'text',
                left: 'center',
                top: 'middle',
                style: {
                  text: '暂无可展示的市场偏好数据',
                  fill: '#94a3b8',
                  fontSize: 14
                }
              }],
          series: [{
            type: 'bar',
            barMaxWidth: 18,
            label: {
              show: hasMarketPreferenceData,
              position: 'right',
              color: '#475569',
              formatter: params => formatMarketPreferenceValue(params.value)
            },
            data: marketPreferenceSeries.value.map(item => ({
              value: item.value,
              itemStyle: {
                color: marketPreferenceMetric.value === 'pnl'
                  ? (item.value >= 0 ? '#16a34a' : '#ef4444')
                  : (marketPreferenceMetric.value === 'volume' ? '#0ea5e9' : '#6366f1')
              }
            }))
          }]
        })
      }
    }

    const loadProfile = async ({ forceRefresh = false } = {}) => {
      if (!walletAddress.value) {
        return
      }
      loadingProfile.value = true
      try {
        profile.value = await polymarket.getTraderProfile(walletAddress.value, {
          use_cache: true,
          force_refresh: forceRefresh
        })
        await renderCharts()
      } catch (error) {
        console.error('Failed to load polymarket trader profile:', error)
        ElMessage.error('加载交易员画像失败')
      } finally {
        loadingProfile.value = false
      }
    }

    const refreshActivity = async ({ forceRefresh = false } = {}) => {
      if (!walletAddress.value) {
        return
      }
      loadingActivity.value = true
      try {
        activities.value = await polymarket.getTraderActivity(walletAddress.value, {
          hours: activityFilters.hours,
          limit: activityFilters.limit,
          use_cache: true,
          force_refresh: forceRefresh
        })
        await renderCharts()
      } catch (error) {
        console.error('Failed to load polymarket trader activity:', error)
        ElMessage.error('加载交易员活动失败')
      } finally {
        loadingActivity.value = false
      }
    }

    const handleResize = () => {
      pnlChartInstance?.resize()
      marketPreferenceChartInstance?.resize()
    }

    const goBack = () => {
      router.push({ name: 'PolymarketTraders' })
    }

    const formatDateTime = value => value ? formatDisplayDateTime(value) : '-'

    watch([() => activityFilters.type, marketPreferenceMetric], () => {
      renderCharts()
    })

    watch(walletAddress, async () => {
      await Promise.all([loadProfile(), refreshActivity()])
    })

    onMounted(async () => {
      window.addEventListener('resize', handleResize)
      await Promise.all([loadProfile(), refreshActivity()])
    })

    onBeforeUnmount(() => {
      window.removeEventListener('resize', handleResize)
      pnlChartInstance?.dispose()
      pnlChartInstance = null
      marketPreferenceChartInstance?.dispose()
      marketPreferenceChartInstance = null
    })

    return {
      profile,
      loadingProfile,
      loadingActivity,
      activityFilters,
      filteredActivities,
      displayActivities,
      rawTradeMedianIntervalSeconds,
      groupedTradeMedianIntervalSeconds,
      groupedReductionCount,
      marketPreferenceMetric,
      marketPreferenceMetricTag,
      pnlChartRef,
      marketPreferenceChartRef,
      loadProfile,
      refreshActivity,
      goBack,
      formatDateTime,
      formatMoney: formatPolymarketMoney,
      formatPercent: formatPolymarketPercent,
      formatWinRate: formatPolymarketWinRate,
      formatNumber: formatPolymarketNumber,
      formatSeconds: formatPolymarketSeconds,
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
.polymarket-trader-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-header {
  padding: 12px 4px;
}

.header-content,
.header-actions,
.identity-block,
.identity-title-row,
.card-header,
.chart-controls,
.activity-header,
.activity-filters {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-content,
.card-header,
.activity-header {
  justify-content: space-between;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.detail-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, 0.18), transparent 32%),
    linear-gradient(135deg, #f8fafc 0%, #e0f2fe 52%, #eef2ff 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.identity-title-row h1 {
  margin: 0;
  font-size: 28px;
  color: #0f172a;
}

.wallet-line {
  margin-top: 8px;
  word-break: break-all;
  font-size: 12px;
  color: #475569;
  font-family: Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
}

.bio-text {
  margin: 10px 0 0;
  color: #334155;
  line-height: 1.7;
}

.hero-score-card,
.metric-card,
.mini-grid div {
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.84);
}

.hero-score-card {
  min-width: 220px;
  padding: 20px;
}

.score-label,
.metric-card span,
.mini-grid span,
.group-title {
  font-size: 12px;
  color: #64748b;
}

.score-value {
  margin-top: 6px;
  font-size: 48px;
  line-height: 1;
  font-weight: 700;
  color: #0f172a;
}

.score-verdict {
  margin: 8px 0 14px;
  color: #334155;
}

.summary-grid {
  width: 100%;
}

.metric-card {
  padding: 16px;
}

.metric-card strong,
.mini-grid strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
  color: #0f172a;
}

.detail-card {
  border-radius: 22px;
}

.chart-card {
  margin-bottom: 16px;
}

.chart-controls {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.chart-box {
  height: 300px;
}

.mini-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.mini-grid div {
  padding: 14px;
}

.reason-list,
.reason-group {
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

.group-title.danger,
.reason-item.danger,
.negative {
  color: #b91c1c;
}

.positive {
  color: #15803d;
}

.activity-card {
  margin-top: 4px;
}

.aggregation-note {
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.activity-summary-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.activity-summary-card {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, #f8fafc 0%, #eef6ff 100%);
}

.activity-summary-card span {
  font-size: 12px;
  color: #64748b;
}

.activity-summary-card strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
  color: #0f172a;
}

@media (max-width: 960px) {
  .detail-hero,
  .activity-header,
  .header-actions,
  .chart-controls,
  .activity-filters,
  .identity-block,
  .identity-title-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .mini-grid {
    grid-template-columns: 1fr;
  }

  .activity-summary-row {
    grid-template-columns: 1fr;
  }

  .hero-score-card {
    width: 100%;
  }
}
</style>