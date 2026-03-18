<template>
  <div class="trade-review">
    <section class="review-hero">
      <div>
        <p class="eyebrow">Trade Review Workspace</p>
        <h1>交易复盘</h1>
        <p class="hero-copy">
          现在默认按完整开平仓交易做分析。也就是买入再卖出的做多单，或卖出再买入的做空单，
          会被还原成一笔完整交易，并把手续费和资金费一起算进去。
        </p>
      </div>
      <div class="hero-actions">
        <el-button @click="resetFilters">重置筛选</el-button>
        <el-button
          type="success"
          plain
          :disabled="!filters.account_id || hasCompleted90DayBackfill"
          :loading="syncingHistory"
          @click="syncHistory"
        >
          {{ syncHistoryButtonText }}
        </el-button>
        <el-tag v-if="hasCompleted90DayBackfill" type="info" effect="dark">当前账户 90 天历史已补</el-tag>
        <el-button type="primary" :loading="isRefreshing" @click="refreshAll({ resetPage: true })">
          刷新复盘
        </el-button>
      </div>
    </section>

    <el-card class="filter-card" shadow="hover">
      <div class="filter-grid filter-grid-main">
        <div class="filter-item">
          <span class="filter-label">账户</span>
          <el-select v-model="filters.account_id" clearable placeholder="全部账户">
            <el-option label="全部账户" :value="null" />
            <el-option
              v-for="account in accounts"
              :key="account.id"
              :label="account.name"
              :value="account.id"
            />
          </el-select>
        </div>

        <div class="filter-item">
          <span class="filter-label">币种</span>
          <el-input
            v-model="filters.symbol"
            placeholder="例如 BTCUSDT"
            clearable
            @keyup.enter="refreshAll({ resetPage: true })"
            @blur="normalizeSymbol"
          />
        </div>

        <div class="filter-item filter-item-wide">
          <span class="filter-label">时间范围</span>
          <el-date-picker
            v-model="dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            unlink-panels
            :shortcuts="dateShortcuts"
          />
        </div>
      </div>

      <div class="filter-foot">
        <div class="filter-hints">
          <el-tag type="info" effect="plain">
            完整交易按平仓时间落入筛选区间，支持把多次加仓、分批减仓合并成同一笔交易。
          </el-tag>
          <el-tag type="warning" effect="plain">
            EVENT_CONTRACTS_ORDER 这类噪音事件不会进入完整交易分析。
          </el-tag>
        </div>
        <el-button type="primary" @click="refreshAll({ resetPage: true })">应用筛选</el-button>
      </div>
    </el-card>

    <section class="summary-grid">
      <el-card shadow="hover" class="summary-card summary-card-primary">
        <p class="summary-label">完整交易数</p>
        <div class="summary-value">{{ completedSummary.total_count }}</div>
        <p class="summary-meta">按完整开平仓闭环统计，不再按单条成交切碎</p>
      </el-card>

      <el-card shadow="hover" class="summary-card">
        <p class="summary-label">胜率</p>
        <div class="summary-value">{{ completedSummary.win_rate.toFixed(2) }}%</div>
        <p class="summary-meta">盈利 {{ completedSummary.win_count }} / 亏损 {{ completedSummary.loss_count }}</p>
      </el-card>

      <el-card shadow="hover" class="summary-card">
        <p class="summary-label">净盈亏</p>
        <div class="summary-value" :class="pnlClass(completedSummary.net_pnl)">
          {{ formatSignedCurrency(completedSummary.net_pnl) }}
        </div>
        <p class="summary-meta">
          毛盈亏 {{ formatSignedCurrency(completedSummary.gross_realized_pnl) }}
          · 资金费 {{ formatSignedCurrency(completedSummary.funding_pnl) }}
        </p>
      </el-card>

      <el-card shadow="hover" class="summary-card">
        <p class="summary-label">手续费 / 平均每笔</p>
        <div class="summary-value summary-value-cost">
          -{{ formatCurrency(completedSummary.commission_cost) }}
        </div>
        <p class="summary-meta">平均每笔 {{ formatSignedCurrency(completedSummary.average_net_pnl) }}</p>
      </el-card>

      <el-card shadow="hover" class="summary-card">
        <p class="summary-label">持仓时长 / 盈亏因子</p>
        <div class="summary-value">{{ formatDuration(completedSummary.average_holding_minutes) }}</div>
        <p class="summary-meta">PF {{ completedSummary.profit_factor == null ? '暂无' : completedSummary.profit_factor.toFixed(2) }}</p>
      </el-card>
    </section>

    <el-row :gutter="20" class="content-grid">
      <el-col :xs="24" :lg="16">
        <el-card shadow="hover" class="timeline-card" v-loading="loading.completedTimeline">
          <template #header>
            <div class="section-header">
              <div>
                <span>完整交易净盈亏曲线</span>
                <p>以平仓时刻为落点，展示每笔完整交易的净盈亏和累计结果</p>
              </div>
              <el-tag type="success" effect="dark">Round Trip</el-tag>
            </div>
          </template>
          <div ref="timelineChartRef" class="timeline-chart"></div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card shadow="hover" class="notes-card">
          <template #header>
            <div class="section-header compact">
              <div>
                <span>复盘结论 / 标签</span>
                <p>二期会把标签、评分和日级复盘持久化到这里</p>
              </div>
            </div>
          </template>

          <div class="notes-placeholder">
            <el-empty description="先把完整交易看清，再补主观复盘记录。" />
            <div class="phase-two-tags">
              <el-tag>交易标签</el-tag>
              <el-tag>执行评分</el-tag>
              <el-tag>错误归因</el-tag>
              <el-tag>日级总结</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" class="history-card" v-loading="loading.completedTrades">
      <template #header>
        <div class="section-header">
          <div>
            <span>完整交易分析</span>
            <p>一行就是一笔完整交易，已经把开仓腿、平仓腿、手续费和资金费聚合好了</p>
          </div>
          <el-tag type="info" effect="plain">共 {{ completedTradeTotal }} 笔</el-tag>
        </div>
      </template>

      <el-table :data="completedTrades" border stripe @row-click="openCompletedTradeDrawer">
        <el-table-column prop="close_time" label="平仓时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.close_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="account_id" label="账户" min-width="120">
          <template #default="{ row }">
            {{ accountName(row.account_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="symbol" label="币种" min-width="120" />
        <el-table-column prop="direction" label="方向" width="110">
          <template #default="{ row }">
            <el-tag :type="row.direction === 'LONG' ? 'success' : 'danger'">
              {{ row.direction === 'LONG' ? '做多' : '做空' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="120">
          <template #default="{ row }">
            {{ formatNumber(row.quantity) }}
          </template>
        </el-table-column>
        <el-table-column prop="entry_avg_price" label="开仓均价" width="130">
          <template #default="{ row }">
            {{ formatNumber(row.entry_avg_price) }}
          </template>
        </el-table-column>
        <el-table-column prop="exit_avg_price" label="平仓均价" width="130">
          <template #default="{ row }">
            {{ formatNumber(row.exit_avg_price) }}
          </template>
        </el-table-column>
        <el-table-column prop="gross_realized_pnl" label="毛盈亏" width="140">
          <template #default="{ row }">
            <span :class="pnlClass(row.gross_realized_pnl)">{{ formatSignedCurrency(row.gross_realized_pnl) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="funding_pnl" label="资金费" width="130">
          <template #default="{ row }">
            <span :class="pnlClass(row.funding_pnl)">{{ formatSignedCurrency(row.funding_pnl) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="commission_cost" label="手续费" width="130">
          <template #default="{ row }">
            -{{ formatCurrency(row.commission_cost) }}
          </template>
        </el-table-column>
        <el-table-column prop="net_pnl" label="净盈亏" width="140">
          <template #default="{ row }">
            <span :class="pnlClass(row.net_pnl)">{{ formatSignedCurrency(row.net_pnl) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="max_floating_profit" label="最大浮盈" width="140">
          <template #default="{ row }">
            <span :class="pnlClass(row.max_floating_profit)">{{ formatSignedCurrency(row.max_floating_profit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="max_drawdown" label="最大回撤" width="140">
          <template #default="{ row }">
            <span class="pnl-negative">-{{ formatCurrency(row.max_drawdown) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="holding_minutes" label="持仓时长" width="140">
          <template #default="{ row }">
            {{ formatDuration(row.holding_minutes) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="completedTradePage"
          v-model:page-size="completedTradePageSize"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          :total="completedTradeTotal"
          @size-change="handleCompletedTradeSizeChange"
          @current-change="handleCompletedTradePageChange"
        />
      </div>
    </el-card>

    <el-card shadow="hover" class="raw-history-card" v-loading="loading.rawHistory">
      <template #header>
        <div class="section-header raw-header">
          <div>
            <span>原始流水辅助核对</span>
            <p>{{ rawScopeDescription }}</p>
          </div>
          <div class="raw-header-actions">
            <el-select v-model="rawFilters.type" clearable placeholder="全部类型" class="raw-type-select" @change="handleRawFilterChange">
              <el-option label="全部类型" value="" />
              <el-option
                v-for="option in historyTypeOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-radio-group v-model="recordScope" size="small" @change="handleRawFilterChange">
              <el-radio-button
                v-for="option in recordScopeOptions"
                :key="option.value"
                :label="option.value"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
            <el-tag type="info" effect="plain">{{ rawHistoryScopeLabel }} · {{ rawHistoryTotal }} 条</el-tag>
          </div>
        </div>
      </template>

      <el-table :data="rawHistoryData" border stripe>
        <el-table-column prop="time" label="时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.time) }}
          </template>
        </el-table-column>
        <el-table-column prop="account_id" label="账户" min-width="120">
          <template #default="{ row }">
            {{ accountName(row.account_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="symbol" label="币种" min-width="120">
          <template #default="{ row }">
            {{ row.symbol || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" min-width="130">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="side" label="方向" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.side" :type="row.side === 'BUY' ? 'success' : 'danger'" effect="plain">
              {{ row.side }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="position_side" label="持仓侧" width="100">
          <template #default="{ row }">
            {{ row.position_side || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="price" label="均价" width="130">
          <template #default="{ row }">
            {{ formatNumber(row.price) }}
          </template>
        </el-table-column>
        <el-table-column prop="qty" label="数量" width="120">
          <template #default="{ row }">
            {{ formatNumber(row.qty) }}
          </template>
        </el-table-column>
        <el-table-column prop="realized_pnl" label="已实现盈亏" width="150">
          <template #default="{ row }">
            <span :class="pnlClass(row.realized_pnl)">{{ formatSignedCurrency(row.realized_pnl) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="commission" label="手续费" width="140">
          <template #default="{ row }">
            <span v-if="row.commission">{{ formatNumber(row.commission) }} {{ row.commission_asset || '' }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="order_id" label="订单ID" min-width="140">
          <template #default="{ row }">
            {{ row.order_id || '-' }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="rawHistoryPage"
          v-model:page-size="rawHistoryPageSize"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          :total="rawHistoryTotal"
          @size-change="handleRawHistorySizeChange"
          @current-change="handleRawHistoryPageChange"
        />
      </div>
    </el-card>

    <el-drawer v-model="completedTradeDrawerVisible" title="完整交易详情" size="46%">
      <template v-if="selectedCompletedTrade">
        <div class="drawer-summary">
          <div>
            <p class="drawer-eyebrow">
              {{ selectedCompletedTrade.direction === 'LONG' ? 'BUY → SELL 做多' : 'SELL → BUY 做空' }}
            </p>
            <h3>{{ selectedCompletedTrade.symbol }}</h3>
            <p class="drawer-subtitle">{{ accountName(selectedCompletedTrade.account_id) }}</p>
          </div>
          <div class="drawer-tag-group">
            <el-tag :type="selectedCompletedTrade.direction === 'LONG' ? 'success' : 'danger'">
              {{ selectedCompletedTrade.direction === 'LONG' ? '做多' : '做空' }}
            </el-tag>
            <el-tag v-if="selectedCompletedTrade.position_side" type="info" effect="plain">
              {{ selectedCompletedTrade.position_side }}
            </el-tag>
          </div>
        </div>

        <el-descriptions :column="2" border class="detail-grid">
          <el-descriptions-item label="开仓时间">
            {{ formatDateTime(selectedCompletedTrade.open_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="平仓时间">
            {{ formatDateTime(selectedCompletedTrade.close_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="持仓时长">
            {{ formatDuration(selectedCompletedTrade.holding_minutes) }}
          </el-descriptions-item>
          <el-descriptions-item label="成交数量">
            {{ formatNumber(selectedCompletedTrade.quantity) }}
          </el-descriptions-item>
          <el-descriptions-item label="开仓均价">
            {{ formatNumber(selectedCompletedTrade.entry_avg_price) }}
          </el-descriptions-item>
          <el-descriptions-item label="平仓均价">
            {{ formatNumber(selectedCompletedTrade.exit_avg_price) }}
          </el-descriptions-item>
          <el-descriptions-item label="毛盈亏">
            <span :class="pnlClass(selectedCompletedTrade.gross_realized_pnl)">
              {{ formatSignedCurrency(selectedCompletedTrade.gross_realized_pnl) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="净盈亏">
            <span :class="pnlClass(selectedCompletedTrade.net_pnl)">
              {{ formatSignedCurrency(selectedCompletedTrade.net_pnl) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="手续费">
            -{{ formatCurrency(selectedCompletedTrade.commission_cost) }}
          </el-descriptions-item>
          <el-descriptions-item label="资金费">
            <span :class="pnlClass(selectedCompletedTrade.funding_pnl)">
              {{ formatSignedCurrency(selectedCompletedTrade.funding_pnl) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="最大浮盈">
            <span :class="pnlClass(selectedCompletedTrade.max_floating_profit)">
              {{ formatSignedCurrency(selectedCompletedTrade.max_floating_profit) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="最大回撤">
            <span class="pnl-negative">-{{ formatCurrency(selectedCompletedTrade.max_drawdown) }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-card shadow="never" class="detail-section-card">
          <template #header>
            <div class="section-header compact">
              <div>
                <span>持仓期间资金曲线</span>
                <p>左轴是这笔交易的净值路径，右轴叠加账户总权益，方便看持仓期内账户资金怎么走</p>
              </div>
              <div class="curve-header-tools">
                <el-radio-group v-model="holdingCurveMode" size="small">
                  <el-radio-button label="absolute">绝对值</el-radio-button>
                  <el-radio-button label="relative">相对起点%</el-radio-button>
                </el-radio-group>
                <el-tag :type="selectedCompletedTrade.price_sample_count ? 'success' : 'warning'" effect="plain">
                  价格采样 {{ selectedCompletedTrade.price_sample_count }} · 权益采样 {{ selectedCompletedTrade.account_equity_point_count }} · 曲线点 {{ selectedCompletedTrade.holding_curve_point_count }}
                </el-tag>
              </div>
            </div>
          </template>

          <el-alert
            v-if="selectedCompletedTrade.price_sample_count === 0"
            title="这笔交易缺少 ticker 历史采样，当前曲线按开平仓与资金费事件做了粗粒度重建。"
            type="warning"
            :closable="false"
            show-icon
            class="curve-alert"
          />

          <el-alert
            v-if="selectedCompletedTrade.account_equity_point_count === 0"
            title="这笔交易缺少 account snapshot 数据，当前图里暂时不会叠加账户总权益线。"
            type="info"
            :closable="false"
            show-icon
            class="curve-alert"
          />

          <div ref="holdingCurveChartRef" class="holding-curve-chart"></div>
        </el-card>

        <el-card shadow="never" class="detail-section-card">
          <template #header>
            <div class="section-header compact">
              <div>
                <span>开仓腿</span>
                <p>共 {{ selectedCompletedTrade.entry_order_count }} 笔开仓订单</p>
              </div>
            </div>
          </template>
          <el-table :data="selectedCompletedTrade.entry_orders" size="small" border>
            <el-table-column prop="time" label="时间" min-width="165">
              <template #default="{ row }">
                {{ formatDateTime(row.time) }}
              </template>
            </el-table-column>
            <el-table-column prop="order_id" label="订单ID" min-width="120" />
            <el-table-column prop="qty" label="数量" width="100">
              <template #default="{ row }">
                {{ formatNumber(row.qty) }}
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价格" width="110">
              <template #default="{ row }">
                {{ formatNumber(row.price) }}
              </template>
            </el-table-column>
            <el-table-column prop="commission" label="手续费" width="120">
              <template #default="{ row }">
                {{ formatNumber(row.commission) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="detail-section-card">
          <template #header>
            <div class="section-header compact">
              <div>
                <span>平仓腿</span>
                <p>共 {{ selectedCompletedTrade.exit_order_count }} 笔平仓订单</p>
              </div>
            </div>
          </template>
          <el-table :data="selectedCompletedTrade.exit_orders" size="small" border>
            <el-table-column prop="time" label="时间" min-width="165">
              <template #default="{ row }">
                {{ formatDateTime(row.time) }}
              </template>
            </el-table-column>
            <el-table-column prop="order_id" label="订单ID" min-width="120" />
            <el-table-column prop="qty" label="数量" width="100">
              <template #default="{ row }">
                {{ formatNumber(row.qty) }}
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价格" width="110">
              <template #default="{ row }">
                {{ formatNumber(row.price) }}
              </template>
            </el-table-column>
            <el-table-column prop="realized_pnl" label="毛盈亏" width="120">
              <template #default="{ row }">
                <span :class="pnlClass(row.realized_pnl)">{{ formatSignedCurrency(row.realized_pnl) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="detail-section-card">
          <template #header>
            <div class="section-header compact">
              <div>
                <span>资金费归集</span>
                <p>共 {{ selectedCompletedTrade.funding_event_count }} 条资金费流水被归到这笔完整交易</p>
              </div>
            </div>
          </template>
          <el-empty v-if="!selectedCompletedTrade.funding_items.length" description="这笔交易没有归集到资金费记录。" />
          <el-table v-else :data="selectedCompletedTrade.funding_items" size="small" border>
            <el-table-column prop="time" label="时间" min-width="165">
              <template #default="{ row }">
                {{ formatDateTime(row.time) }}
              </template>
            </el-table-column>
            <el-table-column prop="transaction_id" label="流水ID" min-width="140" />
            <el-table-column prop="amount" label="资金费" width="120">
              <template #default="{ row }">
                <span :class="pnlClass(row.amount)">{{ formatSignedCurrency(row.amount) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </template>
    </el-drawer>
  </div>
</template>

<script>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { useStore } from 'vuex'
import { riskControl } from '@/api'

const historyTypeOptions = [
  { label: '交易 (TRADE)', value: 'TRADE' },
  { label: '已实现盈亏 (REALIZED_PNL)', value: 'REALIZED_PNL' },
  { label: '资金费 (FUNDING_FEE)', value: 'FUNDING_FEE' },
  { label: '手续费 (COMMISSION)', value: 'COMMISSION' },
  { label: '划转 (TRANSFER)', value: 'TRANSFER' },
  { label: '内部划转 (INTERNAL_TRANSFER)', value: 'INTERNAL_TRANSFER' }
]

const recordScopeOptions = [
  { label: '成交流水', value: 'trades' },
  { label: '资金流水', value: 'cashflow' },
  { label: '全部复盘', value: 'review' }
]

const HOLDING_CURVE_MODE_STORAGE_KEY = 'trade-review-holding-curve-mode'

const createRecentDateRange = (days) => {
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - (days - 1))
  start.setHours(0, 0, 0, 0)
  return [start, end]
}

const createDefaultDateRange = () => createRecentDateRange(30)

const loadHoldingCurveMode = () => {
  if (typeof window === 'undefined') {
    return 'absolute'
  }

  const savedMode = window.localStorage.getItem(HOLDING_CURVE_MODE_STORAGE_KEY)
  return savedMode === 'relative' ? 'relative' : 'absolute'
}

const createEmptyCompletedSummary = () => ({
  total_count: 0,
  win_count: 0,
  loss_count: 0,
  win_rate: 0,
  gross_realized_pnl: 0,
  commission_cost: 0,
  funding_pnl: 0,
  net_pnl: 0,
  average_net_pnl: 0,
  average_holding_minutes: 0,
  profit_factor: null
})

const createEmptyRawSummary = () => ({
  total_count: 0,
  trade_count: 0,
  win_count: 0,
  loss_count: 0,
  win_rate: 0,
  gross_realized_pnl: 0,
  commission_cost: 0,
  funding_pnl: 0,
  transfer_amount: 0,
  net_trading_pnl: 0,
  average_trade_pnl: 0,
  profit_factor: null
})

export default {
  name: 'TradeReview',
  setup() {
    const store = useStore()
    const timelineChartRef = ref(null)
    const holdingCurveChartRef = ref(null)
    const completedTradeDrawerVisible = ref(false)
    const selectedCompletedTrade = ref(null)
    const holdingCurveMode = ref(loadHoldingCurveMode())
    const dateRange = ref(createDefaultDateRange())
    const completedTrades = ref([])
    const completedTradePage = ref(1)
    const completedTradePageSize = ref(20)
    const completedTradeTotal = ref(0)
    const rawHistoryData = ref([])
    const rawHistoryPage = ref(1)
    const rawHistoryPageSize = ref(20)
    const recordScope = ref('trades')
    const syncingHistory = ref(false)
    const loading = reactive({
      completedSummary: false,
      completedTimeline: false,
      completedTrades: false,
      rawSummary: false,
      rawHistory: false
    })
    const completedSummary = reactive(createEmptyCompletedSummary())
    const rawSummary = reactive(createEmptyRawSummary())
    const timelineData = reactive({
      xAxis: [],
      series: []
    })
    const filters = reactive({
      account_id: null,
      symbol: ''
    })
    const rawFilters = reactive({
      type: ''
    })

    const dateShortcuts = [
      {
        text: '近24小时',
        value: () => {
          const end = new Date()
          const start = new Date(end)
          start.setDate(end.getDate() - 1)
          return [start, end]
        }
      },
      {
        text: '近7天',
        value: () => createRecentDateRange(7)
      },
      {
        text: '近30天',
        value: () => createRecentDateRange(30)
      },
      {
        text: '近90天',
        value: () => createRecentDateRange(90)
      }
    ]

    const accounts = computed(() => store.state.accounts)
    const selectedHistoryAccount = computed(() => (
      accounts.value.find(account => account.id === filters.account_id) || null
    ))
    const hasCompleted90DayBackfill = computed(() => Boolean(selectedHistoryAccount.value?.history_90d_backfilled_at))
    const syncHistoryButtonText = computed(() => (
      hasCompleted90DayBackfill.value ? '90天历史已补' : '补90天历史'
    ))
    const isRefreshing = computed(() => Object.values(loading).some(Boolean))
    const rawHistoryScopeLabel = computed(() => {
      const option = recordScopeOptions.find(item => item.value === recordScope.value)
      return option ? option.label : '全部复盘'
    })
    const rawScopeDescription = computed(() => {
      if (rawFilters.type) {
        return `当前在原始流水层按 ${rawFilters.type} 过滤，用于核对完整交易聚合结果。`
      }
      if (recordScope.value === 'trades') {
        return '只看 TRADE 成交流水，用来核对完整交易里的开仓腿和平仓腿。'
      }
      if (recordScope.value === 'cashflow') {
        return '只看手续费、资金费、已实现盈亏和划转流水，用来核对净值变化。'
      }
      return '展示全部复盘相关流水，便于和完整交易结果对照。'
    })
    const rawHistoryTotal = computed(() => {
      if (rawFilters.type) {
        return rawSummary.total_count
      }
      if (recordScope.value === 'trades') {
        return rawSummary.trade_count
      }
      if (recordScope.value === 'cashflow') {
        return Math.max(rawSummary.total_count - rawSummary.trade_count, 0)
      }
      return rawSummary.total_count
    })

    let timelineChart = null
    let holdingCurveChart = null
    let resizeHandler = null

    const normalizeSymbol = () => {
      filters.symbol = (filters.symbol || '').trim().toUpperCase()
    }

    const buildBaseParams = () => {
      normalizeSymbol()
      const params = {}
      if (filters.account_id) {
        params.account_id = filters.account_id
      }
      if (filters.symbol) {
        params.symbol = filters.symbol
      }
      if (dateRange.value && dateRange.value.length === 2) {
        params.start_time = new Date(dateRange.value[0]).toISOString()
        params.end_time = new Date(dateRange.value[1]).toISOString()
      }
      return params
    }

    const buildRawHistoryParams = () => {
      const params = {
        ...buildBaseParams(),
        record_scope: rawFilters.type ? 'all' : recordScope.value,
        skip: (rawHistoryPage.value - 1) * rawHistoryPageSize.value,
        limit: rawHistoryPageSize.value
      }
      if (rawFilters.type) {
        params.type = rawFilters.type
      }
      return params
    }

    const buildRawSummaryParams = () => {
      const params = {
        ...buildBaseParams(),
        record_scope: rawFilters.type ? 'all' : 'review'
      }
      if (rawFilters.type) {
        params.type = rawFilters.type
      }
      return params
    }

    const accountName = (accountId) => {
      const account = store.getters.getAccountById(accountId)
      return account ? account.name : `#${accountId}`
    }

    const formatNumber = (value) => {
      if (value === null || value === undefined || value === '') {
        return '-'
      }
      return Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 })
    }

    const formatCurrency = (value) => {
      if (value === null || value === undefined) {
        return '-'
      }
      return Number(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      })
    }

    const formatSignedCurrency = (value) => {
      const amount = Number(value || 0)
      const sign = amount > 0 ? '+' : ''
      return `${sign}${formatCurrency(amount)}`
    }

    const formatPercent = (value) => {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '-'
      }
      return `${Number(value).toFixed(2)}%`
    }

    const formatSignedPercent = (value) => {
      const amount = Number(value || 0)
      const sign = amount > 0 ? '+' : ''
      return `${sign}${formatPercent(amount)}`
    }

    const formatDateTime = (value) => {
      if (!value) {
        return '-'
      }
      return new Date(value).toLocaleString()
    }

    const formatDuration = (minutes) => {
      const totalMinutes = Number(minutes || 0)
      if (!totalMinutes) {
        return '0m'
      }
      if (totalMinutes < 60) {
        return `${Math.round(totalMinutes)}m`
      }
      const hours = Math.floor(totalMinutes / 60)
      const remainMinutes = Math.round(totalMinutes % 60)
      if (!remainMinutes) {
        return `${hours}h`
      }
      return `${hours}h ${remainMinutes}m`
    }

    const pnlClass = (value) => {
      const amount = Number(value || 0)
      if (amount > 0) {
        return 'pnl-positive'
      }
      if (amount < 0) {
        return 'pnl-negative'
      }
      return ''
    }

    const typeTagType = (value) => {
      const map = {
        TRADE: '',
        REALIZED_PNL: 'success',
        FUNDING_FEE: 'warning',
        COMMISSION: 'info',
        TRANSFER: 'danger',
        INTERNAL_TRANSFER: 'danger'
      }
      return map[value] || 'info'
    }

    const ensureTimelineChart = async () => {
      await nextTick()
      if (!timelineChartRef.value) {
        return
      }
      if (!timelineChart) {
        timelineChart = echarts.init(timelineChartRef.value)
      }
      if (!resizeHandler) {
        resizeHandler = () => {
          if (timelineChart) {
            timelineChart.resize()
          }
          if (holdingCurveChart) {
            holdingCurveChart.resize()
          }
        }
        window.addEventListener('resize', resizeHandler)
      }
    }

    const ensureHoldingCurveChart = async () => {
      await nextTick()
      if (!holdingCurveChartRef.value) {
        return
      }
      if (!holdingCurveChart) {
        holdingCurveChart = echarts.init(holdingCurveChartRef.value)
      }
      if (!resizeHandler) {
        resizeHandler = () => {
          if (timelineChart) {
            timelineChart.resize()
          }
          if (holdingCurveChart) {
            holdingCurveChart.resize()
          }
        }
        window.addEventListener('resize', resizeHandler)
      }
    }

    const renderTimelineChart = async () => {
      await ensureTimelineChart()
      if (!timelineChart) {
        return
      }

      const [periodSeries, cumulativeSeries, tradeSeries] = timelineData.series
      const hasData = timelineData.xAxis.length > 0

      timelineChart.setOption({
        color: ['#d97706', '#155eef', '#0f766e'],
        tooltip: { trigger: 'axis' },
        legend: { top: 0 },
        grid: { left: 20, right: 20, bottom: 20, top: 44, containLabel: true },
        xAxis: {
          type: 'category',
          data: timelineData.xAxis,
          boundaryGap: true
        },
        yAxis: [
          {
            type: 'value',
            name: '净盈亏'
          },
          {
            type: 'value',
            name: '平仓笔数',
            splitLine: { show: false }
          }
        ],
        graphic: hasData ? [] : [{
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '当前筛选下暂无完整交易数据',
            fill: '#98a2b3',
            fontSize: 14
          }
        }],
        series: [
          {
            ...(periodSeries || { name: '单笔净盈亏', type: 'bar', data: [] }),
            barMaxWidth: 24,
            itemStyle: {
              borderRadius: [6, 6, 0, 0]
            }
          },
          {
            ...(cumulativeSeries || { name: '累计净盈亏', type: 'line', data: [] }),
            smooth: true,
            symbolSize: 6,
            areaStyle: {
              color: 'rgba(21, 94, 239, 0.12)'
            }
          },
          {
            ...(tradeSeries || { name: '平仓笔数', type: 'line', data: [] }),
            yAxisIndex: 1,
            smooth: true,
            symbolSize: 6,
            lineStyle: {
              width: 2
            }
          }
        ]
      })
    }

    const describeCurveEventType = (value) => {
      const labelMap = {
        entry: '开仓',
        exit: '平仓',
        funding: '资金费',
        mark: '价格采样'
      }
      return labelMap[value] || value || '-'
    }

    const findLatestPointBefore = (points, axisValue, accessor = 'time') => {
      if (!points.length || !axisValue) {
        return null
      }

      const targetTs = new Date(axisValue).getTime()
      let latestPoint = null
      for (const point of points) {
        const pointTs = new Date(point[accessor]).getTime()
        if (pointTs <= targetTs) {
          latestPoint = point
          continue
        }
        break
      }

      return latestPoint || points[0]
    }

    const buildHoldingCurveSeries = (curvePoints, accountEquityPoints) => {
      const baseEquity = Number(accountEquityPoints?.[0]?.total_equity || 0)
      const isRelativeMode = holdingCurveMode.value === 'relative' && baseEquity > 0

      const tradeNetSeries = curvePoints.map((point) => {
        const value = isRelativeMode ? (Number(point.net_pnl || 0) / baseEquity) * 100 : Number(point.net_pnl || 0)
        return [point.time, Number(value.toFixed(4))]
      })
      const tradeFloatingSeries = curvePoints.map((point) => {
        const value = isRelativeMode ? (Number(point.unrealized_pnl || 0) / baseEquity) * 100 : Number(point.unrealized_pnl || 0)
        return [point.time, Number(value.toFixed(4))]
      })
      const accountEquitySeries = accountEquityPoints.map((point) => {
        const absoluteEquity = Number(point.total_equity || 0)
        const value = isRelativeMode ? ((absoluteEquity - baseEquity) / baseEquity) * 100 : absoluteEquity
        return [point.time, Number(value.toFixed(4))]
      })

      return {
        baseEquity,
        isRelativeMode,
        tradeNetSeries,
        tradeFloatingSeries,
        accountEquitySeries
      }
    }

    const renderHoldingCurveChart = async () => {
      if (!completedTradeDrawerVisible.value || !selectedCompletedTrade.value) {
        return
      }

      await ensureHoldingCurveChart()
      if (!holdingCurveChart) {
        return
      }

      const curvePoints = selectedCompletedTrade.value.holding_curve || []
      const accountEquityPoints = selectedCompletedTrade.value.account_equity_curve || []
      const hasData = curvePoints.length > 0 || accountEquityPoints.length > 0
      const {
        baseEquity,
        isRelativeMode,
        tradeNetSeries,
        tradeFloatingSeries,
        accountEquitySeries
      } = buildHoldingCurveSeries(curvePoints, accountEquityPoints)

      holdingCurveChart.setOption({
        color: ['#0f766e', '#155eef', '#f59e0b'],
        tooltip: {
          trigger: 'axis',
          formatter: (params) => {
            const axisValue = params?.[0]?.axisValue || params?.[0]?.value?.[0]
            const tradePoint = findLatestPointBefore(curvePoints, axisValue)
            const accountPoint = findLatestPointBefore(accountEquityPoints, axisValue)
            const lines = [`<div>${formatDateTime(axisValue)}</div>`]

            if (tradePoint) {
              lines.push(`<div>事件：${describeCurveEventType(tradePoint.event_type)}</div>`)
              if (isRelativeMode && baseEquity > 0) {
                lines.push(`<div>交易净值：${formatSignedPercent((Number(tradePoint.net_pnl || 0) / baseEquity) * 100)} (${formatSignedCurrency(tradePoint.net_pnl)})</div>`)
                lines.push(`<div>浮动盈亏：${formatSignedPercent((Number(tradePoint.unrealized_pnl || 0) / baseEquity) * 100)} (${formatSignedCurrency(tradePoint.unrealized_pnl)})</div>`)
              } else {
                lines.push(`<div>交易净值：${formatSignedCurrency(tradePoint.net_pnl)}</div>`)
                lines.push(`<div>浮动盈亏：${formatSignedCurrency(tradePoint.unrealized_pnl)}</div>`)
              }
              lines.push(`<div>持仓数量：${formatNumber(tradePoint.open_qty)}</div>`)
              if (tradePoint.price !== null && tradePoint.price !== undefined) {
                lines.push(`<div>价格：${formatNumber(tradePoint.price)}</div>`)
              }
            }

            if (accountPoint) {
              if (isRelativeMode && baseEquity > 0) {
                lines.push(`<div>账户权益：${formatSignedPercent(((Number(accountPoint.total_equity || 0) - baseEquity) / baseEquity) * 100)} (${formatCurrency(accountPoint.total_equity)})</div>`)
              } else {
                lines.push(`<div>账户权益：${formatCurrency(accountPoint.total_equity)}</div>`)
              }
              lines.push(`<div>账户余额：${formatCurrency(accountPoint.total_balance)}</div>`)
            }
            return lines.join('')
          }
        },
        legend: { top: 0 },
        grid: { left: 20, right: 20, bottom: 20, top: 44, containLabel: true },
        xAxis: {
          type: 'time'
        },
        yAxis: isRelativeMode
          ? {
              type: 'value',
              name: '相对起点%'
            }
          : [
              {
                type: 'value',
                name: '交易净值'
              },
              {
                type: 'value',
                name: '账户权益',
                splitLine: { show: false }
              }
            ],
        graphic: hasData ? [] : [{
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '当前交易暂无可重建的持仓曲线',
            fill: '#98a2b3',
            fontSize: 14
          }
        }],
        series: [
          {
            name: '交易净值',
            type: 'line',
            smooth: true,
            showSymbol: false,
            areaStyle: {
              color: 'rgba(15, 118, 110, 0.12)'
            },
            data: tradeNetSeries
          },
          {
            name: '浮动盈亏',
            type: 'line',
            smooth: true,
            showSymbol: false,
            yAxisIndex: isRelativeMode ? 0 : 0,
            lineStyle: {
              type: 'dashed',
              width: 2
            },
            data: tradeFloatingSeries
          },
          {
            name: '账户权益',
            type: 'line',
            yAxisIndex: isRelativeMode ? 0 : 1,
            smooth: true,
            showSymbol: false,
            lineStyle: {
              width: 2
            },
            data: accountEquitySeries
          }
        ]
      })
    }

    const fetchCompletedSummary = async () => {
      loading.completedSummary = true
      try {
        const data = await riskControl.getCompletedTradeSummary(buildBaseParams())
        Object.assign(completedSummary, createEmptyCompletedSummary(), data)
      } catch (error) {
        console.error('Failed to fetch completed trade summary:', error)
        Object.assign(completedSummary, createEmptyCompletedSummary())
        ElMessage.error('获取完整交易概览失败')
      } finally {
        loading.completedSummary = false
      }
    }

    const fetchCompletedTimeline = async () => {
      loading.completedTimeline = true
      try {
        const data = await riskControl.getCompletedTradeTimeline(buildBaseParams())
        timelineData.xAxis = data.xAxis || []
        timelineData.series = data.series || []
        await renderTimelineChart()
      } catch (error) {
        console.error('Failed to fetch completed trade timeline:', error)
        timelineData.xAxis = []
        timelineData.series = []
        await renderTimelineChart()
        ElMessage.error('获取完整交易曲线失败')
      } finally {
        loading.completedTimeline = false
      }
    }

    const fetchCompletedTrades = async () => {
      loading.completedTrades = true
      try {
        const data = await riskControl.getCompletedTrades({
          ...buildBaseParams(),
          skip: (completedTradePage.value - 1) * completedTradePageSize.value,
          limit: completedTradePageSize.value
        })
        completedTrades.value = data.items || []
        completedTradeTotal.value = data.total || 0
      } catch (error) {
        console.error('Failed to fetch completed trades:', error)
        completedTrades.value = []
        completedTradeTotal.value = 0
        ElMessage.error('获取完整交易明细失败')
      } finally {
        loading.completedTrades = false
      }
    }

    const fetchRawSummary = async () => {
      loading.rawSummary = true
      try {
        const data = await riskControl.getTransactionReviewSummary(buildRawSummaryParams())
        Object.assign(rawSummary, createEmptyRawSummary(), data)
      } catch (error) {
        console.error('Failed to fetch raw history summary:', error)
        Object.assign(rawSummary, createEmptyRawSummary())
        ElMessage.error('获取原始流水统计失败')
      } finally {
        loading.rawSummary = false
      }
    }

    const fetchRawHistory = async () => {
      loading.rawHistory = true
      try {
        rawHistoryData.value = await riskControl.getTransactionHistory(buildRawHistoryParams())
      } catch (error) {
        console.error('Failed to fetch raw history:', error)
        rawHistoryData.value = []
        ElMessage.error('获取原始流水失败')
      } finally {
        loading.rawHistory = false
      }
    }

    const refreshAll = async ({ resetPage = false } = {}) => {
      if (resetPage) {
        completedTradePage.value = 1
        rawHistoryPage.value = 1
      }
      await Promise.all([
        fetchCompletedSummary(),
        fetchCompletedTimeline(),
        fetchCompletedTrades(),
        fetchRawSummary(),
        fetchRawHistory()
      ])
    }

    const resetFilters = async () => {
      filters.account_id = null
      filters.symbol = ''
      rawFilters.type = ''
      recordScope.value = 'trades'
      dateRange.value = createDefaultDateRange()
      await refreshAll({ resetPage: true })
    }

    const handleCompletedTradeSizeChange = async (value) => {
      completedTradePageSize.value = value
      completedTradePage.value = 1
      await fetchCompletedTrades()
    }

    const handleCompletedTradePageChange = async (value) => {
      completedTradePage.value = value
      await fetchCompletedTrades()
    }

    const handleRawHistorySizeChange = async (value) => {
      rawHistoryPageSize.value = value
      rawHistoryPage.value = 1
      await fetchRawHistory()
    }

    const handleRawHistoryPageChange = async (value) => {
      rawHistoryPage.value = value
      await fetchRawHistory()
    }

    const handleRawFilterChange = async () => {
      rawHistoryPage.value = 1
      await Promise.all([fetchRawSummary(), fetchRawHistory()])
    }

    const openCompletedTradeDrawer = (row) => {
      selectedCompletedTrade.value = row
      completedTradeDrawerVisible.value = true
    }

    watch(
      () => completedTradeDrawerVisible.value,
      async (visible) => {
        if (visible) {
          await renderHoldingCurveChart()
        }
      }
    )

    watch(
      () => selectedCompletedTrade.value,
      async (trade) => {
        if (trade && completedTradeDrawerVisible.value) {
          await renderHoldingCurveChart()
        }
      }
    )

    watch(
      () => holdingCurveMode.value,
      async (mode) => {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(HOLDING_CURVE_MODE_STORAGE_KEY, mode)
        }
        if (completedTradeDrawerVisible.value && selectedCompletedTrade.value) {
          await renderHoldingCurveChart()
        }
      }
    )

    const syncHistory = async () => {
      if (!filters.account_id) {
        ElMessage.warning('请先选择一个账户')
        return
      }
      if (hasCompleted90DayBackfill.value) {
        ElMessage.warning('当前账户已经完成过一次 90 天历史回补')
        return
      }
      try {
        await ElMessageBox.confirm(
          '90 天历史回补按账号只允许执行一次，确认现在开始补数？',
          '确认 90 天补数',
          {
            type: 'warning',
            confirmButtonText: '开始补数',
            cancelButtonText: '取消'
          }
        )
      } catch {
        return
      }
      syncingHistory.value = true
      try {
        const result = await riskControl.syncAccountHistory(filters.account_id, 90)
        ElMessage.success(result.message || '90天历史回补完成')
        await store.dispatch('fetchAccounts')
        await refreshAll({ resetPage: true })
      } catch (error) {
        console.error('Failed to sync account history:', error)
        ElMessage.error(error.response?.data?.detail || '回补账户历史失败')
      } finally {
        syncingHistory.value = false
      }
    }

    onMounted(async () => {
      try {
        if (!accounts.value.length) {
          await store.dispatch('fetchAccounts')
        }
      } catch (error) {
        console.error('Failed to fetch accounts for trade review:', error)
      }
      await renderTimelineChart()
      await refreshAll({ resetPage: true })
    })

    onBeforeUnmount(() => {
      if (resizeHandler) {
        window.removeEventListener('resize', resizeHandler)
        resizeHandler = null
      }
      if (timelineChart) {
        timelineChart.dispose()
        timelineChart = null
      }
      if (holdingCurveChart) {
        holdingCurveChart.dispose()
        holdingCurveChart = null
      }
    })

    return {
      accounts,
      completedSummary,
      completedTradeDrawerVisible,
      completedTradePage,
      completedTradePageSize,
      completedTradeTotal,
      completedTrades,
      dateRange,
      dateShortcuts,
      filters,
      formatCurrency,
      formatDateTime,
      formatDuration,
      formatNumber,
      formatSignedCurrency,
      formatPercent,
      handleCompletedTradePageChange,
      handleCompletedTradeSizeChange,
      handleRawFilterChange,
      handleRawHistoryPageChange,
      handleRawHistorySizeChange,
      hasCompleted90DayBackfill,
      historyTypeOptions,
      holdingCurveChartRef,
      holdingCurveMode,
      isRefreshing,
      loading,
      normalizeSymbol,
      openCompletedTradeDrawer,
      pnlClass,
      rawFilters,
      rawHistoryData,
      rawHistoryPage,
      rawHistoryPageSize,
      rawHistoryScopeLabel,
      rawHistoryTotal,
      rawScopeDescription,
      recordScope,
      recordScopeOptions,
      refreshAll,
      resetFilters,
      selectedCompletedTrade,
      selectedHistoryAccount,
      syncingHistory,
      syncHistoryButtonText,
      syncHistory,
      timelineChartRef,
      typeTagType,
      accountName
    }
  }
}
</script>

<style lang="scss" scoped>
.trade-review {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.review-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 28px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.4), transparent 35%),
    linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0f766e 100%);
  color: #f8fafc;

  h1 {
    margin: 8px 0 10px;
    font-size: 34px;
    line-height: 1.1;
  }
}

.eyebrow,
.drawer-eyebrow {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: rgba(248, 250, 252, 0.72);
}

.drawer-eyebrow {
  color: #667085;
}

.hero-copy,
.drawer-subtitle {
  max-width: 720px;
  margin: 0;
  color: rgba(248, 250, 252, 0.84);
  line-height: 1.6;
}

.drawer-subtitle {
  margin-top: 8px;
  color: #667085;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-card,
.timeline-card,
.notes-card,
.history-card,
.raw-history-card {
  border-radius: 20px;
}

.filter-grid {
  display: grid;
  gap: 16px;
}

.filter-grid-main {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-item-wide {
  grid-column: span 1;
}

.filter-label,
.summary-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #667085;
}

.filter-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}

.filter-hints,
.raw-header-actions,
.drawer-tag-group {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.curve-header-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
}

.summary-card {
  border-radius: 18px;

  :deep(.el-card__body) {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
}

.summary-card-primary {
  background: linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%);
  border: 1px solid rgba(21, 94, 239, 0.12);
}

.summary-value {
  font-size: 28px;
  font-weight: 700;
  color: #101828;
}

.summary-value-cost {
  color: #b42318;
}

.summary-meta {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: #667085;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  span {
    font-size: 16px;
    font-weight: 600;
    color: #101828;
  }

  p {
    margin: 4px 0 0;
    font-size: 13px;
    color: #667085;
  }
}

.section-header.compact {
  align-items: flex-start;
}

.raw-header {
  align-items: flex-start;
}

.timeline-chart {
  height: 340px;
}

.holding-curve-chart {
  height: 280px;
}

.notes-placeholder {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.curve-alert {
  margin-bottom: 16px;
}

.phase-two-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

.drawer-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;

  h3 {
    margin: 6px 0 0;
    font-size: 24px;
    color: #101828;
  }
}

.detail-grid,
.detail-section-card {
  margin-bottom: 18px;
}

.detail-section-card {
  border-radius: 18px;
  background: #f8fafc;
}

.raw-type-select {
  width: 180px;
}

.pnl-positive {
  color: #027a48;
}

.pnl-negative {
  color: #b42318;
}

@media (max-width: 1280px) {
  .summary-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .filter-grid-main {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .review-hero,
  .filter-foot,
  .section-header,
  .raw-header {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid,
  .filter-grid-main {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .review-hero {
    padding: 20px;

    h1 {
      font-size: 28px;
    }
  }

  .summary-grid,
  .filter-grid-main {
    grid-template-columns: 1fr;
  }

  .timeline-chart {
    height: 300px;
  }

  .raw-type-select {
    width: 100%;
  }
}
</style>