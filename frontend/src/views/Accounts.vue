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
          </el-select>
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="form.api_key" placeholder="请输入API Key"></el-input>
        </el-form-item>
        <el-form-item label="API Secret" prop="api_secret">
          <el-input v-model="form.api_secret" type="password" placeholder="请输入API Secret" show-password></el-input>
        </el-form-item>
        <el-form-item v-if="requiresPassphrase" label="Passphrase" prop="api_passphrase">
          <el-input
            v-model="form.api_passphrase"
            type="password"
            placeholder="请输入 OKX API Passphrase"
            show-password
          ></el-input>
        </el-form-item>
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
    const passphraseValidator = (_rule, value, callback) => {
      if (form.exchange === 'okx' && !String(value || '').trim()) {
        callback(new Error('OKX 账户必须填写 Passphrase'))
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
      initial_balance: 0.0,
      is_active: true
    })

    const rules = {
      name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
      exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
      api_key: [{ required: true, message: '请输入API Key', trigger: 'blur' }],
      api_secret: [{ required: true, message: '请输入API Secret', trigger: 'blur' }],
      api_passphrase: [{ validator: passphraseValidator, trigger: 'blur' }]
    }

    const dialogTitle = computed(() => isEdit.value ? '编辑账户' : '添加账户')
    const requiresPassphrase = computed(() => form.exchange === 'okx')
    const displayTimezone = computed(() => store.getters.displayTimezone)

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
      form.initial_balance = 0.0
      form.is_active = true
      dialogVisible.value = true
    }

    const handleEdit = (row) => {
      isEdit.value = true
      form.id = row.id
      form.name = row.name
      form.exchange = row.exchange
      form.api_key = row.api_key
      form.api_secret = row.api_secret
      form.api_passphrase = row.api_passphrase || ''
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
      return [
        `<strong>${escapeHtml(row.name || `账户 ${row.id}`)}</strong>`,
        buildConnectivityCheckHtml('现货账户接口', result.spot_account),
        buildConnectivityCheckHtml('合约账户接口', result.futures_account),
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
            if (isEdit.value) {
              await riskControl.updateAccount(form.id, {
                name: form.name,
                exchange: form.exchange,
                api_key: form.api_key,
                api_secret: form.api_secret,
                api_passphrase: form.api_passphrase || null,
                initial_balance: form.initial_balance,
                is_active: form.is_active
              })
              ElMessage.success('更新成功')
            } else {
              await riskControl.createAccount({
                name: form.name,
                exchange: form.exchange,
                api_key: form.api_key,
                api_secret: form.api_secret,
                api_passphrase: form.api_passphrase || null,
                initial_balance: form.initial_balance,
                settings: {}
              })
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
      requiresPassphrase,
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
