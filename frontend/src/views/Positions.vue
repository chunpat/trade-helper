<template>
  <div class="positions">
    <h1>持仓管理</h1>
    <div class="page-content">
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
      <el-table :data="positions" style="width: 100%">
        <el-table-column prop="id" label="#" width="60"></el-table-column>
        <el-table-column prop="symbol" label="Symbol" width="120"></el-table-column>
        <el-table-column prop="position_side" label="Side" width="100">
          <template #default="{ row }">
            <el-tag type="info" v-if="row.position_side">{{ row.position_side }}</el-tag>
            <span v-else>NET</span>
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
        <el-table-column prop="risk_level" label="Risk" width="120"></el-table-column>
        <el-table-column prop="updated_at" label="Updated" width="200"></el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Positions',
  data () {
    return {
      selectedAccount: null
    }
  },
  computed: {
    positions () { return this.$store.state.positions },
    accounts () { return this.$store.state.accounts }
  },
  async mounted () {
    // fetch positions on mount
      try {
        await this.$store.dispatch('fetchAccounts')
        await this.loadPositions()
      } catch (e) {
        console.error('failed fetch positions', e)
      }
  },
  methods: {
    accountName(id) {
      const acct = this.$store.getters.getAccountById(id)
      return acct ? acct.name : `#${id}`
    },
    async loadPositions () {
      const params = this.selectedAccount ? { account_id: this.selectedAccount } : {}
      await this.$store.dispatch('fetchPositions', params)
    },
    async onAccountChange () {
      await this.loadPositions()
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

.el-tag.type-info {
  background: #edf7ff;
  color: #409eff;
  border: 1px solid rgba(64,158,255,0.15);
}
</style>
