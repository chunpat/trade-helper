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
        <el-checkbox v-model="showPatterns" @change="handlePatternToggle" style="margin-left: 20px; color: #d1d4dc;">
          显示形态
        </el-checkbox>
      </div>
    </div>
    <div ref="chartRef" class="chart-box"></div>
    
    <!-- 形态快捷导航栏 -->
    <div v-if="detectedPatterns.length > 0" class="pattern-nav">
      <div class="nav-title">已识别形态 (点击跳转):</div>
      <div class="nav-chips">
        <el-tag 
          v-for="(pat, idx) in detectedPatterns" 
          :key="idx"
          :type="pat.direction === 'Bullish' ? 'success' : 'danger'"
          class="nav-chip"
          effect="dark"
          @click="focusOnPattern(pat)"
        >
          {{ pat.name }} ({{ formatDate(pat.points[pat.points.length-1].time) }})
        </el-tag>
      </div>
    </div>
    <div v-else-if="showPatterns" class="pattern-nav empty">
      当前视野未检测到形态
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { createChart, ColorType } from 'lightweight-charts'
import { marketInsight } from '@/api'

const props = defineProps({
  symbol: {
    type: String,
    required: true
  },
  tolerance: {
    type: Number,
    default: 0.2
  }
})

const chartRef = ref(null)
const interval = ref('1h')
const showPatterns = ref(true) 
const detectedPatterns = ref([]) 
let chart = null
let candleSeries = null
let volumeSeries = null
let rsiSeries = null
let patternSeriesList = []
let currentKlines = [] 

defineExpose({
  focusOnPattern
})

onMounted(() => {
  initChart()
  fetchData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.remove()
  }
})

watch(() => props.symbol, () => {
  fetchData()
})

watch(() => props.tolerance, () => {
    fetchData()
})

function handleResize() {
  if (chart && chartRef.value) {
    chart.applyOptions({ width: chartRef.value.clientWidth })
  }
}

function formatDate(ts) {
    return new Date(ts).toLocaleDateString()
}

// Simple RSI Calculation
function calculateRSI(data, period = 14) {
    let rsi = [];
    let gains = [];
    let losses = [];
    
    // Calculate changes
    for (let i = 1; i < data.length; i++) {
        const change = data[i].close - data[i - 1].close;
        gains.push(Math.max(0, change));
        losses.push(Math.max(0, -change));
    }
    
    // Initial average
    let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
    let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
    
    // First RSI
    for (let i = period; i < data.length; i++) {
        // Current index in gain/loss array is i-1
        // We need next gain/loss to update average
        
        // Actually, the loop above for gains/losses results in array length N-1
        // gains[0] corresponds to change between index 0 and 1
        // So average of first 14 gains is indices 0..13
        // This corresponds to data point at index 14
        
        let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        let val = 100 - (100 / (1 + rs));
        
        rsi.push({ time: data[i].time, value: val });
        
        // Smoothed average for next step
        // gains[i] is the NEXT change (between i and i+1)? No.
        // gains[i-1] is change ending at i.
        // Wait, loop structure:
        // i goes from period (14) to end.
        // We want to calculate RSI for point i.
        // The most recent change is change (i-1 to i).
        
        const currentChange = data[i].close - data[i - 1].close;
        const currentGain = Math.max(0, currentChange);
        const currentLoss = Math.max(0, -currentChange);
        
        avgGain = ((avgGain * (period - 1)) + currentGain) / period;
        avgLoss = ((avgLoss * (period - 1)) + currentLoss) / period;
    }
    
    return rsi;
}

function initChart() {
  if (!chartRef.value) return
  
  chart = createChart(chartRef.value, {
    layout: {
      background: { type: ColorType.Solid, color: '#1e1e1e' },
      textColor: '#d1d4dc',
    },
    grid: {
      vertLines: { color: 'rgba(42, 46, 57, 0.5)' },
      horzLines: { color: 'rgba(42, 46, 57, 0.5)' },
    },
    width: chartRef.value.clientWidth,
    height: 600, 
    timeScale: {
        timeVisible: true,
        borderColor: '#485c7b',
    },
    rightPriceScale: {
        borderColor: '#485c7b',
        scaleMargins: {
            top: 0.1,
            bottom: 0.3, // Leave space for RSI
        },
    },
    crosshair: {
        mode: 1 
    }
  })

  // Main Candle Series
  candleSeries = chart.addCandlestickSeries({
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350'
  })
  
  // Volume Series (Overlay)
  volumeSeries = chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: {
          type: 'volume',
      },
      priceScaleId: 'vol',
  })
  
  chart.priceScale('vol').applyOptions({
      scaleMargins: {
          top: 0.7, 
          bottom: 0.1,
      },
  })
  
  // RSI Series
  rsiSeries = chart.addLineSeries({
      color: 'rgba(255, 165, 0, 1)',
      lineWidth: 2,
      priceScaleId: 'rsi',
  })
  
  chart.priceScale('rsi').applyOptions({
      scaleMargins: {
          top: 0.75,
          bottom: 0.02,
      },
  })
  
  // Add RSI Levels
  rsiSeries.createPriceLine({
      price: 70,
      color: 'rgba(255, 255, 255, 0.4)',
      lineWidth: 1,
      lineStyle: 2, 
      axisLabelVisible: false,
  });
  rsiSeries.createPriceLine({
      price: 30,
      color: 'rgba(255, 255, 255, 0.4)',
      lineWidth: 1,
      lineStyle: 2, 
      axisLabelVisible: false,
  });
}

function handlePatternToggle() {
  fetchData()
}

function focusOnPattern(pattern) {
    if (!pattern || !pattern.points || pattern.points.length === 0) return
    
    // Pattern points are objects { index, price, time(ms) }
    const points = [...pattern.points].sort((a,b) => a.time - b.time)
    
    const startTime = points[0].time / 1000
    const endTime = points[points.length - 1].time / 1000
    
    const range = endTime - startTime
    const padding = Math.max(range * 0.5, 3600 * 5)
    
    chart.timeScale().setVisibleRange({
        from: startTime - padding,
        to: endTime + padding
    })
}

async function fetchData() {
  if (!props.symbol) return
  
  try {
    const limit = 1500
    const klinePromise = marketInsight.getKlines({
      symbol: props.symbol,
      interval: interval.value,
      limit: limit 
    })
    
    let patternPromise = Promise.resolve([])
    if (showPatterns.value) {
      patternPromise = marketInsight.getPatterns({
        symbol: props.symbol,
        interval: interval.value,
        limit: limit, 
        tolerance: props.tolerance
      })
    }
    
    const [klines, patterns] = await Promise.all([klinePromise, patternPromise])
    currentKlines = klines
    detectedPatterns.value = patterns || []
    
    detectedPatterns.value.sort((a,b) => b.points[b.points.length-1].time - a.points[a.points.length-1].time)
    
    renderChart(klines, patterns)
    
  } catch (error) {
    console.error('Failed to fetch data:', error)
  }
}

function renderChart(rawData, patterns = []) {
  if (!chart || !candleSeries) return

  const data = rawData.map(item => ({
    time: item[0] / 1000, 
    open: parseFloat(item[1]),
    high: parseFloat(item[2]),
    low: parseFloat(item[3]),
    close: parseFloat(item[4]),
    volume: parseFloat(item[5])
  }))
  
  const uniqueData = []
  const timeSet = new Set()
  for(const d of data) {
      if(!timeSet.has(d.time)) {
          timeSet.add(d.time)
          uniqueData.push(d)
      }
  }
  uniqueData.sort((a, b) => a.time - b.time)

  candleSeries.setData(uniqueData)

  // Volume
  const volumeData = uniqueData.map(d => ({
      time: d.time,
      value: d.volume,
      color: d.close >= d.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
  }))
  volumeSeries.setData(volumeData)
  
  // RSI
  const rsiData = calculateRSI(uniqueData)
  rsiSeries.setData(rsiData)
  
  // Patterns
  patternSeriesList.forEach(s => chart.removeSeries(s))
  patternSeriesList = []
  
  if (patterns && patterns.length > 0) {
    const markers = []
    
    patterns.forEach((pat) => {
        const color = pat.direction === 'Bullish' ? '#00E396' : (pat.direction === 'Bearish' ? '#FF4560' : '#B2B5BE')
        const lastPoint = pat.points[pat.points.length - 1]
        
        markers.push({
            time: lastPoint.time / 1000,
            position: pat.direction === 'Bullish' ? 'belowBar' : (pat.direction === 'Bearish' ? 'aboveBar' : 'inBar'),
            color: color,
            shape: pat.direction === 'Bullish' ? 'arrowUp' : (pat.direction === 'Bearish' ? 'arrowDown' : 'circle'),
            text: pat.name,
            size: 1
        })
    })
    
    markers.sort((a,b) => a.time - b.time)
    candleSeries.setMarkers(markers)
  } else {
    candleSeries.setMarkers([])
  }
}
</script>

<style scoped>
.kline-container {
  width: 100%;
  height: 600px;
  background-color: #1e1e1e;
  border-radius: 4px;
  padding: 10px;
  display: flex;
  flex-direction: column;
}

.kline-header {
  height: 40px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  margin-bottom: 10px;
}

.symbol-info {
  display: flex;
  align-items: center;
  gap: 20px;
}

.symbol-name {
  color: #d1d4dc;
  font-weight: bold;
  font-size: 16px;
}

.chart-box {
  flex: 1;
  width: 100%;
  min-height: 480px;
}

.pattern-nav {
  height: 60px;
  border-top: 1px solid #333;
  padding: 10px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background-color: #252525;
}

.nav-title {
  font-size: 12px;
  color: #888;
  margin-bottom: 5px;
}

.nav-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  white-space: nowrap;
  padding-bottom: 2px;
}

.nav-chip {
  cursor: pointer;
  transition: all 0.2s;
}

.nav-chip:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.5);
}

.pattern-nav.empty {
  color: #555;
  align-items: center;
  font-style: italic;
}

/* Scrollbar for nav-chips */
.nav-chips::-webkit-scrollbar {
  height: 4px;
}
.nav-chips::-webkit-scrollbar-thumb {
  background: #444;
  border-radius: 2px;
}
</style>
