<template>
  <div class="kline-container">
    <div class="kline-header">
      <div class="symbol-info">
        <span class="symbol-name">{{ symbol }}</span>
        <el-radio-group v-model="interval" size="small" @change="fetchData">
          <el-radio-button label="15m">15m</el-radio-button>
          <el-radio-button label="1h">1h</el-radio-button>
          <el-radio-button label="4h">4h</el-radio-button>
          <el-radio-button label="1d">1d</el-radio-button>
        </el-radio-group>
      </div>
    </div>
    <div ref="chartRef" class="chart-box"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { marketInsight } from '@/api'

const props = defineProps({
  symbol: {
    type: String,
    required: true
  }
})

const chartRef = ref(null)
const interval = ref('1h')
let chart = null

onMounted(() => {
  initChart()
  fetchData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
  }
})

watch(() => props.symbol, () => {
  fetchData()
})

function handleResize() {
  if (chart) {
    chart.resize()
  }
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
}

async function fetchData() {
  if (!props.symbol) return
  
  try {
    const response = await marketInsight.getKlines({
      symbol: props.symbol,
      interval: interval.value,
      limit: 100
    })
    
    renderChart(response)
  } catch (error) {
    console.error('Failed to fetch klines:', error)
  }
}

function renderChart(rawData) {
  // Binance Kline format: [o_time, open, high, low, close, vol, c_time, ...]
  const dates = []
  const values = []
  const volumes = []

  rawData.forEach(item => {
    dates.push(echarts.format.formatTime('yyyy-MM-dd hh:mm', item[0]))
    // values: [open, close, low, high]
    values.push([
      parseFloat(item[1]), 
      parseFloat(item[4]), 
      parseFloat(item[3]), 
      parseFloat(item[2])
    ])
    volumes.push(parseFloat(item[5]))
  })

  const option = {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      },
      borderWidth: 1,
      borderColor: '#ccc',
      padding: 10,
      textStyle: {
        color: '#000'
      },
      position: function (pos, params, el, elRect, size) {
        const obj = { top: 10 };
        obj[['left', 'right'][+(pos[0] < size.viewSize[0] / 2)]] = 30;
        return obj;
      }
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: {
        backgroundColor: '#777'
      }
    },
    grid: [
      {
        left: '5%',
        right: '5%',
        height: '65%'
      },
      {
        left: '5%',
        right: '5%',
        top: '75%',
        height: '15%'
      }
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        splitLine: { show: false },
        min: 'dataMin',
        max: 'dataMax',
        axisPointer: {
          z: 100
        }
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: false,
        axisLine: { onZero: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        min: 'dataMin',
        max: 'dataMax'
      }
    ],
    yAxis: [
      {
        scale: true,
        splitArea: {
          show: true
        }
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false }
      }
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 50,
        end: 100
      },
      {
        show: true,
        xAxisIndex: [0, 1],
        type: 'slider',
        top: '92%',
        start: 50,
        end: 100
      }
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: values,
        itemStyle: {
          color: '#ef232a',
          color0: '#14b143',
          borderColor: '#ef232a',
          borderColor0: '#14b143'
        }
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: {
          color: '#83bff6'
        }
      }
    ]
  };

  chart.setOption(option)
}
</script>

<style scoped>
.kline-container {
  width: 100%;
  background: #fff;
}

.kline-header {
  padding: 10px 15px;
  border-bottom: 1px solid #eee;
}

.symbol-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.symbol-name {
  font-size: 18px;
  font-weight: bold;
}

.chart-box {
  width: 100%;
  height: 450px;
}
</style>
