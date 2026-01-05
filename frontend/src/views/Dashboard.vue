<template>
  <div class="dashboard">
    <!-- Overview Cards -->
    <el-row :gutter="20" class="overview-cards">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>总持仓价值</span>
              <el-tag :type="positionValueStatus">{{ positionValueStatus }}</el-tag>
            </div>
          </template>
          <div class="card-value">{{ totalPositionValue }}</div>
          <div class="card-change">
            <span :class="{ 'up': dayChange >= 0, 'down': dayChange < 0 }">
              {{ dayChange >= 0 ? '+' : '' }}{{ dayChange }}%
            </span>
            较昨日
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>风险预警数</span>
              <el-tag :type="alertStatus">{{ alertStatus }}</el-tag>
            </div>
          </template>
          <div class="card-value">{{ activeAlerts }}</div>
          <div class="alert-distribution">
            <el-tag type="danger" size="small">高风险: {{ highRiskAlerts }}</el-tag>
            <el-tag type="warning" size="small">中风险: {{ mediumRiskAlerts }}</el-tag>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>日内盈亏</span>
              <el-tag :type="pnlStatus">{{ pnlStatus }}</el-tag>
            </div>
          </template>
          <div class="card-value" :class="{ 'profit': dailyPnL >= 0, 'loss': dailyPnL < 0 }">
            {{ dailyPnL >= 0 ? '+' : '' }}${{ dailyPnL.toLocaleString() }}
          </div>
          <div class="pnl-ratio">收益率: {{ pnlRatio }}%</div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>活跃账户数</span>
            </div>
          </template>
          <div class="card-value">{{ activeAccounts }}</div>
          <div class="account-status">
            正常运行: {{ normalAccounts }} / 异常: {{ abnormalAccounts }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Charts Section -->
    <el-row :gutter="20" class="charts-section">
      <el-col :span="16">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>持仓分布</span>
              <el-select v-model="timeRange" size="small">
                <el-option label="今日" value="today" />
                <el-option label="本周" value="week" />
                <el-option label="本月" value="month" />
              </el-select>
            </div>
          </template>
          <div class="chart-container">
            <div ref="positionChart" style="height: 350px;"></div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>风险分布</span>
            </div>
          </template>
          <div class="chart-container">
            <div ref="riskPieChart" style="height: 350px;"></div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Recent Alerts -->
    <el-card shadow="hover" class="recent-alerts">
      <template #header>
        <div class="card-header">
          <span>最近预警</span>
          <el-button type="text" @click="viewAllAlerts">查看全部</el-button>
        </div>
      </template>
      <el-table :data="recentAlerts" style="width: 100%">
        <el-table-column prop="time" label="时间" width="180" />
        <el-table-column prop="type" label="类型" width="120" />
        <el-table-column prop="account" label="账户" width="120" />
        <el-table-column prop="message" label="详情" />
        <el-table-column prop="risk_level" label="风险等级" width="120">
          <template #default="scope">
            <el-tag :type="getRiskLevelType(scope.row.risk_level)">
              {{ scope.row.risk_level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="scope.row.status === '已处理' ? 'success' : 'danger'">
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { dashboard } from '@/api'

export default {
  name: 'Dashboard',
  setup() {
    const router = useRouter()
    const timeRange = ref('today')
    const positionChart = ref(null)
    const riskPieChart = ref(null)

    // Data refs
    const totalPositionValue = ref('0')
    const positionValueStatus = ref('')
    const dayChange = ref(0)
    const activeAlerts = ref(0)
    const alertStatus = ref('')
    const highRiskAlerts = ref(0)
    const mediumRiskAlerts = ref(0)
    const dailyPnL = ref(0)
    const pnlStatus = ref('')
    const pnlRatio = ref(0)
    const activeAccounts = ref(0)
    const normalAccounts = ref(0)
    const abnormalAccounts = ref(0)
    const recentAlerts = ref([])

    let positionChartInstance = null
    let riskPieChartInstance = null

    const fetchData = async () => {
      try {
        const summary = await dashboard.getSummary()
        totalPositionValue.value = summary.total_position_value
        positionValueStatus.value = summary.position_value_status
        dayChange.value = summary.day_change
        activeAlerts.value = summary.active_alerts
        alertStatus.value = summary.alert_status
        highRiskAlerts.value = summary.high_risk_alerts
        mediumRiskAlerts.value = summary.medium_risk_alerts
        dailyPnL.value = summary.daily_pnl
        pnlStatus.value = summary.pnl_status
        pnlRatio.value = summary.pnl_ratio
        activeAccounts.value = summary.active_accounts
        normalAccounts.value = summary.normal_accounts
        abnormalAccounts.value = summary.abnormal_accounts

        const alerts = await dashboard.getRecentAlerts()
        recentAlerts.value = alerts
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error)
      }
    }

    const updateCharts = async () => {
      try {
        // Position Chart
        const positionData = await dashboard.getPositionChart(timeRange.value)
        if (positionChartInstance) {
          positionChartInstance.setOption({
            xAxis: { data: positionData.xAxis },
            series: positionData.series
          })
        }

        // Risk Chart
        const riskData = await dashboard.getRiskChart()
        if (riskPieChartInstance) {
          riskPieChartInstance.setOption({
            series: [{ data: riskData }]
          })
        }
      } catch (error) {
        console.error('Failed to fetch chart data:', error)
      }
    }

    const initCharts = async () => {
      // Initialize instances
      positionChartInstance = echarts.init(positionChart.value)
      riskPieChartInstance = echarts.init(riskPieChart.value)

      // Set initial options (skeleton)
      positionChartInstance.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['BTC', 'ETH', 'Others'] },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: []
      })

      riskPieChartInstance.setOption({
        tooltip: { trigger: 'item' },
        legend: { orient: 'vertical', left: 'left' },
        series: [{
          name: '风险分布',
          type: 'pie',
          radius: '60%',
          data: [],
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }]
      })

      window.addEventListener('resize', () => {
        positionChartInstance && positionChartInstance.resize()
        riskPieChartInstance && riskPieChartInstance.resize()
      })
      
      await updateCharts()
    }

    watch(timeRange, () => {
      updateCharts()
    })

    const getRiskLevelType = (level) => {
      const types = {
        '高风险': 'danger',
        '中风险': 'warning',
        '低风险': 'success'
      }
      return types[level] || 'info'
    }

    const viewAllAlerts = () => {
      router.push('/risk-alerts')
    }

    onMounted(async () => {
      await fetchData()
      await initCharts()
    })

    return {
      timeRange,
      positionChart,
      riskPieChart,
      totalPositionValue,
      positionValueStatus,
      dayChange,
      activeAlerts,
      alertStatus,
      highRiskAlerts,
      mediumRiskAlerts,
      dailyPnL,
      pnlStatus,
      pnlRatio,
      activeAccounts,
      normalAccounts,
      abnormalAccounts,
      recentAlerts,
      getRiskLevelType,
      viewAllAlerts
    }
  }
}
</script>

<style lang="scss" scoped>
.dashboard {
  .overview-cards {
    margin-bottom: 20px;
    
    .el-card {
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .card-value {
        font-size: 24px;
        font-weight: bold;
        margin: 10px 0;
      }
      
      .card-change {
        font-size: 14px;
        color: #909399;
        
        .up { color: #67C23A; }
        .down { color: #F56C6C; }
      }
      
      .alert-distribution {
        display: flex;
        gap: 10px;
      }
      
      .profit { color: #67C23A; }
      .loss { color: #F56C6C; }
      
      .pnl-ratio, .account-status {
        font-size: 14px;
        color: #909399;
      }
    }
  }
  
  .charts-section {
    margin-bottom: 20px;
    
    .chart-container {
      padding: 10px;
    }
  }
  
  .recent-alerts {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  }
}
</style>
