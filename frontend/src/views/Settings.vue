<template>
  <div class="settings">
    <div class="header">
      <h1>风控配置</h1>
      <el-select v-model="selectedAccountId" placeholder="选择账户" @change="fetchConfig">
        <el-option
          v-for="account in accounts"
          :key="account.id"
          :label="account.name || account.exchange + ' (' + account.id + ')'"
          :value="account.id"
        />
      </el-select>
    </div>

    <div class="page-content" v-loading="loading">
      <el-empty v-if="!selectedAccountId" description="请先选择一个账户进行配置" />
      
      <el-form 
        v-else 
        ref="formRef" 
        :model="form" 
        :rules="rules" 
        label-width="180px"
        class="risk-form"
      >
        <el-divider content-position="left">仓位风控</el-divider>
        
        <el-form-item label="最大杠杆倍数" prop="max_leverage">
          <el-input-number v-model="form.max_leverage" :min="1" :max="125" />
          <div class="help-text">允许的最大杠杆倍数</div>
        </el-form-item>

        <el-form-item label="最大持仓价值 (USDT)" prop="max_position_value">
          <el-input-number v-model="form.max_position_value" :min="0" :step="1000" />
          <div class="help-text">单账户允许的最大持仓总价值</div>
        </el-form-item>

        <el-form-item label="风险率阈值" prop="risk_ratio_threshold">
          <el-input-number v-model="form.risk_ratio_threshold" :min="0" :max="1" :step="0.01" />
          <div class="help-text">保证金使用率预警阈值 (0-1)</div>
        </el-form-item>

        <el-divider content-position="left">订单风控</el-divider>

        <el-form-item label="单笔最大下单量" prop="max_single_order">
          <el-input-number v-model="form.max_single_order" :min="0" :step="0.1" />
        </el-form-item>

        <el-form-item label="价格偏离度限制" prop="price_deviation_limit">
          <el-input-number v-model="form.price_deviation_limit" :min="0" :max="0.5" :step="0.01" />
          <div class="help-text">下单价格与市价的最大允许偏差比例</div>
        </el-form-item>

        <el-form-item label="下单频率限制 (次/分)" prop="order_frequency_limit">
          <el-input-number v-model="form.order_frequency_limit" :min="1" :max="600" />
        </el-form-item>

        <el-divider content-position="left">账户风控</el-divider>

        <el-form-item label="每日最大亏损额 (USDT)" prop="max_daily_loss">
          <el-input-number v-model="form.max_daily_loss" :min="0" :step="100" />
        </el-form-item>

        <el-form-item label="风险等级阈值" prop="risk_level_threshold">
          <el-input-number v-model="form.risk_level_threshold" :min="0" :max="1" :step="0.01" />
          <div class="help-text">触发高风险报警的综合评分阈值</div>
        </el-form-item>

        <el-form-item label="启用风控" prop="is_active">
          <el-switch v-model="form.is_active" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="submitForm" :loading="submitting">保存配置</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, reactive } from 'vue'
import { riskControl } from '@/api'
import { ElMessage } from 'element-plus'

export default {
  name: 'Settings',
  setup() {
    const loading = ref(false)
    const submitting = ref(false)
    const accounts = ref([])
    const selectedAccountId = ref(null)
    const formRef = ref(null)

    const form = reactive({
      max_leverage: 20,
      max_position_value: 10000,
      risk_ratio_threshold: 0.8,
      max_single_order: 1000,
      price_deviation_limit: 0.05,
      order_frequency_limit: 10,
      max_daily_loss: 500,
      risk_level_threshold: 0.8,
      is_active: true
    })

    const rules = {
      max_leverage: [{ required: true, message: '请输入最大杠杆', trigger: 'blur' }],
      max_position_value: [{ required: true, message: '请输入最大持仓价值', trigger: 'blur' }],
    }

    const fetchAccounts = async () => {
      try {
        const data = await riskControl.getAccounts()
        accounts.value = data
        if (data.length > 0) {
          selectedAccountId.value = data[0].id
          fetchConfig()
        }
      } catch (error) {
        ElMessage.error('获取账户列表失败')
      }
    }

    const fetchConfig = async () => {
      if (!selectedAccountId.value) return
      loading.value = true
      try {
        const data = await riskControl.getRiskConfig(selectedAccountId.value)
        Object.assign(form, data)
      } catch (error) {
        if (error.response && error.response.status !== 404) {
          ElMessage.error('获取风控配置失败')
        }
      } finally {
        loading.value = false
      }
    }

    const submitForm = async () => {
      if (!formRef.value) return
      await formRef.value.validate(async (valid) => {
        if (valid) {
          submitting.value = true
          try {
            const payload = { ...form, account_id: selectedAccountId.value }
            await riskControl.updateRiskConfig(selectedAccountId.value, payload)
            ElMessage.success('配置已保存')
          } catch (error) {
            ElMessage.error('保存配置失败')
          } finally {
            submitting.value = false
          }
        }
      })
    }

    const resetForm = () => {
      fetchConfig()
    }

    onMounted(() => {
      fetchAccounts()
    })

    return {
      loading,
      submitting,
      accounts,
      selectedAccountId,
      form,
      rules,
      formRef,
      fetchConfig,
      submitForm,
      resetForm
    }
  }
}
</script>

<style scoped>
.settings {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-content {
  background: white;
  padding: 30px;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.risk-form {
  max-width: 800px;
}

.help-text {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 5px;
}
</style>
