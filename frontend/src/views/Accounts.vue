<template>
  <div class="accounts">
    <div class="header">
      <h1>账户管理</h1>
      <el-button type="primary" @click="showAddDialog">添加账户</el-button>
    </div>

    <el-card class="box-card">
      <el-table :data="accounts" style="width: 100%" v-loading="loading">
        <el-table-column prop="name" label="账户名称" width="150" />
        <el-table-column prop="exchange" label="交易所" width="120">
          <template #default="scope">
            <el-tag>{{ scope.row.exchange }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="api_key" label="API Key" width="200">
          <template #default="scope">
            {{ maskApiKey(scope.row.api_key) }}
          </template>
        </el-table-column>
        <el-table-column prop="total_balance" label="账户余额" width="150">
          <template #default="scope">
            {{ formatMoney(scope.row.total_balance) }}
          </template>
        </el-table-column>
        <el-table-column prop="total_equity" label="账户权益" width="150">
          <template #default="scope">
            {{ formatMoney(scope.row.total_equity) }}
          </template>
        </el-table-column>
        <el-table-column prop="initial_balance" label="初始资金" width="150">
          <template #default="scope">
            {{ formatMoney(scope.row.initial_balance) }}
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleStatusChange(scope.row)"
              active-color="#13ce66"
              inactive-color="#ff4949"
            />
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="280">
          <template #default="scope">
            <el-button
              size="small"
              type="success"
              @click="handleTestConnectivity(scope.row)"
              :loading="testingAccountId === scope.row.id"
              :disabled="!supportsConnectivityTest(scope.row.exchange)"
            >测试连接</el-button>
            <el-button size="small" @click="handleEdit(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Add/Edit Dialog -->
    <el-dialog
      :title="dialogTitle"
      v-model="dialogVisible"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="账户名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入账户名称"></el-input>
        </el-form-item>
        <el-form-item label="交易所" prop="exchange">
          <el-select v-model="form.exchange" placeholder="请选择交易所" style="width: 100%">
            <el-option label="Binance" value="binance"></el-option>
            <el-option label="OKX" value="okx"></el-option>
            <el-option label="Polymarket" value="polymarket"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="keyLabel" prop="api_key">
          <el-input v-model="form.api_key" :placeholder="keyPlaceholder"></el-input>
        </el-form-item>
        <el-form-item v-if="isPolymarket" label="Signer 私钥" prop="api_secret">
          <el-input
            v-model="form.api_secret"
            type="password"
            placeholder="请输入 Polymarket signer 私钥；没有时可暂留空用于只校验 CLOB 凭据"
            show-password
          ></el-input>
        </el-form-item>
        <el-alert
          v-if="isPolymarket && !polymarketSignerConfigured"
          type="warning"
          :closable="false"
          show-icon
          title="当前账户还没有保存合法的 signer 私钥。编辑页里如果这个输入框为空，通常表示库里的旧 api_secret 实际上是 relayer key，而不是 signer。"
        />
        <el-form-item v-else :label="secretLabel" prop="api_secret">
          <el-input v-model="form.api_secret" type="password" :placeholder="secretPlaceholder" show-password></el-input>
        </el-form-item>
        <el-divider v-if="isPolymarket" content-position="left">CLOB API 凭据</el-divider>
        <el-alert
          v-if="isPolymarket"
          type="warning"
          :closable="false"
          show-icon
          title="这里填写的是 CLOB 交易凭据，不是 polymarket.com 设置页“开发者 / Builder Program”里展示的 API keys。开发者页那组 key 用于 builder/relayer 归因与免 gas 流程，不能直接当普通 CLOB 下单凭据。"
        />
        <el-form-item v-if="isPolymarket" label="Relayer API Key" prop="polymarket_relayer_api_key">
          <el-input
            v-model="form.polymarket_relayer_api_key"
            placeholder="仅用于 relayer-v2 的 RELAYER_API_KEY；不要和 signer 私钥或开发者页 Builder keys 混用"
          ></el-input>
        </el-form-item>
        <el-form-item v-if="isPolymarket" label="Relayer Key Address" prop="polymarket_relayer_api_key_address">
          <el-input
            v-model="form.polymarket_relayer_api_key_address"
            placeholder="请输入 RELAYER_API_KEY_ADDRESS / owner signer 地址"
          ></el-input>
        </el-form-item>
        <el-form-item v-if="isPolymarket" label="CLOB API Key" prop="polymarket_clob_api_key">
          <el-input
            v-model="form.polymarket_clob_api_key"
            placeholder="请输入通过 CLOB auth/create-or-derive 获得的交易 API Key，不要填开发者页 Builder keys"
          ></el-input>
        </el-form-item>
        <el-form-item v-if="isPolymarket" label="CLOB API Secret" prop="polymarket_clob_api_secret">
          <el-input
            v-model="form.polymarket_clob_api_secret"
            type="password"
            placeholder="请输入与上面 CLOB API Key 同组的交易 API Secret"
            show-password
          ></el-input>
        </el-form-item>
        <el-form-item v-if="isPolymarket" label="CLOB Passphrase" prop="polymarket_clob_api_passphrase">
          <el-input
            v-model="form.polymarket_clob_api_passphrase"
            type="password"
            placeholder="请输入与上面 CLOB API Key 同组的交易 Passphrase"
            show-password
          ></el-input>
        </el-form-item>
        <el-form-item v-if="requiresPassphrase" :label="passphraseLabel" prop="api_passphrase">
          <el-input
            v-model="form.api_passphrase"
            type="password"
            :placeholder="passphrasePlaceholder"
            show-password
          ></el-input>
        </el-form-item>
        <el-form-item v-if="isPolymarket" label="Signature Type">
          <el-select v-model="form.polymarket_signature_type" style="width: 100%">
            <el-option label="0 - EOA" :value="0"></el-option>
            <el-option label="3 - Deposit Wallet / POLY_1271" :value="3"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item v-if="isPolymarket" label="Funder 地址">
          <el-input
            v-model="form.polymarket_funder_address"
            placeholder="可选，deposit wallet 模式下填写"
          ></el-input>
        </el-form-item>
        <el-alert
          v-if="form.exchange === 'polymarket'"
          type="info"
          :closable="false"
          show-icon
          title="Polymarket 至少有三套容易混淆的凭据：Signer 私钥用于订单签名，CLOB API key/secret/passphrase 用于 CLOB 私有交易接口，Relayer API key 用于 relayer-v2 的 wallet/deposit 操作。设置页“开发者 / Builder Program”里看到的 builder keys 和 builder code 也不是这组 CLOB 交易凭据。"
        />
        <el-form-item label="初始资金" prop="initial_balance">
          <el-input-number v-model="form.initial_balance" :min="0" :precision="2" :step="1000" style="width: 100%"></el-input-number>
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="form.is_active"></el-switch>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitForm" :loading="submitting">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed } from 'vue'
import { useStore } from 'vuex'
import { ElMessage, ElMessageBox } from 'element-plus'
import { riskControl } from '@/api'
import { formatDateTime as formatDisplayDateTime } from '@/utils/datetime'

export default {
  name: 'Accounts',
  setup() {
    const store = useStore()
    const looksLikePolymarketSigner = value => /^0x[a-fA-F0-9]{64}$/.test(String(value || '').trim())

    const signerSecretValidator = (_rule, value, callback) => {
      if (form.exchange !== 'polymarket' && !String(value || '').trim()) {
        callback(new Error('请输入API Secret'))
        return
      }
      if (form.exchange === 'polymarket' && !String(value || '').trim() && !isEdit.value) {
        callback(new Error('新建 Polymarket 账户时请填写 signer 私钥'))
        return
      }
      callback()
    }

    const passphraseValidator = (_rule, value, callback) => {
      if (form.exchange === 'okx' && !String(value || '').trim()) {
        callback(new Error('OKX 账户必须填写 Passphrase'))
        return
      }
      callback()
    }

    const polymarketApiCredsValidator = (_rule, _value, callback) => {
      if (form.exchange !== 'polymarket') {
        callback()
        return
      }

      const values = [
        form.polymarket_clob_api_key,
        form.polymarket_clob_api_secret,
        form.polymarket_clob_api_passphrase,
      ].map(item => String(item || '').trim())

      const filledCount = values.filter(Boolean).length
      if (filledCount > 0 && filledCount < values.length) {
        callback(new Error('CLOB API Key、Secret、Passphrase 需要同时填写'))
        return
      }
      callback()
    }

    const polymarketRelayerValidator = (_rule, _value, callback) => {
      if (form.exchange !== 'polymarket') {
        callback()
        return
      }

      const values = [
        form.polymarket_relayer_api_key,
        form.polymarket_relayer_api_key_address,
      ].map(item => String(item || '').trim())

      const filledCount = values.filter(Boolean).length
      if (filledCount > 0 && filledCount < values.length) {
        callback(new Error('Relayer API Key 与 Relayer Key Address 需要同时填写'))
        return
      }
      callback()
    }

    const polymarketFunderValidator = (_rule, value, callback) => {
      if (form.exchange !== 'polymarket') {
        callback()
        return
      }

      if (Number(form.polymarket_signature_type) !== 3) {
        callback()
        return
      }

      const walletAddress = String(form.api_key || '').trim().toLowerCase()
      const funderAddress = String(value || '').trim().toLowerCase()
      if (walletAddress && funderAddress && walletAddress !== funderAddress) {
        callback(new Error('POLY_1271 模式下 Funder 地址必须等于钱包地址（deposit wallet 地址）'))
        return
      }
      callback()
    }

    const accounts = ref([])
    const loading = ref(false)
    const dialogVisible = ref(false)
    const submitting = ref(false)
    const isEdit = ref(false)
    const testingAccountId = ref(null)
    const formRef = ref(null)

    const form = reactive({
      id: null,
      name: '',
      exchange: 'binance',
      api_key: '',
      api_secret: '',
      api_passphrase: '',
      polymarket_relayer_api_key: '',
      polymarket_relayer_api_key_address: '',
      polymarket_clob_api_key: '',
      polymarket_clob_api_secret: '',
      polymarket_clob_api_passphrase: '',
      polymarket_signature_type: 0,
      polymarket_funder_address: '',
      initial_balance: 0.0,
      is_active: true
    })

    const rules = {
      name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
      exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
      api_key: [{ required: true, message: '请输入API Key', trigger: 'blur' }],
      api_secret: [{ validator: signerSecretValidator, trigger: 'blur' }],
      polymarket_relayer_api_key: [{ validator: polymarketRelayerValidator, trigger: 'blur' }],
      polymarket_relayer_api_key_address: [{ validator: polymarketRelayerValidator, trigger: 'blur' }],
      polymarket_clob_api_key: [{ validator: polymarketApiCredsValidator, trigger: 'blur' }],
      polymarket_clob_api_secret: [{ validator: polymarketApiCredsValidator, trigger: 'blur' }],
      polymarket_clob_api_passphrase: [{ validator: polymarketApiCredsValidator, trigger: 'blur' }],
      polymarket_funder_address: [{ validator: polymarketFunderValidator, trigger: 'blur' }],
      api_passphrase: [{ validator: passphraseValidator, trigger: 'blur' }]
    }

    const dialogTitle = computed(() => isEdit.value ? '编辑账户' : '添加账户')
    const isPolymarket = computed(() => form.exchange === 'polymarket')
    const polymarketSignerConfigured = computed(() => looksLikePolymarketSigner(form.api_secret))
    const requiresPassphrase = computed(() => form.exchange === 'okx')
    const keyLabel = computed(() => form.exchange === 'polymarket' ? '钱包地址' : 'API Key')
    const secretLabel = computed(() => {
      if (isPolymarket.value) return 'Signer 私钥'
      return 'API Secret'
    })
    const keyPlaceholder = computed(() => form.exchange === 'polymarket' ? '请输入 Polymarket 钱包地址' : '请输入API Key')
    const secretPlaceholder = computed(() => {
      if (isPolymarket.value) return '请输入 Polymarket signer 私钥'
      return '请输入API Secret'
    })
    const passphraseLabel = computed(() => 'Passphrase')
    const passphrasePlaceholder = computed(() => '请输入 OKX API Passphrase')
    const displayTimezone = computed(() => store.getters.displayTimezone)
    const supportsConnectivityTest = exchange => ['binance', 'okx', 'okex', 'polymarket'].includes(String(exchange || '').toLowerCase())

    const resetPolymarketFields = () => {
      form.polymarket_relayer_api_key = ''
      form.polymarket_relayer_api_key_address = ''
      form.polymarket_clob_api_key = ''
      form.polymarket_clob_api_secret = ''
      form.polymarket_clob_api_passphrase = ''
      form.polymarket_signature_type = 0
      form.polymarket_funder_address = ''
    }

    const buildPolymarketSettings = () => {
      const settings = {}
      if (Number(form.polymarket_signature_type) === 3) {
        settings.polymarket_signature_type = 3
      }
      if (String(form.polymarket_funder_address || '').trim()) {
        settings.polymarket_funder_address = String(form.polymarket_funder_address).trim()
      }
      if (String(form.polymarket_relayer_api_key || '').trim()) {
        settings.polymarket_relayer_api_key = String(form.polymarket_relayer_api_key || '').trim()
        settings.polymarket_relayer_api_key_address = String(form.polymarket_relayer_api_key_address || '').trim()
      }
      if (String(form.polymarket_clob_api_key || '').trim()) {
        settings.polymarket_clob_api_key = String(form.polymarket_clob_api_key || '').trim()
        settings.polymarket_clob_api_secret = String(form.polymarket_clob_api_secret || '').trim()
        settings.polymarket_clob_api_passphrase = String(form.polymarket_clob_api_passphrase || '').trim()
      }
      return settings
    }

    const buildAccountPayload = () => {
      const payload = {
        name: form.name,
        exchange: form.exchange,
        api_key: form.api_key,
        initial_balance: form.initial_balance,
        is_active: form.is_active
      }

      if (form.exchange !== 'polymarket') {
        payload.api_secret = form.api_secret
        payload.api_passphrase = form.api_passphrase || null
      } else {
        const signerValue = String(form.api_secret || '').trim()
        if (signerValue) {
          payload.api_secret = signerValue
        }
      }

      payload.settings = form.exchange === 'polymarket' ? buildPolymarketSettings() : {}
      return payload
    }

    const fetchAccounts = async () => {
      loading.value = true
      try {
        const data = await riskControl.getAccounts()
        accounts.value = data
      } catch (error) {
        console.error('Failed to fetch accounts:', error)
        ElMessage.error('获取账户列表失败')
      } finally {
        loading.value = false
      }
    }

    const showAddDialog = () => {
      isEdit.value = false
      form.id = null
      form.name = ''
      form.exchange = 'binance'
      form.api_key = ''
      form.api_secret = ''
      form.api_passphrase = ''
      resetPolymarketFields()
      form.initial_balance = 0.0
      form.is_active = true
      dialogVisible.value = true
    }

    const handleEdit = (row) => {
      const settings = row.settings || {}
      const hasPolymarketApiCreds = Boolean(
        settings.polymarket_clob_api_key ||
        settings.polymarket_clob_api_secret ||
        settings.polymarket_clob_api_passphrase
      )
      isEdit.value = true
      form.id = row.id
      form.name = row.name
      form.exchange = row.exchange
      form.api_key = row.api_key
      form.api_secret = row.exchange === 'polymarket'
        ? (looksLikePolymarketSigner(row.api_secret) ? row.api_secret : '')
        : row.api_secret
      form.api_passphrase = row.api_passphrase || ''
      form.polymarket_relayer_api_key = settings.polymarket_relayer_api_key || (row.exchange === 'polymarket' && !looksLikePolymarketSigner(row.api_secret) ? row.api_secret : '')
      form.polymarket_relayer_api_key_address = settings.polymarket_relayer_api_key_address || settings.polymarket_signer_address || settings.polymarket_relayer_signer_address || settings.polymarket_funder_address || ''
      form.polymarket_clob_api_key = settings.polymarket_clob_api_key || ''
      form.polymarket_clob_api_secret = settings.polymarket_clob_api_secret || ''
      form.polymarket_clob_api_passphrase = settings.polymarket_clob_api_passphrase || ''
      form.polymarket_signature_type = Number(settings.polymarket_signature_type || 0)
      form.polymarket_funder_address = settings.polymarket_funder_address || ''
      form.initial_balance = row.initial_balance || 0.0
      form.is_active = row.is_active
      dialogVisible.value = true
    }

    const handleDelete = (row) => {
      ElMessageBox.confirm(
        `确定要删除账户 "${row.name}" 吗？`,
        '警告',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
        }
      ).then(async () => {
        try {
          await riskControl.deleteAccount(row.id)
          ElMessage.success('删除成功')
          fetchAccounts()
        } catch (error) {
          console.error('Failed to delete account:', error)
          ElMessage.error('删除失败')
        }
      }).catch(() => {})
    }

    const handleStatusChange = async (row) => {
      try {
        await riskControl.updateAccount(row.id, { is_active: row.is_active })
        ElMessage.success('状态更新成功')
      } catch (error) {
        console.error('Failed to update status:', error)
        row.is_active = !row.is_active // Revert
        ElMessage.error('状态更新失败')
      }
    }

    const escapeHtml = (value) => {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
    }

    const buildConnectivityCheckHtml = (title, check) => {
      const lines = [
        `${title}: ${check.ok ? '正常' : '失败'}${check.status_code ? ` (HTTP ${check.status_code})` : ''}`,
        check.message ? `返回: ${check.message}` : null,
        check.hint ? `提示: ${check.hint}` : null
      ].filter(Boolean)

      return lines.map(line => escapeHtml(line)).join('<br>')
    }

    const buildConnectivityDialogHtml = (row, result) => {
      const checks = Array.isArray(result.checks) && result.checks.length
        ? result.checks
        : [result.spot_account, result.futures_account].filter(Boolean)
      const scopeTitleMap = {
        spot: '现货账户接口',
        futures: '合约账户接口',
        wallet: '本地钱包格式',
        signer: 'Signer 私钥检查',
        sdk: '官方 SDK 依赖',
        clob_l1: 'CLOB L1 认证',
        clob_l2: 'CLOB L2 认证'
      }

      return [
        `<strong>${escapeHtml(row.name || `账户 ${row.id}`)}</strong>`,
        ...checks.map(check => buildConnectivityCheckHtml(scopeTitleMap[check.scope] || check.scope || '检查项', check)),
        result.overall_hint ? escapeHtml(`综合判断: ${result.overall_hint}`) : '',
        result.account_mode_note ? escapeHtml(`账户模式说明: ${result.account_mode_note}`) : ''
      ].filter(Boolean).join('<br><br>')
    }

    const handleTestConnectivity = async (row) => {
      testingAccountId.value = row.id
      try {
        const result = await riskControl.testAccountConnectivity(row.id)
        await ElMessageBox.alert(
          buildConnectivityDialogHtml(row, result),
          '账户连通性检测',
          {
            confirmButtonText: '知道了',
            dangerouslyUseHTMLString: true
          }
        )
      } catch (error) {
        console.error('Failed to test account connectivity:', error)
        ElMessage.error('账户连通性检测失败')
      } finally {
        testingAccountId.value = null
      }
    }

    const submitForm = async () => {
      if (!formRef.value) return
      
      await formRef.value.validate(async (valid) => {
        if (valid) {
          submitting.value = true
          try {
            const payload = buildAccountPayload()
            if (isEdit.value) {
              await riskControl.updateAccount(form.id, payload)
              ElMessage.success('更新成功')
            } else {
              await riskControl.createAccount(payload)
              ElMessage.success('创建成功')
            }
            dialogVisible.value = false
            fetchAccounts()
          } catch (error) {
            console.error('Failed to submit form:', error)
            ElMessage.error(error.response?.data?.detail || (isEdit.value ? '更新失败' : '创建失败'))
          } finally {
            submitting.value = false
          }
        }
      })
    }

    const maskApiKey = (key) => {
      if (!key || key.length < 8) return key
      return key.substring(0, 4) + '****' + key.substring(key.length - 4)
    }

    const formatMoney = (value) => {
      if (value === undefined || value === null) return '-'
      return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }

    const formatDate = (dateStr) => {
      if (!dateStr) return '-'
      return formatDisplayDateTime(dateStr, displayTimezone.value)
    }

    onMounted(() => {
      fetchAccounts()
    })

    return {
      accounts,
      loading,
      dialogVisible,
      submitting,
      form,
      rules,
      formRef,
      testingAccountId,
      dialogTitle,
      isPolymarket,
      polymarketSignerConfigured,
      requiresPassphrase,
      keyLabel,
      secretLabel,
      keyPlaceholder,
      secretPlaceholder,
      passphraseLabel,
      passphrasePlaceholder,
      supportsConnectivityTest,
      showAddDialog,
      handleEdit,
      handleDelete,
      handleStatusChange,
      handleTestConnectivity,
      submitForm,
      maskApiKey,
      formatMoney,
      formatDate
    }
  }
}
</script>

<style scoped>
.accounts {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.box-card {
  margin-bottom: 20px;
}
</style>
