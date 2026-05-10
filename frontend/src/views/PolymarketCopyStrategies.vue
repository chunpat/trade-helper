<template>
  <div class="polymarket-copy-page">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">Polymarket Copy Trading</p>
        <h1>同比例跟单策略</h1>
        <p class="hero-copy">
          第一版只做单源钱包 dry-run。开仓和加仓按源单成交额乘 copy ratio，减仓和平仓按源仓位变化比例同步。
        </p>
      </div>
      <div class="hero-actions">
        <el-button plain :loading="loadingRunnerStatus" @click="loadRunnerStatus">刷新 runner 状态</el-button>
        <el-button type="primary" :loading="loadingStrategies" @click="loadStrategies">刷新策略列表</el-button>
      </div>
    </section>

    <el-row :gutter="16" class="top-grid">
      <el-col :xs="24" :lg="10">
        <el-card shadow="hover" class="detail-card">
          <template #header>
            <div class="card-header">
              <span>创建策略</span>
              <el-tag size="small" type="info">默认同比例 dry-run</el-tag>
            </div>
          </template>

          <el-form label-position="top" :model="form" class="strategy-form">
            <el-form-item label="策略名称">
              <el-input v-model="form.strategy_name" placeholder="例如：跟单 Bee 钱包 0.1 倍" />
            </el-form-item>
            <el-form-item label="源钱包地址">
              <el-input v-model="form.source_wallet" placeholder="0x..." />
            </el-form-item>

            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="copy ratio">
                  <el-input-number v-model="form.copy_ratio" :min="0.01" :max="1" :step="0.05" :precision="2" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="最小跟单额">
                  <el-input-number v-model="form.min_copy_order_usdc" :min="0" :step="5" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="单笔上限">
                  <el-input-number v-model="form.max_order_usdc" :min="1" :step="10" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="单市场暴露上限">
                  <el-input-number v-model="form.max_market_exposure_usdc" :min="1" :step="50" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="runner 回看小时数">
                  <el-input-number v-model="form.runner_lookback_hours" :min="1" :max="720" :step="12" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="runner 活动上限">
                  <el-input-number v-model="form.runner_activity_limit" :min="20" :max="500" :step="20" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="最大信号延迟 (秒)">
                  <el-input-number v-model="form.max_signal_delay_seconds" :min="1" :max="3600" :step="30" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="最大滑点 (bps)">
                  <el-input-number v-model="form.max_slippage_bps" :min="0" :max="5000" :step="10" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <div class="switch-row">
              <el-switch v-model="form.dry_run" active-text="dry-run" inactive-text="live" />
              <el-switch v-model="form.close_only" active-text="close-only" inactive-text="可开仓" />
            </div>

            <div class="form-actions">
              <el-button type="primary" :loading="creatingStrategy" @click="createStrategy">创建策略</el-button>
              <el-button @click="resetForm">重置</el-button>
            </div>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="14">
        <el-card shadow="hover" class="detail-card status-card">
          <template #header>
            <div class="card-header">
              <span>Runner 状态</span>
              <el-tag :type="runnerStatus.running ? 'success' : 'warning'" size="small">
                {{ runnerStatus.running ? '运行中' : '已停止' }}
              </el-tag>
            </div>
          </template>

          <div class="status-grid">
            <div class="metric-card"><span>轮询间隔</span><strong>{{ runnerStatus.interval_seconds || '-' }} 秒</strong></div>
            <div class="metric-card"><span>运行中策略</span><strong>{{ runnerStatus.strategy_count || 0 }}</strong></div>
            <div class="metric-card"><span>总策略数</span><strong>{{ strategies.length }}</strong></div>
            <div class="metric-card"><span>当前选中</span><strong>{{ selectedStrategy?.strategy_name || '-' }}</strong></div>
          </div>

          <div v-if="latestSimulation" class="simulation-summary-box">
            <div class="summary-title">最近一次模拟结果</div>
            <div class="summary-grid">
              <div><span>原始成交</span><strong>{{ latestSimulation.summary.raw_trade_count }}</strong></div>
              <div><span>聚合成交</span><strong>{{ latestSimulation.summary.grouped_trade_count }}</strong></div>
              <div><span>执行信号</span><strong>{{ latestSimulation.summary.executed_signal_count }}</strong></div>
              <div><span>跳过信号</span><strong>{{ latestSimulation.summary.skipped_signal_count }}</strong></div>
              <div><span>源名义额</span><strong>{{ formatMoney(latestSimulation.summary.total_source_notional_usdc) }}</strong></div>
              <div><span>复制名义额</span><strong>{{ formatMoney(latestSimulation.summary.total_copied_notional_usdc) }}</strong></div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" class="detail-card">
      <template #header>
        <div class="card-header">
          <span>策略列表</span>
          <el-tag size="small" type="info">{{ strategies.length }} 条</el-tag>
        </div>
      </template>

      <el-table :data="strategies" stripe v-loading="loadingStrategies" @row-click="selectStrategy" class="strategy-table">
        <el-table-column prop="strategy_name" label="策略" min-width="220" />
        <el-table-column prop="source_wallet" label="源钱包" min-width="180">
          <template #default="scope">{{ shortenWallet(scope.row.source_wallet) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'running' ? 'success' : 'info'" size="small">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="倍率" width="90" align="right">
          <template #default="scope">{{ scope.row.copy_ratio.toFixed(2) }}x</template>
        </el-table-column>
        <el-table-column label="单笔上限" width="110" align="right">
          <template #default="scope">{{ formatMoney(scope.row.max_order_usdc) }}</template>
        </el-table-column>
        <el-table-column label="最近运行" min-width="160">
          <template #default="scope">{{ formatDateTime(scope.row.last_run_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="280">
          <template #default="scope">
            <div class="table-actions">
              <el-button link type="primary" :loading="actingStrategyId === scope.row.id && actionType === 'simulate'" @click.stop="simulateStrategy(scope.row)">模拟</el-button>
              <el-button v-if="scope.row.status !== 'running'" link type="success" :loading="actingStrategyId === scope.row.id && actionType === 'start'" @click.stop="startStrategy(scope.row)">启动</el-button>
              <el-button v-else link type="warning" :loading="actingStrategyId === scope.row.id && actionType === 'stop'" @click.stop="stopStrategy(scope.row)">停止</el-button>
              <el-button link @click.stop="loadRuns(scope.row)">运行记录</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="16" class="bottom-grid">
      <el-col :xs="24" :lg="12">
        <el-card shadow="hover" class="detail-card">
          <template #header>
            <div class="card-header">
              <span>最近运行记录</span>
              <el-tag size="small" type="info">{{ selectedStrategy?.strategy_name || '未选择策略' }}</el-tag>
            </div>
          </template>

          <el-table :data="strategyRuns" size="small" max-height="360" v-loading="loadingRuns">
            <el-table-column prop="id" label="#" width="70" />
            <el-table-column label="时间" min-width="160">
              <template #default="scope">{{ formatDateTime(scope.row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="executed_signal_count" label="执行" width="80" align="right" />
            <el-table-column prop="skipped_signal_count" label="跳过" width="80" align="right" />
            <el-table-column label="复制名义额" min-width="110" align="right">
              <template #default="scope">{{ formatMoney(scope.row.total_copied_notional_usdc) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card shadow="hover" class="detail-card">
          <template #header>
            <div class="card-header">
              <span>最近一次模拟信号</span>
              <el-tag size="small" type="info">{{ latestSimulation?.strategy?.strategy_name || '未运行模拟' }}</el-tag>
            </div>
          </template>

          <el-table :data="latestSimulation?.signals || []" size="small" max-height="360">
            <el-table-column prop="signal_type" label="信号" width="90" />
            <el-table-column prop="title" label="市场" min-width="180" />
            <el-table-column prop="side" label="方向" width="80" />
            <el-table-column label="源单" width="100" align="right">
              <template #default="scope">{{ formatMoney(scope.row.source_trade_usdc) }}</template>
            </el-table-column>
            <el-table-column label="复制单" width="100" align="right">
              <template #default="scope">{{ formatMoney(scope.row.follower_order_usdc) }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="90" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { polymarket } from '@/api'
import { formatDateTime as formatDisplayDateTime } from '@/utils/datetime'
import { formatPolymarketMoney, shortenPolymarketWallet } from '@/utils/polymarket'

const defaultForm = () => ({
  strategy_name: '',
  source_wallet: '',
  copy_ratio: 0.1,
  min_copy_order_usdc: 20,
  max_order_usdc: 200,
  max_market_exposure_usdc: 500,
  max_position_notional_usdc: 1000,
  runner_lookback_hours: 24,
  runner_activity_limit: 120,
  max_signal_delay_seconds: 120,
  max_slippage_bps: 80,
  dry_run: true,
  close_only: false
})

export default {
  name: 'PolymarketCopyStrategies',
  setup() {
    const form = reactive(defaultForm())
    const strategies = ref([])
    const selectedStrategy = ref(null)
    const strategyRuns = ref([])
    const latestSimulation = ref(null)
    const runnerStatus = ref({ running: false, interval_seconds: 0, strategy_count: 0 })
    const loadingStrategies = ref(false)
    const loadingRunnerStatus = ref(false)
    const loadingRuns = ref(false)
    const creatingStrategy = ref(false)
    const actingStrategyId = ref(null)
    const actionType = ref('')

    const formatMoney = value => formatPolymarketMoney(value)
    const shortenWallet = value => shortenPolymarketWallet(value)
    const formatDateTime = value => (value ? formatDisplayDateTime(value) : '-')

    const resetForm = () => {
      Object.assign(form, defaultForm())
    }

    const loadRuns = async strategy => {
      if (!strategy?.id) {
        return
      }
      selectedStrategy.value = strategy
      loadingRuns.value = true
      try {
        strategyRuns.value = await polymarket.getCopyStrategyRuns(strategy.id, { limit: 20 })
      } catch (error) {
        console.error('Failed to load copy strategy runs:', error)
        ElMessage.error('加载策略运行记录失败')
      } finally {
        loadingRuns.value = false
      }
    }

    const loadStrategies = async () => {
      loadingStrategies.value = true
      try {
        strategies.value = await polymarket.listCopyStrategies()
        if (!selectedStrategy.value && strategies.value.length) {
          await loadRuns(strategies.value[0])
        }
      } catch (error) {
        console.error('Failed to load polymarket copy strategies:', error)
        ElMessage.error('加载跟单策略失败')
      } finally {
        loadingStrategies.value = false
      }
    }

    const loadRunnerStatus = async () => {
      loadingRunnerStatus.value = true
      try {
        runnerStatus.value = await polymarket.getCopyRunnerStatus()
      } catch (error) {
        console.error('Failed to load polymarket copy runner status:', error)
        ElMessage.error('加载 runner 状态失败')
      } finally {
        loadingRunnerStatus.value = false
      }
    }

    const selectStrategy = async strategy => {
      await loadRuns(strategy)
    }

    const createStrategy = async () => {
      if (!form.strategy_name || !form.source_wallet) {
        ElMessage.warning('请先填写策略名称和源钱包地址')
        return
      }
      creatingStrategy.value = true
      try {
        const created = await polymarket.createCopyStrategy({ ...form })
        ElMessage.success('策略已创建')
        resetForm()
        await loadStrategies()
        await loadRunnerStatus()
        await loadRuns(created)
      } catch (error) {
        console.error('Failed to create copy strategy:', error)
        ElMessage.error(error?.response?.data?.detail || '创建策略失败')
      } finally {
        creatingStrategy.value = false
      }
    }

    const simulateStrategy = async strategy => {
      actingStrategyId.value = strategy.id
      actionType.value = 'simulate'
      try {
        latestSimulation.value = await polymarket.simulateCopyStrategy(strategy.id, {
          lookback_hours: strategy.runner_lookback_hours,
          activity_limit: strategy.runner_activity_limit
        })
        await loadRuns(strategy)
        await loadStrategies()
        ElMessage.success('模拟完成')
      } catch (error) {
        console.error('Failed to simulate copy strategy:', error)
        ElMessage.error(error?.response?.data?.detail || '执行模拟失败')
      } finally {
        actingStrategyId.value = null
        actionType.value = ''
      }
    }

    const startStrategy = async strategy => {
      actingStrategyId.value = strategy.id
      actionType.value = 'start'
      try {
        await polymarket.startCopyStrategy(strategy.id)
        await loadStrategies()
        await loadRunnerStatus()
        ElMessage.success('策略已启动 dry-run 轮询')
      } catch (error) {
        console.error('Failed to start copy strategy:', error)
        ElMessage.error(error?.response?.data?.detail || '启动策略失败')
      } finally {
        actingStrategyId.value = null
        actionType.value = ''
      }
    }

    const stopStrategy = async strategy => {
      actingStrategyId.value = strategy.id
      actionType.value = 'stop'
      try {
        await polymarket.stopCopyStrategy(strategy.id)
        await loadStrategies()
        await loadRunnerStatus()
        ElMessage.success('策略已停止')
      } catch (error) {
        console.error('Failed to stop copy strategy:', error)
        ElMessage.error(error?.response?.data?.detail || '停止策略失败')
      } finally {
        actingStrategyId.value = null
        actionType.value = ''
      }
    }

    onMounted(async () => {
      await Promise.all([loadStrategies(), loadRunnerStatus()])
    })

    return {
      form,
      strategies,
      selectedStrategy,
      strategyRuns,
      latestSimulation,
      runnerStatus,
      loadingStrategies,
      loadingRunnerStatus,
      loadingRuns,
      creatingStrategy,
      actingStrategyId,
      actionType,
      formatMoney,
      shortenWallet,
      formatDateTime,
      resetForm,
      loadStrategies,
      loadRunnerStatus,
      loadRuns,
      selectStrategy,
      createStrategy,
      simulateStrategy,
      startStrategy,
      stopStrategy
    }
  }
}
</script>

<style scoped>
.polymarket-copy-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 24px;
  border-radius: 20px;
  background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #475569;
}

.hero-panel h1 {
  margin: 0 0 8px;
  font-size: 30px;
  color: #0f172a;
}

.hero-copy {
  margin: 0;
  max-width: 720px;
  color: #475569;
  line-height: 1.6;
}

.hero-actions,
.form-actions,
.table-actions,
.switch-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.top-grid,
.bottom-grid {
  margin: 0;
}

.detail-card,
.strategy-table {
  border-radius: 18px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.status-grid,
.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.summary-grid > div {
  padding: 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.15);
}

.metric-card span,
.summary-grid > div span {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.metric-card strong,
.summary-grid > div strong {
  display: block;
  margin-top: 6px;
  font-size: 20px;
  color: #0f172a;
}

.simulation-summary-box {
  margin-top: 16px;
}

.summary-title {
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

@media (max-width: 960px) {
  .hero-panel {
    flex-direction: column;
  }

  .status-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
