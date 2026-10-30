<template>
  <div class="notification-toggle" v-if="isAdmin">
    <span>钉钉通知</span>
    <el-switch :model-value="Boolean(config?.[field])" :loading="loading || saving"
      :disabled="!config || loading || saving" active-text="开启" inactive-text="关闭" @change="save" />
    <el-button v-if="error" link type="danger" size="small" @click="load">读取失败，重试</el-button>
    <span v-else-if="config && !config.enabled" class="muted">总开关已关闭</span>
    <router-link to="/settings">通知设置</router-link>
  </div>
  <span v-else class="muted">钉钉通知由管理员设置</span>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useStore } from 'vuex'
import { ElMessage } from 'element-plus'
import { notificationSettings } from '@/api'

const props = defineProps({ event: { type: String, required: true } })
const store = useStore()
const isAdmin = computed(() => Boolean(store.state.currentUser?.is_admin))
const field = computed(() => `notify_${props.event}`)
const config = ref(null)
const loading = ref(false)
const saving = ref(false)
const error = ref(false)
let requestId = 0
let disposed = false

async function load() {
  if (!isAdmin.value || disposed || saving.value) return
  const id = ++requestId
  loading.value = true
  try {
    const result = await notificationSettings.getDingTalkConfig()
    if (id !== requestId || disposed) return
    config.value = result
    error.value = false
  } catch (_) {
    if (id === requestId && !disposed) { error.value = true; config.value = null }
  } finally {
    if (id === requestId && !disposed) loading.value = false
  }
}

async function save(enabled) {
  const id = ++requestId
  saving.value = true
  try {
    const result = await notificationSettings.updateDingTalkEvent(props.event, enabled)
    if (id !== requestId || disposed) return
    config.value = result
    ElMessage.success(enabled ? '本板块钉钉通知已开启' : '本板块钉钉通知已关闭')
  } catch (err) {
    if (id === requestId && !disposed) ElMessage.error(err.response?.data?.detail || '保存失败，请重试')
  } finally {
    if (id === requestId && !disposed) saving.value = false
  }
}

watch(() => [store.state.currentUser?.id, isAdmin.value], () => {
  requestId += 1
  config.value = null
  loading.value = false
  saving.value = false
  load()
}, { immediate: true })
onMounted(() => window.addEventListener('focus', load))
onUnmounted(() => { disposed = true; requestId += 1; window.removeEventListener('focus', load) })
</script>

<style scoped>
.notification-toggle { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-size: 12px; }
.notification-toggle a { color: #409eff; text-decoration: none; }
.muted { color: #909399; font-size: 12px; }
</style>
