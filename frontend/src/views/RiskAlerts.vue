<template>
  <div class="risk-alerts">
    <div class="header">
      <h1>风险预警</h1>
      <div class="filters">
        <el-select v-model="filters.risk_level" placeholder="风险等级" clearable @change="fetchAlerts" style="width: 120px">
          <el-option label="低风险" value="low" />
          <el-option label="中风险" value="medium" />
          <el-option label="高风险" value="high" />
          <el-option label="极高风险" value="critical" />
        </el-select>
        <el-select v-model="filters.is_resolved" placeholder="状态" clearable @change="fetchAlerts" style="width: 120px">
          <el-option label="全部" :value="null" />
          <el-option label="未处理" :value="false" />
          <el-option label="已处理" :value="true" />
        </el-select>
        <el-button type="primary" @click="fetchAlerts">刷新</el-button>
      </div>
    </div>

    <div class="page-content">
      <el-table :data="alerts" v-loading="loading" style="width: 100%">
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="account_id" label="账户ID" width="100" />
        <el-table-column prop="alert_type" label="类型" width="150" />
        <el-table-column prop="risk_level" label="风险等级" width="120">
          <template #default="scope">
            <el-tag :type="getRiskLevelType(scope.row.risk_level)">
              {{ getRiskLevelLabel(scope.row.risk_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="消息" />
        <el-table-column prop="is_resolved" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.is_resolved ? 'success' : 'danger'">
              {{ scope.row.is_resolved ? '已处理' : '未处理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button 
              v-if="!scope.row.is_resolved"
              size="small" 
              type="primary" 
              @click="handleResolve(scope.row)"
            >
              处理
            </el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <!-- Resolve Dialog -->
    <el-dialog v-model="resolveDialogVisible" title="处理预警" width="500px">
      <el-form :model="resolveForm" label-width="80px">
        <el-form-item label="处理备注">
          <el-input 
            v-model="resolveForm.notes" 
            type="textarea" 
            rows="3"
            placeholder="请输入处理备注"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="resolveDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitResolve" :loading="submitting">
            确定
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { riskControl } from '@/api'
import { ElMessage } from 'element-plus'

const alerts = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const filters = reactive({
  risk_level: '',
  is_resolved: false // Default to showing unresolved
})

const resolveDialogVisible = ref(false)
const submitting = ref(false)
const resolveForm = reactive({
  id: null,
  notes: ''
})

const fetchAlerts = async () => {
  loading.value = true
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
      ...filters
    }
    // Filter out empty strings/nulls
    if (!params.risk_level) delete params.risk_level
    if (params.is_resolved === null) delete params.is_resolved

    const data = await riskControl.getRiskAlerts(params)
    alerts.value = data
    // Since backend doesn't return total count, we'll just set it to a large number if we got a full page
    // This is a temporary workaround until backend supports pagination metadata
    if (data.length === pageSize.value) {
        total.value = currentPage.value * pageSize.value + pageSize.value
    } else {
        total.value = (currentPage.value - 1) * pageSize.value + data.length
    }
  } catch (error) {
    console.error('Failed to fetch alerts:', error)
    ElMessage.error('获取预警列表失败')
  } finally {
    loading.value = false
  }
}

const handleSizeChange = (val) => {
  pageSize.value = val
  fetchAlerts()
}

const handleCurrentChange = (val) => {
  currentPage.value = val
  fetchAlerts()
}

const handleResolve = (row) => {
  resolveForm.id = row.id
  resolveForm.notes = ''
  resolveDialogVisible.value = true
}

const submitResolve = async () => {
  submitting.value = true
  try {
    await riskControl.resolveAlert(resolveForm.id, resolveForm.notes)
    ElMessage.success('处理成功')
    resolveDialogVisible.value = false
    fetchAlerts()
  } catch (error) {
    console.error('Failed to resolve alert:', error)
    ElMessage.error('处理失败')
  } finally {
    submitting.value = false
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

const getRiskLevelType = (level) => {
  const map = {
    low: 'info',
    medium: 'warning',
    high: 'danger',
    critical: 'danger'
  }
  return map[level] || 'info'
}

const getRiskLevelLabel = (level) => {
  const map = {
    low: '低风险',
    medium: '中风险',
    high: '高风险',
    critical: '极高风险'
  }
  return map[level] || level
}

onMounted(() => {
  fetchAlerts()
})
</script>

<style scoped>
.risk-alerts {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.filters {
  display: flex;
  gap: 10px;
}

.page-content {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
