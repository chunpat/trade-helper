<template>
  <div class="positions">
    <h1>持仓管理</h1>
    <div class="page-content">
      <el-tabs v-model="activeTab">
        <!-- Active Positions Tab -->
        <el-tab-pane label="当前持仓" name="active">
          <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px">
            <div style="display:flex; align-items:center; gap:8px">
              <el-select v-model="selectedAccount" placeholder="All accounts" clearable @change="onAccountChange" style="min-width:240px">
                <el-option label="All accounts" :value="null"></el-option>
                <el-option v-for="acct in accounts" :key="acct.id" :label="acct.name" :value="acct.id"></el-option>
              </el-select>
              <el-button type="primary" @click="refreshPositions">刷新</el-button>
              <el-button type="success" @click="manualSyncAll">手动 Sync 全部</el-button>
              <el-button type="warning" @click="manualSyncAccount" :disabled="!selectedAccount">手动 Sync 选中账户</el-button>
            </div>
            <div>
              <small>显示持仓（LONG / SHORT 单独显示）</small>
            </div>
          </div>
          <el-table :data="positions" style="width: 100%" v-loading="loadingPositions">
            <el-table-column prop="id" label="#" width="60"></el-table-column>
            <el-table-column prop="symbol" label="Symbol" width="120"></el-table-column>
            <el-table-column prop="position_side" label="Side" width="100">
              <template #default="{ row }">
                <el-tag :type="row.position_side === 'LONG' ? 'success' : (row.position_side === 'SHORT' ? 'danger' : 'info')">
                  {{ row.position_side || 'NET' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="account_id" label="Account" width="150">
              <template #default="{ row }">
                <span>{{ accountName(row.account_id) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="size" label="Size" width="120"></el-table-column>
            <el-table-column prop="entry_price" label="Entry" width="140"></el-table-column>
            <el-table-column prop="current_price" label="Current" width="140"></el-table-column>
            <el-table-column prop="unrealized_pnl" label="Unrealized PnL" width="160">
              <template #default="{ row }">
                <span :class="row.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'">{{ row.unrealized_pnl }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="risk_level" label="Risk" width="120">
              <template #default="{ row }">
                <el-tag :type="getRiskLevelType(row.risk_level)">{{ row.risk_level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="updated_at" label="Updated" width="180">
              <template #default="{ row }">
                {{ formatDate(row.updated_at) }}
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- History Tab -->
        <el-tab-pane label="历史订单/资金费" name="history">
          <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap: wrap;">
              <el-select v-model="historyFilters.account_id" placeholder="选择账户" clearable @change="fetchHistory" style="width:200px">
                <el-option v-for="acct in accounts" :key="acct.id" :label="acct.name" :value="acct.id"></el-option>
              </el-select>
              <el-input v-model="historyFilters.symbol" placeholder="Symbol (e.g. BTCUSDT)" style="width: 180px" clearable @clear="fetchHistory" @keyup.enter="fetchHistory" />
              <el-select v-model="historyFilters.type" placeholder="类型" clearable @change="fetchHistory" style="width: 150px">
                <el-option label="全部" value="" />
                <el-option label="交易 (TRADE)" value="TRADE" />
                <el-option label="资金费 (FUNDING_FEE)" value="FUNDING_FEE" />
                <el-option label="已实现盈亏 (REALIZED_PNL)" value="REALIZED_PNL" />
                <el-option label="佣金 (COMMISSION)" value="COMMISSION" />
                <el-option label="划转 (TRANSFER)" value="TRANSFER" />
              </el-select>
              <el-button type="primary" @click="fetchHistory">查询</el-button>
              <el-button type="success" @click="syncHistory" :disabled="!historyFilters.account_id" :loading="syncingHistory">
                同步最新历史
              </el-button>
            </div>
          </div>

          <el-table :data="historyData" style="width: 100%" v-loading="loadingHistory" border>
            <el-table-column prop="time" label="时间" width="180">
              <template #default="{ row }">
                {{ formatDate(row.time) }}
              </template>
            </el-table-column>
            <el-table-column prop="account_id" label="账户" width="120">
              <template #default="{ row }">
                <span>{{ accountName(row.account_id) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="symbol" label="Symbol" width="120"></el-table-column>
            <el-table-column prop="type" label="类型" width="150">
              <template #default="{ row }">
                <el-tag :type="getHistoryTypeTag(row.type)">{{ row.type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="side" label="方向" width="80">
               <template #default="{ row }">
                <span v-if="row.side" :class="row.side === 'BUY' ? 'text-success' : 'text-danger'">{{ row.side }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价格" width="120">
              <template #default="{ row }">
                {{ row.price ? row.price : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="qty" label="数量" width="120">
              <template #default="{ row }">
                {{ row.qty ? row.qty : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="realized_pnl" label="变动金额/PnL" width="150">
              <template #default="{ row }">
                <span :class="row.realized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'">
                  {{ row.realized_pnl }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="commission" label="手续费" width="120">
              <template #default="{ row }">
                <span v-if="row.commission">{{ row.commission }} {{ row.commission_asset }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
          
          <div class="pagination" style="margin-top: 20px; display: flex; justify-content: flex-end;">
            <el-pagination
              v-model:current-page="historyPage"
              v-model:page-size="historyPageSize"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              :total="historyTotal"
              @size-change="handleHistorySizeChange"
              @current-change="handleHistoryPageChange"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script>
import { riskControl } from '@/api'

export default {
  name: 'Positions',
  data () {
    return {
      activeTab: 'active',
      selectedAccount: null,
      loadingPositions: false,
      
      // History Data
      historyData: [],
      loadingHistory: false,
      syncingHistory: false,
      historyFilters: {
        account_id: null,
        symbol: '',
        type: ''
      },
      historyPage: 1,
      historyPageSize: 20,
      historyTotal: 0
    }
  },
  computed: {
    positions () { return this.$store.state.positions },
    accounts () { return this.$store.state.accounts }
  },
  async mounted () {
    try {
      await this.$store.dispatch('fetchAccounts')
      await this.loadPositions()
      // Optionally load history if an account is selected or just load all
      this.fetchHistory()
    } catch (e) {
      console.error('failed fetch positions', e)
    }
  },
  methods: {
    accountName(id) {
      const acct = this.$store.getters.getAccountById(id)
      return acct ? acct.name : `#${id}`
    },
    formatDate(dateStr) {
      if (!dateStr) return '-'
      return new Date(dateStr).toLocaleString()
    },
    getRiskLevelType(level) {
      const map = {
        low: 'info',
        medium: 'warning',
        high: 'danger',
        critical: 'danger'
      }
      return map[level] || 'info'
    },
    
    // Positions Logic
    async loadPositions () {
      this.loadingPositions = true
      try {
        const params = this.selectedAccount ? { account_id: this.selectedAccount } : {}
        await this.$store.dispatch('fetchPositions', params)
      } finally {
        this.loadingPositions = false
      }
    },
    async onAccountChange () {
      await this.loadPositions()
      // Also update history filter if user wants consistency, but let's keep them separate for flexibility
      // this.historyFilters.account_id = this.selectedAccount
      // this.fetchHistory()
    },
    async refreshPositions () {
      await this.loadPositions()
    },
    async manualSyncAll () {
      try {
        await this.$store.dispatch('triggerSyncPositions')
        await this.loadPositions()
        this.$message.success('全量同步已触发并刷新')
      } catch (e) {
        console.error(e)
        this.$message.error('触发全量同步失败')
      }
    },
    async manualSyncAccount () {
      if (!this.selectedAccount) return
      try {
        await this.$store.dispatch('triggerAccountSync', this.selectedAccount)
        await this.loadPositions()
        this.$message.success('选中账户同步已触发并刷新')
      } catch (e) {
        console.error(e)
        this.$message.error('触发账户同步失败')
      }
    },

    // History Logic
    async fetchHistory() {
      this.loadingHistory = true
      try {
        const params = {
          skip: (this.historyPage - 1) * this.historyPageSize,
          limit: this.historyPageSize,
          ...this.historyFilters
        }
        // Clean empty params
        if (!params.account_id) delete params.account_id
        if (!params.symbol) delete params.symbol
        if (!params.type) delete params.type

        const data = await riskControl.getTransactionHistory(params)
        this.historyData = data
        
        // Mock total count for now as API doesn't return it yet
        if (data.length === this.historyPageSize) {
            this.historyTotal = this.historyPage * this.historyPageSize + this.historyPageSize
        } else {
            this.historyTotal = (this.historyPage - 1) * this.historyPageSize + data.length
        }
      } catch (error) {
        console.error('Failed to fetch history:', error)
        this.$message.error('获取历史记录失败')
      } finally {
        this.loadingHistory = false
      }
    },
    async syncHistory() {
      if (!this.historyFilters.account_id) {
        this.$message.warning('请先选择一个账户')
        return
      }
      this.syncingHistory = true
      try {
        await riskControl.syncAccountHistory(this.historyFilters.account_id)
        this.$message.success('同步成功')
        this.fetchHistory()
      } catch (error) {
        console.error('Sync history failed:', error)
        this.$message.error('同步失败: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.syncingHistory = false
      }
    },
    handleHistorySizeChange(val) {
      this.historyPageSize = val
      this.fetchHistory()
    },
    handleHistoryPageChange(val) {
      this.historyPage = val
      this.fetchHistory()
    },
    getHistoryTypeTag(type) {
      const map = {
        'TRADE': '',
        'FUNDING_FEE': 'warning',
        'REALIZED_PNL': 'success',
        'COMMISSION': 'info',
        'TRANSFER': 'info'
      }
      return map[type] || 'info'
    }
  }
}
</script>

<style scoped>
.positions {
  padding: 20px;
}

.page-content {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.pnl-positive {
  color: #0f9d58; /* green */
  font-weight: 600;
}
.pnl-negative {
  color: #db4437; /* red */
  font-weight: 600;
}

.text-success {
  color: #0f9d58;
}
.text-danger {
  color: #db4437;
}

.el-tag.type-info {
  background: #edf7ff;
  color: #409eff;
  border: 1px solid rgba(64,158,255,0.15);
}
</style>
