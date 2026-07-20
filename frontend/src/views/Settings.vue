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

    <el-card class="display-time-card">
      <template #header>
        <div class="display-time-card-header">
          <span>时间显示</span>
          <span class="display-time-preview">当前显示 {{ currentDisplayTime }}</span>
        </div>
      </template>

      <div class="display-time-grid">
        <div>
          <div class="display-time-label">显示时区</div>
          <el-select v-model="displayTimezone" placeholder="选择显示时区" @change="handleDisplayTimezoneChange">
            <el-option
              v-for="option in displayTimezoneOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <div class="help-text">后端时间按 UTC 解析，再按这里的时区显示。东八区请选择“北京时间 (UTC+8)”。</div>
        </div>

        <div class="display-time-meta">
          <div class="display-time-label">当前生效时区</div>
          <div class="display-time-value">{{ displayTimezoneLabel }}</div>
          <div class="display-time-subtitle">UTC 偏移：{{ displayTimezoneOffsetLabel }}</div>
          <div class="display-time-subtitle">浏览器系统时区：{{ browserTimezoneLabel }}</div>
        </div>
      </div>
    </el-card>

    <el-card class="notification-card">
      <template #header>
        <div class="display-time-card-header">
          <span>市场洞察 · 钉钉通知</span>
          <el-tag :type="dingTalkForm.enabled && dingTalkMeta.webhook_configured ? 'success' : 'info'">
            {{ dingTalkForm.enabled && dingTalkMeta.webhook_configured ? '已启用' : '未启用' }}
          </el-tag>
        </div>
      </template>

      <el-form label-width="180px" class="risk-form" v-loading="dingTalkLoading">
        <el-form-item label="启用钉钉通知">
          <el-switch v-model="dingTalkForm.enabled" />
          <div class="help-text">启用后由洞察 worker 后台扫描，关闭页面也会继续运行。</div>
        </el-form-item>
        <el-form-item label="机器人 Webhook">
          <el-input
            v-model="dingTalkForm.webhook_url"
            type="password"
            show-password
            :placeholder="dingTalkMeta.webhook_configured ? 'Webhook 已配置，留空表示不修改' : 'https://oapi.dingtalk.com/robot/send?access_token=...'"
          />
          <div class="help-text">仅支持钉钉自定义机器人 HTTPS Webhook，保存后不会再次回显。</div>
        </el-form-item>
        <el-form-item label="加签 Secret">
          <el-input
            v-model="dingTalkForm.secret"
            type="password"
            show-password
            :placeholder="dingTalkMeta.secret_configured ? '加签密钥已配置，留空表示不修改' : 'SEC...（机器人开启加签时填写）'"
          />
          <div class="help-text">推荐机器人开启“加签”；如使用关键词安全设置，请添加关键词 TradeHelper。</div>
        </el-form-item>
        <el-form-item label="通知事件">
          <el-checkbox v-model="dingTalkForm.notify_market_breakout">
            短线量价雷达：放量有效突破
          </el-checkbox>
        </el-form-item>
        <el-form-item label="最低信号评分">
          <el-input-number
            v-model="dingTalkForm.market_min_score"
            :min="0"
            :max="100"
            :step="5"
          />
          <div class="help-text">只推送达到该评分且已突破压力位的信号，建议保持 60 分。</div>
        </el-form-item>
        <el-form-item label="同币种冷却时间">
          <el-input-number
            v-model="dingTalkForm.market_cooldown_minutes"
            :min="5"
            :max="1440"
            :step="5"
          />
          <span class="input-unit">分钟</span>
          <div class="help-text">同一币种在冷却期内只推送一次，防止重复提醒。</div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="dingTalkSaving" @click="saveDingTalkConfig">保存钉钉配置</el-button>
          <el-button :loading="dingTalkTesting" :disabled="!dingTalkMeta.webhook_configured" @click="testDingTalk">发送测试通知</el-button>
        </el-form-item>
      </el-form>
    </el-card>

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
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useStore } from 'vuex'
import { notificationSettings, riskControl } from '@/api'
import { ElMessage } from 'element-plus'
import {
  DISPLAY_TIMEZONE_OPTIONS,
  formatCurrentDateTime,
  getDisplayTimezoneLabel,
  getDisplayTimezoneOffsetLabel,
  resolveDisplayTimezone,
} from '@/utils/datetime'

export default {
  name: 'Settings',
  setup() {
    const store = useStore()
    const loading = ref(false)
    const submitting = ref(false)
    const accounts = ref([])
    const selectedAccountId = ref(null)
    const formRef = ref(null)
    const currentTimeTick = ref(Date.now())
    const dingTalkLoading = ref(false)
    const dingTalkSaving = ref(false)
    const dingTalkTesting = ref(false)
    let currentTimeTimer = null

    const displayTimezoneOptions = DISPLAY_TIMEZONE_OPTIONS
    const browserTimezoneLabel = resolveDisplayTimezone('system')
    const displayTimezone = computed({
      get: () => store.getters.displayTimezone,
      set: (value) => store.dispatch('setDisplayTimezone', value)
    })
    const displayTimezoneLabel = computed(() => getDisplayTimezoneLabel(displayTimezone.value))
    const displayTimezoneOffsetLabel = computed(() => getDisplayTimezoneOffsetLabel(displayTimezone.value))
    const currentDisplayTime = computed(() => {
      currentTimeTick.value
      return formatCurrentDateTime(displayTimezone.value)
    })

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

    const dingTalkForm = reactive({
      enabled: false,
      webhook_url: '',
      secret: '',
      notify_market_breakout: true,
      notify_risk_alert: true,
      market_min_score: 60,
      market_cooldown_minutes: 60
    })
    const dingTalkMeta = reactive({
      webhook_configured: false,
      secret_configured: false
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

    const fetchDingTalkConfig = async () => {
      dingTalkLoading.value = true
      try {
        const data = await notificationSettings.getDingTalkConfig()
        dingTalkForm.enabled = Boolean(data.enabled)
        dingTalkForm.notify_market_breakout = Boolean(data.notify_market_breakout)
        dingTalkForm.notify_risk_alert = Boolean(data.notify_risk_alert)
        dingTalkForm.market_min_score = Number(data.market_min_score ?? 60)
        dingTalkForm.market_cooldown_minutes = Number(data.market_cooldown_minutes ?? 60)
        dingTalkForm.webhook_url = ''
        dingTalkForm.secret = ''
        dingTalkMeta.webhook_configured = Boolean(data.webhook_configured)
        dingTalkMeta.secret_configured = Boolean(data.secret_configured)
      } catch (error) {
        ElMessage.error('获取钉钉配置失败')
      } finally {
        dingTalkLoading.value = false
      }
    }

    const saveDingTalkConfig = async () => {
      dingTalkSaving.value = true
      try {
        const data = await notificationSettings.updateDingTalkConfig({ ...dingTalkForm })
        dingTalkMeta.webhook_configured = Boolean(data.webhook_configured)
        dingTalkMeta.secret_configured = Boolean(data.secret_configured)
        dingTalkForm.webhook_url = ''
        dingTalkForm.secret = ''
        ElMessage.success('钉钉通知配置已保存')
      } catch (error) {
        ElMessage.error(error.response?.data?.detail || '保存钉钉配置失败')
      } finally {
        dingTalkSaving.value = false
      }
    }

    const testDingTalk = async () => {
      dingTalkTesting.value = true
      try {
        await notificationSettings.testDingTalk()
        ElMessage.success('钉钉测试通知已发送')
      } catch (error) {
        ElMessage.error(error.response?.data?.detail || '钉钉测试通知发送失败')
      } finally {
        dingTalkTesting.value = false
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

    const handleDisplayTimezoneChange = (value) => {
      store.dispatch('setDisplayTimezone', value)
      currentTimeTick.value = Date.now()
      ElMessage.success(`时间显示已切换为 ${getDisplayTimezoneLabel(value)} ${getDisplayTimezoneOffsetLabel(value)}`)
    }

    onMounted(() => {
      currentTimeTimer = window.setInterval(() => {
        currentTimeTick.value = Date.now()
      }, 1000)
      fetchAccounts()
      fetchDingTalkConfig()
    })

    onBeforeUnmount(() => {
      if (currentTimeTimer) {
        window.clearInterval(currentTimeTimer)
        currentTimeTimer = null
      }
    })

    return {
      browserTimezoneLabel,
      currentDisplayTime,
      displayTimezone,
      displayTimezoneLabel,
      displayTimezoneOffsetLabel,
      displayTimezoneOptions,
      loading,
      dingTalkForm,
      dingTalkLoading,
      dingTalkMeta,
      dingTalkSaving,
      dingTalkTesting,
      submitting,
      accounts,
      selectedAccountId,
      form,
      rules,
      formRef,
      fetchConfig,
      saveDingTalkConfig,
      testDingTalk,
      handleDisplayTimezoneChange,
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

.display-time-card {
  margin-bottom: 20px;
}

.notification-card {
  margin-bottom: 20px;
}

.notification-card :deep(.el-input) {
  max-width: 620px;
}

.input-unit {
  margin-left: 8px;
  color: #606266;
}

.display-time-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.display-time-preview {
  font-size: 13px;
  color: #606266;
}

.display-time-grid {
  display: grid;
  grid-template-columns: minmax(280px, 420px) minmax(220px, 1fr);
  gap: 24px;
  align-items: start;
}

.display-time-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.display-time-meta {
  padding: 14px 16px;
  border-radius: 12px;
  background: #f8fafc;
}

.display-time-value {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.display-time-subtitle {
  margin-top: 8px;
  font-size: 13px;
  color: #6b7280;
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

@media (max-width: 900px) {
  .display-time-grid {
    grid-template-columns: 1fr;
  }
}
</style>
