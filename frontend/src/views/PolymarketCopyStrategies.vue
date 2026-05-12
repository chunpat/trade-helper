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

            <el-form-item label="执行模式">
              <el-switch v-model="form.dry_run" active-text="dry-run" inactive-text="真实交易" />
            </el-form-item>

            <el-form-item label="执行账户">
              <div class="account-picker-row">
                <el-select v-model="form.execution_account_id" clearable filterable placeholder="请选择真实交易账户" style="width: 100%">
                  <el-option
                    v-for="account in polymarketAccounts"
                    :key="account.id"
                    :label="`${account.name || '未命名账户'} · ${String(account.exchange || '').toUpperCase()}${account.is_active ? '' : ' · 已停用'}`"
                    :value="account.id"
                    :disabled="!account.is_active"
                  />
                </el-select>
                <el-button :loading="loadingAccounts" @click="showAddAccountDialog">添加账户</el-button>
              </div>
              <div class="field-hint">dry-run 可不绑定账户；切到真实交易模式时必须先绑定一个启用中的 Polymarket 账户。</div>
              <el-alert
                v-if="!form.dry_run"
                type="warning"
                :closable="false"
                show-icon
                title="当前仓库已经接入 Polymarket live 预检、真实下单与回执落库；启动后 runner 会按信号提交订单，停止时会尝试撤销本地记录的未完成订单。"
              />
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
                  <el-input-number v-model="form.max_order_usdc" :min="0" :step="10" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="单市场暴露上限">
                  <el-input-number v-model="form.max_market_exposure_usdc" :min="0" :step="50" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <div class="field-hint">copy ratio 默认 1.00 表示按源单金额 1:1 同步；最小跟单额和各类上限填 0 表示不限。</div>

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
          <template #default="scope">
            <div class="wallet-cell">
              <span>{{ shortenWallet(scope.row.source_wallet) }}</span>
              <el-button link type="primary" @click.stop="goToTraderDetail(scope.row.source_wallet)">详情</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'running' ? 'success' : 'info'" size="small">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="模式" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.dry_run ? 'info' : 'danger'" size="small">{{ scope.row.dry_run ? 'dry-run' : 'live' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行账户" min-width="180">
          <template #default="scope">{{ formatExecutionAccount(scope.row) }}</template>
        </el-table-column>
        <el-table-column label="倍率" width="90" align="right">
          <template #default="scope">{{ scope.row.copy_ratio.toFixed(2) }}x</template>
        </el-table-column>
        <el-table-column label="单笔上限" width="110" align="right">
          <template #default="scope">{{ formatLimitMoney(scope.row.max_order_usdc) }}</template>
        </el-table-column>
        <el-table-column label="最近运行" min-width="160">
          <template #default="scope">{{ formatDateTime(scope.row.last_run_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="280">
          <template #default="scope">
            <div class="table-actions">
              <el-button link type="primary" :loading="actingStrategyId === scope.row.id && actionType === 'simulate'" @click.stop="simulateStrategy(scope.row)">模拟</el-button>
              <el-button v-if="!scope.row.dry_run" link type="info" :loading="actingStrategyId === scope.row.id && actionType === 'preflight'" @click.stop="preflightStrategy(scope.row)">预检</el-button>
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

    <el-dialog
      v-model="accountDialogVisible"
      title="添加真实交易账户"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form ref="accountFormRef" :model="accountForm" :rules="accountRules" label-position="top">
        <el-form-item label="账户名称" prop="name">
          <el-input v-model="accountForm.name" :placeholder="accountNamePlaceholder" />
        </el-form-item>
        <el-form-item label="交易所" prop="exchange">
          <el-select v-model="accountForm.exchange" placeholder="请选择交易所" style="width: 100%">
            <el-option label="Binance" value="binance" />
            <el-option label="OKX" value="okx" />
            <el-option label="Polymarket" value="polymarket" />
          </el-select>
        </el-form-item>
        <el-form-item :label="accountKeyLabel" prop="api_key">
          <el-input v-model="accountForm.api_key" :placeholder="accountKeyPlaceholder" />
        </el-form-item>
        <el-form-item :label="accountSecretLabel" prop="api_secret">
          <el-input v-model="accountForm.api_secret" type="password" show-password :placeholder="accountSecretPlaceholder" />
        </el-form-item>
        <el-form-item v-if="accountRequiresPassphrase" label="Passphrase" prop="api_passphrase">
          <el-input v-model="accountForm.api_passphrase" type="password" show-password placeholder="请输入 OKX API Passphrase" />
        </el-form-item>
        <el-alert
          v-if="accountForm.exchange === 'polymarket'"
          type="info"
          :closable="false"
          show-icon
          title="Polymarket 账户当前先保存钱包地址与私钥占位，用于策略绑定；仓库还没接入私有下单与连通性检测。"
        />
        <el-form-item label="初始资金" prop="initial_balance">
          <el-input-number v-model="accountForm.initial_balance" :min="0" :precision="2" :step="1000" style="width: 100%" />
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="form-actions">
          <el-button @click="accountDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="creatingAccount" @click="createAccount">创建账户</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { polymarket, riskControl } from '@/api'
import { formatDateTime as formatDisplayDateTime } from '@/utils/datetime'
import { formatPolymarketMoney, shortenPolymarketWallet } from '@/utils/polymarket'

const defaultForm = () => ({
  strategy_name: '',
  source_wallet: '',
  execution_account_id: null,
  copy_ratio: 1,
  min_copy_order_usdc: 0,
  max_order_usdc: 0,
  max_market_exposure_usdc: 0,
  max_position_notional_usdc: 0,
  runner_lookback_hours: 24,
  runner_activity_limit: 120,
  max_signal_delay_seconds: 120,
  max_slippage_bps: 80,
  dry_run: true,
  close_only: false
})

const defaultAccountForm = () => ({
  name: '',
  exchange: 'polymarket',
  api_key: '',
  api_secret: '',
  api_passphrase: '',
  initial_balance: 0
})

export default {
  name: 'PolymarketCopyStrategies',
  setup() {
    const router = useRouter()
    const form = reactive(defaultForm())
    const accountForm = reactive(defaultAccountForm())
    const strategies = ref([])
    const accounts = ref([])
    const selectedStrategy = ref(null)
    const strategyRuns = ref([])
    const latestSimulation = ref(null)
    const runnerStatus = ref({ running: false, interval_seconds: 0, strategy_count: 0 })
    const loadingStrategies = ref(false)
    const loadingAccounts = ref(false)
    const loadingRunnerStatus = ref(false)
    const loadingRuns = ref(false)
    const creatingStrategy = ref(false)
    const creatingAccount = ref(false)
    const actingStrategyId = ref(null)
    const actionType = ref('')
    const accountDialogVisible = ref(false)
    const accountFormRef = ref(null)

    const accountRequiresPassphrase = computed(() => accountForm.exchange === 'okx')
    const polymarketAccounts = computed(() => accounts.value.filter(account => String(account.exchange || '').toLowerCase() === 'polymarket'))
    const accountNamePlaceholder = computed(() => {
      if (accountForm.exchange === 'polymarket') {
        return '例如：Polymarket 主钱包'
      }
      return '例如：主账户 / OKX 量化账户'
    })
    const accountKeyLabel = computed(() => (accountForm.exchange === 'polymarket' ? '钱包地址' : 'API Key'))
    const accountSecretLabel = computed(() => (accountForm.exchange === 'polymarket' ? '私钥' : 'API Secret'))
    const accountKeyPlaceholder = computed(() => (accountForm.exchange === 'polymarket' ? '请输入 Polymarket 钱包地址' : '请输入 API Key'))
    const accountSecretPlaceholder = computed(() => (accountForm.exchange === 'polymarket' ? '请输入 Polymarket 私钥' : '请输入 API Secret'))
    const accountRules = {
      name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
      exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
      api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
      api_secret: [{ required: true, message: '请输入 API Secret', trigger: 'blur' }],
      api_passphrase: [{
        validator: (_rule, value, callback) => {
          if (accountForm.exchange === 'okx' && !String(value || '').trim()) {
            callback(new Error('OKX 账户必须填写 Passphrase'))
            return
          }
          callback()
        },
        trigger: 'blur'
      }]
    }

    const formatMoney = value => formatPolymarketMoney(value)
    const formatLimitMoney = value => {
      if (value === undefined || value === null || Number(value) <= 0) {
        return '不限'
      }
      return formatPolymarketMoney(value)
    }
    const escapeHtml = value => String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
    const shortenWallet = value => shortenPolymarketWallet(value)
    const formatDateTime = value => (value ? formatDisplayDateTime(value) : '-')
    const goToTraderDetail = wallet => {
      if (!wallet) {
        return
      }
      router.push({ name: 'PolymarketTraderDetail', params: { wallet } })
    }
    const formatExecutionAccount = strategy => {
      if (!strategy?.execution_account_id) {
        return strategy?.dry_run ? '未绑定（dry-run）' : '未绑定'
      }
      if (strategy.execution_account_name && strategy.execution_account_exchange) {
        return `${strategy.execution_account_name} · ${String(strategy.execution_account_exchange).toUpperCase()}`
      }
      const account = accounts.value.find(item => item.id === strategy.execution_account_id)
      if (!account) {
        return `账户 #${strategy.execution_account_id}`
      }
      return `${account.name || `账户 #${account.id}`} · ${String(account.exchange || '').toUpperCase()}`
    }

    const resetForm = () => {
      Object.assign(form, defaultForm())
    }

    const resetAccountForm = () => {
      Object.assign(accountForm, defaultAccountForm())
    }

    const loadAccounts = async () => {
      loadingAccounts.value = true
      try {
        accounts.value = await riskControl.getAccounts()
      } catch (error) {
        console.error('Failed to load accounts:', error)
        ElMessage.error('加载账户列表失败')
      } finally {
        loadingAccounts.value = false
      }
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

    const showAddAccountDialog = () => {
      resetAccountForm()
      accountDialogVisible.value = true
    }

    const createAccount = async () => {
      if (!accountFormRef.value) {
        return
      }
      accountFormRef.value.validate(async valid => {
        if (!valid) {
          return
        }
        creatingAccount.value = true
        try {
          const created = await riskControl.createAccount({
            ...accountForm,
            api_passphrase: accountForm.api_passphrase || null,
            settings: {}
          })
          await loadAccounts()
          form.execution_account_id = created.id
          accountDialogVisible.value = false
          ElMessage.success('账户已创建并绑定到当前策略表单')
        } catch (error) {
          console.error('Failed to create account:', error)
          ElMessage.error(error?.response?.data?.detail || '创建账户失败')
        } finally {
          creatingAccount.value = false
        }
      })
    }

    const createStrategy = async () => {
      if (!form.strategy_name || !form.source_wallet) {
        ElMessage.warning('请先填写策略名称和源钱包地址')
        return
      }
      if (!form.dry_run && !form.execution_account_id) {
        ElMessage.warning('真实交易模式必须先绑定一个执行账户')
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

    const buildPreflightDialogHtml = result => {
      const signal = result.sample_signal
      const checks = Array.isArray(result.checks) ? result.checks : []
      return [
        `<strong>${escapeHtml(result.strategy?.strategy_name || '未命名策略')}</strong>`,
        escapeHtml(`总体结果: ${result.overall_ok ? '通过' : '未通过'}`),
        result.overall_hint ? escapeHtml(`结论: ${result.overall_hint}`) : '',
        escapeHtml(`最近窗口可执行信号: ${result.executable_signal_count || 0}`),
        signal ? escapeHtml(`样本信号: ${signal.title || '-'} / ${signal.side || '-'} / ${formatMoney(signal.follower_order_usdc)}`) : '',
        ...checks.map(check => escapeHtml(`${check.ok ? '通过' : '失败'} | ${check.name} | HTTP ${check.status_code}${check.message ? ` | ${check.message}` : ''}${check.hint ? ` | ${check.hint}` : ''}`))
      ].filter(Boolean).join('<br><br>')
    }

    const preflightStrategy = async strategy => {
      actingStrategyId.value = strategy.id
      actionType.value = 'preflight'
      try {
        const result = await polymarket.preflightCopyStrategy(strategy.id, {
          lookback_hours: strategy.runner_lookback_hours,
          activity_limit: strategy.runner_activity_limit
        })
        await ElMessageBox.alert(buildPreflightDialogHtml(result), 'Live 预检结果', {
          confirmButtonText: '知道了',
          dangerouslyUseHTMLString: true
        })
      } catch (error) {
        console.error('Failed to preflight copy strategy:', error)
        ElMessage.error(error?.response?.data?.detail || '执行 live 预检失败')
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
      await Promise.all([loadStrategies(), loadRunnerStatus(), loadAccounts()])
    })

    return {
      form,
      accountForm,
      strategies,
      accounts,
      polymarketAccounts,
      selectedStrategy,
      strategyRuns,
      latestSimulation,
      runnerStatus,
      loadingStrategies,
      loadingAccounts,
      loadingRunnerStatus,
      loadingRuns,
      creatingStrategy,
      creatingAccount,
      actingStrategyId,
      actionType,
      accountDialogVisible,
      accountFormRef,
      accountRequiresPassphrase,
      accountNamePlaceholder,
      accountKeyLabel,
      accountSecretLabel,
      accountKeyPlaceholder,
      accountSecretPlaceholder,
      accountRules,
      formatMoney,
      formatLimitMoney,
      shortenWallet,
      formatDateTime,
      goToTraderDetail,
      formatExecutionAccount,
      resetForm,
      resetAccountForm,
      loadStrategies,
      loadAccounts,
      loadRunnerStatus,
      loadRuns,
      selectStrategy,
      showAddAccountDialog,
      createAccount,
      createStrategy,
      preflightStrategy,
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
.switch-row,
.account-picker-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.account-picker-row {
  width: 100%;
}

.field-hint {
  margin: 6px 0 10px;
  font-size: 12px;
  color: #64748b;
}

.wallet-cell {
  display: flex;
  align-items: center;
  gap: 8px;
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
