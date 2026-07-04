<template>
  <div class="market-insight">
    <el-page-header @back="$router.back()" :content="pageTitle" class="page-header" />
    
    <!-- 市场总览 -->
    <el-card class="overview-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>市场总览</span>
          <el-button 
            :icon="Refresh" 
            circle 
            size="small" 
            @click="refreshData"
            :loading="loading"
          />
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">24H总成交量</div>
            <div class="stat-value">${{ formatNumber(overview.total_volume_24h) }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">总市值</div>
            <div class="stat-value">${{ formatNumber(overview.total_market_cap) }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">BTC市值占比</div>
            <div class="stat-value">{{ overview.btc_dominance?.toFixed(2) }}%</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-item">
            <div class="stat-label">活跃币种</div>
            <div class="stat-value">{{ overview.active_cryptocurrencies }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- GPT-5.1 AI 分析 -->
    <el-card v-if="aiAnalysis" class="ai-analysis-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>🤖 GPT-5.1 深度市场解析</span>
          <el-tag size="small" type="success" effect="dark">AI Powered</el-tag>
        </div>
      </template>
      <div class="ai-content" v-html="renderMarkdown(aiAnalysis)"></div>
    </el-card>

    <!-- K 线图 -->
    <el-card class="kline-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>📊 行情与 K 线形态</span>
          </div>
          <div class="header-controls">
            <div class="pattern-strictness-control">
              <span class="control-label">识别严格度</span>
              <el-select
                v-model="patternTolerance"
                size="small"
                class="strictness-select"
                @change="handlePatternToleranceChange"
              >
                <el-option
                  v-for="option in patternToleranceOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </div>

            <el-popover placement="bottom-end" :width="320" trigger="click">
              <template #reference>
                <el-button size="small" plain>
                  形态筛选 ({{ selectedPatternTypes.length }}/{{ patternFilterOptions.length }})
                </el-button>
              </template>
              <div class="pattern-filter-panel">
                <div class="filter-panel-title">勾选要显示的形态类型</div>
                <el-checkbox-group v-model="selectedPatternTypes" class="pattern-filter-group">
                  <el-checkbox
                    v-for="option in patternFilterOptions"
                    :key="option.value"
                    :label="option.value"
                  >
                    {{ option.label }}
                  </el-checkbox>
                </el-checkbox-group>
                <div class="pattern-filter-actions">
                  <el-button text size="small" @click="selectAllPatternTypes">全选</el-button>
                  <el-button text size="small" @click="clearPatternTypes">清空</el-button>
                </div>
              </div>
            </el-popover>
          </div>
        </div>
      </template>
      <KlineChart 
        ref="chartRef"
        :symbol="currentChartSymbol" 
        :tolerance="patternTolerance"
        :selected-pattern-types="selectedPatternTypes"
      />
    </el-card>

    <!-- K线形态捕捉器 -->
    <el-card class="scanner-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>🕯️ K线形态捕捉器 (Candlestick Patterns)</span>
          </div>
          <div class="header-controls">
            <el-tag size="small" type="info" effect="plain">
              当前筛选 {{ selectedPatternTypes.length }}/{{ patternFilterOptions.length }} 类形态
            </el-tag>
            <el-button 
              type="primary" 
              size="small" 
              :loading="scanning"
              @click="scanPatterns"
            >
              扫描形态
            </el-button>
          </div>
        </div>
      </template>
      
      <div v-if="scanning" class="scanning-placeholder">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在扫描市场Top20活跃币种以及潜在机会...</span>
      </div>

      <div v-if="!scanning && filteredScanResults.length === 0" class="empty-scan">
        {{ scanResults.length > 0 ? '当前筛选下暂无形态，请调整筛选或严格度。' : '暂无发现近期形态，请稍后刷新。' }}
      </div>

      <el-row v-else :gutter="16">
        <el-col 
          v-for="(res, idx) in filteredScanResults" 
          :key="idx"
          :xs="24" :sm="12" :md="6"
        >
          <div 
            class="scan-item" 
            :class="res.pattern.direction === 'Bullish' ? 'bullish' : 'bearish'"
            @click="handlePatternClick(res)"
          >
            <div class="scan-header">
              <span class="scan-symbol">{{ formatSymbol(res.symbol) }}</span>
              <el-tag size="small" :type="res.pattern.direction === 'Bullish' ? 'success' : 'danger'">
                {{ res.pattern.direction }}
              </el-tag>
            </div>
            <div class="scan-body">
              <div class="pattern-name">{{ res.pattern.name }}</div>
              <div class="pattern-info">
                周期: 1H | 
                <span v-if="res.pattern.name.includes('Potential')">潜在反转区</span>
                <span v-else>形态完成</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 异常代币监控 -->
    <el-card class="anomaly-card" shadow="hover">
      <template #header>
        <div class="card-header anomaly-header">
          <div class="header-left">
            <span>异常代币监控</span>
            <el-tag size="small" type="warning" effect="plain">
              Binance 前100成交额持续扫描
            </el-tag>
          </div>
          <div class="header-controls">
            <el-tag v-if="lastAnomalyScanAt" size="small" type="info" effect="plain">
              最近扫描 {{ formatDateTime(lastAnomalyScanAt) }}
            </el-tag>
            <el-button
              type="warning"
              plain
              size="small"
              :loading="anomalyScanLoading"
              @click="triggerAnomalyScan"
            >
              立即扫描
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        v-if="activeAnomalies.length > 0"
        :data="activeAnomalies"
        stripe
        size="small"
        @row-click="openAnomalyDetail"
        row-class-name="clickable-row"
      >
        <el-table-column label="币种" min-width="110">
          <template #default="{ row }">
            <strong>{{ formatSymbol(row.symbol) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="异常等级" width="110">
          <template #default="{ row }">
            <el-tag :type="getAnomalyLevelTagType(row.anomaly_level)" size="small">
              {{ getAnomalyLevelLabel(row.anomaly_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常分" width="90" align="right">
          <template #default="{ row }">
            {{ (row.anomaly_score * 100).toFixed(0) }}
          </template>
        </el-table-column>
        <el-table-column label="24H涨跌" width="120" align="right">
          <template #default="{ row }">
            <el-tag :type="row.price_change_percent_24h >= 0 ? 'success' : 'danger'" size="small">
              {{ row.price_change_percent_24h >= 0 ? '+' : '' }}{{ safeFixed(row.price_change_percent_24h, 2) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="真实性" width="120">
          <template #default="{ row }">
            <el-tag :type="getCredibilityTagType(row.credibility_label)" size="small">
              {{ row.credibility_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" min-width="180">
          <template #default="{ row }">
            <span class="source-summary">{{ row.source_summary || '暂无可靠来源' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="建议" width="100">
          <template #default="{ row }">
            <el-tag :type="getTradeBiasTagType(row.trade_bias)" size="small" effect="dark">
              {{ getTradeBiasLabel(row.trade_bias) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-else
        description="暂无活跃异常事件，系统会后台持续扫描前100成交额币种。"
      />
    </el-card>

    <!-- 交易信号 -->
    <el-card v-if="signals.length > 0" class="signals-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>🎯 交易信号</span>
          <el-tag size="small" type="info">基于市场情绪和价格分析</el-tag>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col 
          v-for="signal in signals" 
          :key="signal.symbol"
          :xs="24" :sm="12" :md="8"
        >
          <div class="signal-item" :class="`signal-${signal.signal_type}`">
            <div class="signal-header">
              <span class="signal-symbol">{{ formatSymbol(signal.symbol) }}</span>
              <el-tag 
                :type="getSignalTagType(signal.signal_type)"
                size="small"
              >
                {{ getSignalLabel(signal.signal_type) }}
              </el-tag>
            </div>
            <el-progress 
              :percentage="signal.strength" 
              :color="getSignalColor(signal.signal_type)"
              :show-text="false"
            />
            <div class="signal-strength">信号强度: {{ signal.strength.toFixed(0) }}</div>
            <div class="signal-reasons">
              <div v-for="(reason, idx) in signal.reasons" :key="idx" class="reason">
                • {{ reason }}
              </div>
            </div>
            <div v-if="signal.suggested_entry" class="signal-prices">
              <div class="price-item entry">
                <span class="label">建仓:</span>
                <span class="value">${{ formatPrice(signal.suggested_entry) }}</span>
              </div>
              <div class="price-row">
                <div class="price-item sl">
                  <span class="label">止损:</span>
                  <span class="value danger">${{ formatPrice(signal.suggested_stop_loss) }}</span>
                </div>
                <div class="price-item tp">
                  <span class="label">止盈:</span>
                  <span class="value success">${{ formatPrice(signal.suggested_take_profit) }}</span>
                </div>
              </div>
              <div class="rr-ratio">
                期望盈亏比: <el-tag size="mini" type="info">{{ getRRRatioLabel(signal) }}</el-tag>
              </div>
              <div v-if="signal.signal_type === 'neutral' && signal.sl_percent" class="neutral-prices">
                <div class="neutral-direction long-dir">做多参考：止损 ${{ formatPrice(signal.suggested_entry * (1 - signal.sl_percent)) }} / 止盈 ${{ formatPrice(signal.suggested_entry * (1 + signal.tp_percent)) }}</div>
                <div class="neutral-direction short-dir">做空参考：止损 ${{ formatPrice(signal.suggested_entry * (1 + signal.sl_percent)) }} / 止盈 ${{ formatPrice(signal.suggested_entry * (1 - signal.tp_percent)) }}</div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 市场情绪 & 宏观 -->
    <el-row :gutter="16" class="sentiment-rankings">
      <!-- 恐惧贪婪指数 -->
      <el-col :xs="24" :md="12">
        <el-card class="sentiment-macro-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>😱 恐惧与贪婪指数</span>
              <el-tag v-if="fearGreedIndex" :type="getFngTagType(fearGreedIndex.value_classification)">
                {{ fearGreedIndex.value_classification }} ({{ fearGreedIndex.value }})
              </el-tag>
            </div>
          </template>
          <div class="macro-compact-card">
            <div class="macro-summary-row">
              <div class="macro-hero">
                <div class="macro-hero-label">当前情绪</div>
                <div class="macro-hero-value" :style="{ color: getFngColor(fearGreedIndex?.value) }">
                  {{ fearGreedIndex?.value ?? '--' }}
                </div>
                <div class="macro-hero-subtitle">{{ fearGreedIndex?.value_classification || '暂无数据' }}</div>
              </div>
              <div class="macro-meta-list">
                <div class="macro-meta-item">
                  <span class="meta-label">30日均值</span>
                  <strong class="meta-value">{{ fearGreed30DayAverageLabel }}</strong>
                </div>
                <div class="macro-meta-item">
                  <span class="meta-label">近一日变化</span>
                  <strong class="meta-value" :class="fearGreedDeltaClass">{{ fearGreedDeltaLabel }}</strong>
                </div>
              </div>
            </div>
            <div ref="fearGreedChartRef" class="macro-chart"></div>
          </div>
        </el-card>
      </el-col>

      <!-- 彩虹图价格带 -->
      <el-col :xs="24" :md="12">
        <el-card class="sentiment-macro-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>🌈 BTC 彩虹图指标</span>
              <el-tag v-if="btcCurrentPrice" type="info" size="small">
                BTC: ${{ formatNumber(btcCurrentPrice) }}
              </el-tag>
            </div>
          </template>
          <div class="macro-compact-card">
            <div class="macro-summary-row">
              <div class="macro-hero">
                <div class="macro-hero-label">当前区间</div>
                <div class="macro-hero-value rainbow-price">${{ formatNumber(btcCurrentPrice) }}</div>
                <div class="macro-hero-subtitle">{{ rainbowCurrentBandLabel }}</div>
              </div>
              <div class="macro-meta-list">
                <div class="macro-meta-item">
                  <span class="meta-label">参考线</span>
                  <strong class="meta-value">{{ rainbowReferencePriceLabel }}</strong>
                </div>
                <div class="macro-meta-item">
                  <span class="meta-label">相对偏离</span>
                  <strong class="meta-value">{{ rainbowDistanceLabel }}</strong>
                </div>
              </div>
            </div>
            <div ref="rainbowChartRef" class="macro-chart"></div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 市场情绪细节 -->
    <el-card class="sentiment-card" shadow="hover">
      <template #header>
        <span>💭 合约市场统计</span>
      </template>
      <el-row :gutter="16">
        <el-col 
          v-for="item in sentiment" 
          :key="item.symbol"
          :xs="24" :sm="12" :md="8"
        >
          <div class="sentiment-item">
            <div class="sentiment-header">
              <span class="symbol">{{ formatSymbol(item.symbol) }}</span>
              <el-tag 
                :type="getSentimentTagType(item.sentiment_score)"
                size="small"
              >
                {{ getSentimentLabel(item.sentiment_score) }}
              </el-tag>
            </div>
            <div class="sentiment-data">
              <div class="data-row">
                <span class="label">资金费率:</span>
                <span :class="getFundingRateClass(item.funding_rate)">
                  {{ (item.funding_rate * 100).toFixed(4) }}%
                </span>
              </div>
              <div class="data-row">
                <span class="label">多空比:</span>
                <span :class="getLongShortRatioClass(item.long_short_ratio)">
                  {{ item.long_short_ratio?.toFixed(2) }}
                </span>
              </div>
              <div class="data-row" v-if="item.open_interest">
                <span class="label">未平仓合约:</span>
                <span>{{ formatNumber(item.open_interest) }}</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 排行榜 -->
    <el-row :gutter="16" class="rankings">
      <!-- 山寨币放量启动榜 -->
      <el-col :xs="24" :md="16">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>🚀 山寨币放量启动榜</span>
              <el-tooltip content="筛选15分钟成交量明显放大、近1小时刚转强且24H涨幅未透支的币；不是24H涨幅排名。" placement="top">
                <el-tag type="warning" effect="plain" size="small">不追 24H 榜一</el-tag>
              </el-tooltip>
            </div>
          </template>
          <el-table 
            :data="altcoinStarters"
            size="small"
            @row-click="selectSymbol"
            row-class-name="clickable-row"
          >
            <el-table-column label="币种" min-width="110">
              <template #default="{ row }">
                <span class="symbol-name">{{ formatSymbol(row.symbol) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="现价" min-width="110" align="right">
              <template #default="{ row }">
                <span class="price">${{ row.last_price.toFixed(row.last_price < 1 ? 4 : 2) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="15m量比" min-width="90" align="right">
              <template #default="{ row }">
                <strong class="startup-volume">{{ safeFixed(row.volume_ratio, 1) }}x</strong>
              </template>
            </el-table-column>
            <el-table-column label="近1H" min-width="90" align="right">
              <template #default="{ row }">
                <el-tag type="success" size="small">+{{ safeFixed(row.momentum_1h, 2) }}%</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="24H" min-width="90" align="right">
              <template #default="{ row }">
                <span>+{{ safeFixed(row.price_change_percent_24h, 2) }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="启动分" min-width="85" align="right">
              <template #default="{ row }">
                <el-tag type="warning" size="small">{{ safeFixed(row.startup_score, 0) }}</el-tag>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂未发现符合条件的早期放量标的" :image-size="60" />
            </template>
          </el-table>
        </el-card>
      </el-col>

      <!-- 成交量榜 -->
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>
            <span>💰 合约成交量榜</span>
          </template>
          <el-table 
            :data="topVolume" 
            :show-header="false" 
            size="small"
            @row-click="selectSymbol"
            row-class-name="clickable-row"
          >
            <el-table-column width="150">
              <template #default="{ row }">
                <span class="symbol-name">{{ formatSymbol(row.symbol) }}</span>
              </template>
            </el-table-column>
            <el-table-column align="right">
              <template #default="{ row }">
                <span class="volume">${{ formatNumber(row.volume_24h) }}</span>
              </template>
            </el-table-column>
            <el-table-column width="100" align="right">
              <template #default="{ row }">
                <el-tag 
                  :type="row.price_change_percent_24h > 0 ? 'success' : 'danger'" 
                  size="small"
                >
                  {{ row.price_change_percent_24h > 0 ? '+' : '' }}{{ row.price_change_percent_24h.toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 资金费率排行 (Coinglass 聚合/Binance 合约) -->
    <el-row :gutter="16" class="rankings" style="margin-top: 20px;">
      <!-- 正费率榜 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>🚀 资金费率排行榜 (Highest)</span>
              <el-tag size="small" type="success">多头情绪高涨</el-tag>
            </div>
          </template>
          <el-table :data="fundingRateHigh" size="small" @row-click="selectSymbol" row-class-name="clickable-row">
            <el-table-column prop="symbol" label="交易对" width="120">
               <template #default="{ row }">
                <span class="symbol-name">{{ formatSymbol(row.symbol) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="rate" label="8H费率" align="right">
              <template #default="{ row }">
                <span class="bullish-text" style="font-weight: bold;">{{ row.rate.toFixed(4) }}%</span>
              </template>
            </el-table-column>
            <el-table-column prop="exchange" label="来源" align="right" width="80" />
          </el-table>
        </el-card>
      </el-col>

      <!-- 负费率榜 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>🩸 资金费率排行榜 (Lowest)</span>
              <el-tag size="small" type="danger">空头极度密集</el-tag>
            </div>
          </template>
          <el-table :data="fundingRateLow" size="small" @row-click="selectSymbol" row-class-name="clickable-row">
            <el-table-column prop="symbol" label="交易对" width="120">
               <template #default="{ row }">
                <span class="symbol-name">{{ formatSymbol(row.symbol) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="rate" label="8H费率" align="right">
              <template #default="{ row }">
                <span class="bearish-text" style="font-weight: bold;">{{ row.rate.toFixed(4) }}%</span>
              </template>
            </el-table-column>
            <el-table-column prop="exchange" label="来源" align="right" width="80" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 自选币种 -->
    <el-card shadow="hover" style="margin-top: 20px">
      <template #header>
        <div class="card-header">
          <span>⭐ 自选币种</span>
          <el-button size="small" type="primary" plain @click="showWatchlistDialog = true">
            管理自选
          </el-button>
        </div>
      </template>
      <el-table 
        :data="watchlist" 
        stripe
        @row-click="selectSymbol"
        row-class-name="clickable-row"
        v-loading="loading && watchlist.length === 0"
      >
        <template #empty>
          <el-empty description="暂无自选币种，请点击管理自选添加" />
        </template>
        <el-table-column label="币种" width="120">
          <template #default="{ row }">
            <strong>{{ formatSymbol(row.symbol) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="最新价" align="right">
          <template #default="{ row }">
            ${{ row.last_price.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="24H涨跌" align="right">
          <template #default="{ row }">
            <el-tag 
              :type="row.price_change_percent_24h > 0 ? 'success' : 'danger'"
              size="small"
            >
              {{ row.price_change_percent_24h > 0 ? '+' : '' }}{{ row.price_change_percent_24h.toFixed(2) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="24H最高" align="right">
          <template #default="{ row }">
            ${{ row.high_24h.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="24H最低" align="right">
          <template #default="{ row }">
            ${{ row.low_24h.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="24H成交量" align="right">
          <template #default="{ row }">
            ${{ formatNumber(row.volume_24h) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 管理自选对话框 -->
    <el-dialog 
      v-model="showWatchlistDialog" 
      title="管理自选币种"
      width="500px"
    >
      <el-input
        v-model="newWatchSymbol"
        placeholder="输入币种符号，如: BTCUSDT"
        @keyup.enter="addToWatchlist"
      >
        <template #append>
          <el-button @click="addToWatchlist">添加</el-button>
        </template>
      </el-input>
      <div class="watchlist-items">
        <el-tag
          v-for="symbol in userWatchlist"
          :key="symbol"
          closable
          @close="removeFromWatchlist(symbol)"
          style="margin: 5px"
        >
          {{ formatSymbol(symbol) }}
        </el-tag>
      </div>
    </el-dialog>

    <el-drawer
      v-model="anomalyDrawerVisible"
      title="异常事件详情"
      size="45%"
    >
      <div v-loading="anomalyDetailLoading">
        <template v-if="selectedAnomaly">
          <div class="anomaly-detail-header">
            <div>
              <div class="detail-symbol">{{ formatSymbol(selectedAnomaly.symbol) }}</div>
              <div class="detail-meta">{{ formatDateTime(selectedAnomaly.last_detected_at) }} 更新</div>
            </div>
            <div class="detail-tags">
              <el-tag :type="getAnomalyLevelTagType(selectedAnomaly.anomaly_level)">
                {{ getAnomalyLevelLabel(selectedAnomaly.anomaly_level) }}
              </el-tag>
              <el-tag :type="getCredibilityTagType(selectedAnomaly.credibility_label)">
                {{ selectedAnomaly.credibility_label }}
              </el-tag>
              <el-tag :type="getTradeBiasTagType(selectedAnomaly.trade_bias)" effect="dark">
                {{ getTradeBiasLabel(selectedAnomaly.trade_bias) }}
              </el-tag>
            </div>
          </div>

          <el-descriptions :column="2" border class="anomaly-descriptions">
            <el-descriptions-item label="事件类型">{{ selectedAnomaly.event_type }}</el-descriptions-item>
            <el-descriptions-item label="异常分">{{ (selectedAnomaly.anomaly_score * 100).toFixed(0) }}</el-descriptions-item>
            <el-descriptions-item label="24H涨跌">
              {{ safeFixed(selectedAnomaly.price_change_percent_24h, 2) }}%
            </el-descriptions-item>
            <el-descriptions-item label="24H成交额">
              ${{ formatNumber(selectedAnomaly.quote_volume_24h) }}
            </el-descriptions-item>
            <el-descriptions-item label="资金费率">
              {{ selectedAnomaly.funding_rate != null ? `${(selectedAnomaly.funding_rate * 100).toFixed(4)}%` : '--' }}
            </el-descriptions-item>
            <el-descriptions-item label="多空比">
              {{ selectedAnomaly.long_short_ratio != null ? selectedAnomaly.long_short_ratio.toFixed(2) : '--' }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="detail-section" v-if="selectedAnomaly.trigger_reasons?.length">
            <div class="section-title">触发原因</div>
            <div class="detail-bullets">
              <div v-for="(reason, idx) in selectedAnomaly.trigger_reasons" :key="idx">• {{ reason }}</div>
            </div>
          </div>

          <div class="detail-section" v-if="selectedAnomaly.evidence_summary">
            <div class="section-title">证据摘要</div>
            <div class="detail-paragraph">{{ selectedAnomaly.evidence_summary }}</div>
          </div>

          <div class="detail-section" v-if="selectedAnomaly.advice">
            <div class="section-title">交易建议</div>
            <div class="advice-grid">
              <div class="advice-card">
                <div class="advice-label">方向</div>
                <div class="advice-value">{{ getTradeBiasLabel(selectedAnomaly.advice.bias) }}</div>
              </div>
              <div class="advice-card">
                <div class="advice-label">置信度</div>
                <div class="advice-value">{{ safeFixed(selectedAnomaly.advice.confidence, 0) }}</div>
              </div>
              <div class="advice-card">
                <div class="advice-label">建议入场</div>
                <div class="advice-value">{{ selectedAnomaly.advice.suggested_entry ? `$${formatPrice(selectedAnomaly.advice.suggested_entry)}` : '--' }}</div>
              </div>
              <div class="advice-card">
                <div class="advice-label">建议止损</div>
                <div class="advice-value">{{ selectedAnomaly.advice.suggested_stop_loss ? `$${formatPrice(selectedAnomaly.advice.suggested_stop_loss)}` : '--' }}</div>
              </div>
              <div class="advice-card">
                <div class="advice-label">建议止盈</div>
                <div class="advice-value">{{ selectedAnomaly.advice.suggested_take_profit ? `$${formatPrice(selectedAnomaly.advice.suggested_take_profit)}` : '--' }}</div>
              </div>
            </div>
            <div class="detail-paragraph">{{ selectedAnomaly.advice.recommendation }}</div>
            <div class="risk-note" v-if="selectedAnomaly.advice.risk_note">
              风险提示：{{ selectedAnomaly.advice.risk_note }}
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">新闻来源</div>
            <div v-if="selectedAnomaly.news?.length" class="news-list">
              <a
                v-for="item in selectedAnomaly.news"
                :key="item.id || `${item.title}-${item.published_at}`"
                class="news-item"
                :href="item.url || '#'"
                target="_blank"
                rel="noopener noreferrer"
              >
                <div class="news-title">{{ item.title }}</div>
                <div class="news-meta">
                  <el-tag size="small" type="info">{{ item.source }}</el-tag>
                  <span>{{ item.source_domain || '来源未标注' }}</span>
                  <span>{{ formatDateTime(item.published_at) }}</span>
                </div>
                <div v-if="item.summary" class="news-summary">{{ item.summary }}</div>
              </a>
            </div>
            <el-empty v-else description="暂未获取到相关新闻" />
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useStore } from 'vuex'
import { Loading, Refresh } from '@element-plus/icons-vue'
import echarts from '@/lib/echarts'
import { marketInsight } from '@/api'
import { ElMessage } from 'element-plus'
import KlineChart from '@/components/KlineChart.vue'
import {
  formatDateTime as formatDisplayDateTime,
  formatShortDate as formatDisplayShortDate
} from '@/utils/datetime'

const store = useStore()
const displayTimezone = computed(() => store.getters.displayTimezone)

const pageTitle = ref('市场洞察')
const loading = ref(false)

// 数据
const overview = ref({})
const altcoinStarters = ref([])
const topVolume = ref([])
const watchlist = ref([])
const fundingRateHigh = ref([])
const fundingRateLow = ref([])
const sentiment = ref([])
const fearGreedIndex = ref(null)
const fearGreedHistory = ref([])
const rainbowBands = ref([])
const signals = ref([])
const aiAnalysis = ref('')
const currentChartSymbol = ref('BTCUSDT')
const activeAnomalies = ref([])
const lastAnomalyScanAt = ref('')
const anomalyScanLoading = ref(false)
const anomalyDrawerVisible = ref(false)
const anomalyDetailLoading = ref(false)
const selectedAnomaly = ref(null)

// Scanner State
const scanning = ref(false)
const scanResults = ref([])
const chartRef = ref(null) // Reference to KlineChart component
const fearGreedChartRef = ref(null)
const rainbowChartRef = ref(null)

let fearGreedChart = null
let rainbowChart = null

const patternTolerance = ref(0.35)
const patternToleranceOptions = [
  { value: 0.25, label: '宽松' },
  { value: 0.35, label: '标准' },
  { value: 0.45, label: '严格' },
  { value: 0.55, label: '极严格' }
]
const patternFilterOptions = [
  { value: 'hammer', label: '锤子线' },
  { value: 'inverted_hammer', label: '倒锤子' },
  { value: 'shooting_star', label: '流星线' },
  { value: 'bullish_engulfing', label: '看涨吞没' },
  { value: 'bearish_engulfing', label: '看跌吞没' },
  { value: 'doji', label: '十字星' }
]
const selectedPatternTypes = ref(patternFilterOptions.map(option => option.value))

const filteredScanResults = computed(() => {
  if (!selectedPatternTypes.value.length) {
    return []
  }
  return scanResults.value.filter(item => selectedPatternTypes.value.includes(getPatternType(item?.pattern?.name)))
})

const fearGreedDelta = computed(() => {
  const current = Number(fearGreedHistory.value?.[0]?.value)
  const previous = Number(fearGreedHistory.value?.[1]?.value)
  if (Number.isNaN(current) || Number.isNaN(previous)) return null
  return current - previous
})

const fearGreed30DaySeries = computed(() => {
  return [...(fearGreedHistory.value || [])]
    .slice(0, 30)
    .reverse()
    .map(item => ({
      label: formatShortDate(item.timestamp),
      value: Number(item.value)
    }))
    .filter(item => !Number.isNaN(item.value))
})

const fearGreed30DayAverageLabel = computed(() => {
  if (!fearGreed30DaySeries.value.length) {
    return '--'
  }
  const total = fearGreed30DaySeries.value.reduce((sum, item) => sum + item.value, 0)
  return (total / fearGreed30DaySeries.value.length).toFixed(1)
})

const fearGreedDeltaLabel = computed(() => {
  if (fearGreedDelta.value == null) {
    return '--'
  }
  if (fearGreedDelta.value === 0) {
    return '0.0'
  }
  return `${fearGreedDelta.value > 0 ? '+' : ''}${fearGreedDelta.value.toFixed(1)}`
})

const fearGreedDeltaClass = computed(() => {
  if (fearGreedDelta.value == null || fearGreedDelta.value === 0) {
    return ''
  }
  return fearGreedDelta.value > 0 ? 'is-up' : 'is-down'
})

const btcCurrentPrice = computed(() => {
  const btcInWatch = watchlist.value.find(i => i.symbol === 'BTCUSDT')
  if (btcInWatch) return btcInWatch.last_price
  return 0
})

const rainbowChartSeries = computed(() => {
  return [...(rainbowBands.value || [])]
    .reverse()
    .map(item => ({
      name: item.name,
      price: Number(item.price),
      color: item.color
    }))
    .filter(item => item.price > 0)
})

const rainbowCurrentBand = computed(() => {
  if (!btcCurrentPrice.value || rainbowBands.value.length === 0) return null

  return rainbowBands.value.reduce((closest, band) => {
    if (!closest) return band
    const currentDistance = Math.abs(Math.log(btcCurrentPrice.value / band.price))
    const closestDistance = Math.abs(Math.log(btcCurrentPrice.value / closest.price))
    return currentDistance < closestDistance ? band : closest
  }, null)
})

const rainbowCurrentBandLabel = computed(() => {
  if (!btcCurrentPrice.value || !rainbowCurrentBand.value) {
    return '等待 BTC 价格和区间数据'
  }
  return `接近 ${rainbowCurrentBand.value.name}`
})

const rainbowReferencePriceLabel = computed(() => {
  if (!rainbowCurrentBand.value?.price) {
    return '--'
  }
  return `$${formatNumber(rainbowCurrentBand.value.price)}`
})

const rainbowDistanceLabel = computed(() => {
  if (!btcCurrentPrice.value || !rainbowCurrentBand.value?.price) {
    return '--'
  }
  const diff = ((btcCurrentPrice.value - rainbowCurrentBand.value.price) / rainbowCurrentBand.value.price) * 100
  if (Math.abs(diff) < 0.1) {
    return '接近参考线'
  }
  return `${diff > 0 ? '+' : '-'}${Math.abs(diff).toFixed(2)}%`
})

// 自选管理
const showWatchlistDialog = ref(false)
const newWatchSymbol = ref('')
const userWatchlist = ref([])

// 从 localStorage 加载自选
const loadUserWatchlist = () => {
  const saved = localStorage.getItem('user_watchlist')
  if (saved) {
    try {
      userWatchlist.value = JSON.parse(saved)
    } catch (e) {
      userWatchlist.value = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ORDIUSDT']
    }
  } else {
    userWatchlist.value = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ORDIUSDT']
  }
}

// 保存自选到 localStorage
const saveUserWatchlist = () => {
  localStorage.setItem('user_watchlist', JSON.stringify(userWatchlist.value))
}

// 自动刷新定时器
let refreshTimer = null

function initMacroCharts() {
  if (fearGreedChartRef.value && !fearGreedChart) {
    fearGreedChart = echarts.init(fearGreedChartRef.value)
  }
  if (rainbowChartRef.value && !rainbowChart) {
    rainbowChart = echarts.init(rainbowChartRef.value)
  }
  updateFearGreedChart()
  updateRainbowChart()
}

function disposeMacroCharts() {
  if (fearGreedChart) {
    fearGreedChart.dispose()
    fearGreedChart = null
  }
  if (rainbowChart) {
    rainbowChart.dispose()
    rainbowChart = null
  }
}

function resizeMacroCharts() {
  fearGreedChart?.resize()
  rainbowChart?.resize()
}

function updateFearGreedChart() {
  if (!fearGreedChart) {
    return
  }

  const series = fearGreed30DaySeries.value
  fearGreedChart.setOption({
    animation: false,
    grid: {
      left: 36,
      right: 16,
      top: 20,
      bottom: 28
    },
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const point = params?.[0]
        if (!point) {
          return ''
        }
        return `${point.axisValue}<br/>情绪值: ${point.data}`
      }
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: series.map(item => item.label),
      axisLabel: {
        color: '#909399',
        fontSize: 11
      },
      axisLine: {
        lineStyle: {
          color: '#dcdfe6'
        }
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: {
        lineStyle: {
          color: '#f0f2f5'
        }
      },
      axisLabel: {
        color: '#909399',
        fontSize: 11
      }
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 3,
          color: getFngColor(Number(fearGreedIndex.value?.value) || 50)
        },
        areaStyle: {
          color: 'rgba(230, 162, 60, 0.10)'
        },
        data: series.map(item => item.value),
        markPoint: series.length
          ? {
              symbol: 'circle',
              symbolSize: 10,
              data: [
                {
                  coord: [series[series.length - 1].label, series[series.length - 1].value],
                  itemStyle: {
                    color: getFngColor(Number(fearGreedIndex.value?.value) || 50)
                  }
                }
              ]
            }
          : undefined
      }
    ]
  })
}

function updateRainbowChart() {
  if (!rainbowChart) {
    return
  }

  const series = rainbowChartSeries.value
  rainbowChart.setOption({
    animation: false,
    grid: {
      left: 48,
      right: 16,
      top: 20,
      bottom: 44
    },
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const point = params?.[0]
        if (!point) {
          return ''
        }
        return `${point.axisValue}<br/>参考价: $${formatNumber(point.data)}`
      }
    },
    xAxis: {
      type: 'category',
      data: series.map(item => item.name),
      axisLabel: {
        color: '#909399',
        fontSize: 10,
        interval: 0,
        rotate: 24
      },
      axisLine: {
        lineStyle: {
          color: '#dcdfe6'
        }
      }
    },
    yAxis: {
      type: 'log',
      logBase: 10,
      splitLine: {
        lineStyle: {
          color: '#f0f2f5'
        }
      },
      axisLabel: {
        color: '#909399',
        fontSize: 11,
        formatter: value => `$${formatNumber(value)}`
      }
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: {
          width: 3,
          color: '#ff8f00'
        },
        itemStyle: {
          color: params => series[params.dataIndex]?.color || '#ff8f00'
        },
        data: series.map(item => item.price),
        markLine: btcCurrentPrice.value
          ? {
              symbol: 'none',
              label: {
                show: true,
                position: 'insideEndTop',
                formatter: `BTC $${formatNumber(btcCurrentPrice.value)}`,
                color: '#303133'
              },
              lineStyle: {
                type: 'dashed',
                width: 2,
                color: '#303133'
              },
              data: [
                {
                  yAxis: btcCurrentPrice.value
                }
              ]
            }
          : undefined
      }
    ]
  })
}

onMounted(() => {
  loadUserWatchlist()
  initMacroCharts()
  loadData()
  window.addEventListener('resize', resizeMacroCharts)
  // 每30秒自动刷新
  refreshTimer = setInterval(() => {
    loadData(true)
  }, 30000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
  window.removeEventListener('resize', resizeMacroCharts)
  disposeMacroCharts()
})

watch(fearGreed30DaySeries, () => {
  updateFearGreedChart()
}, { deep: true })

watch([rainbowChartSeries, btcCurrentPrice], () => {
  updateRainbowChart()
}, { deep: true })

const handlePatternClick = (res) => {
  currentChartSymbol.value = res.symbol
  // Focus logic: wait for chart to update symbol and load data, then focus
  // We can pass the pattern to the chart component to focus on
  // But chart reloads on symbol change.
  // Actually, we can use a ref method on the chart component.
  // Wait for next tick or event?
  // Let's rely on watch within KlineChart? 
  // Better: KlineChart exposes a focus method. But symbol change triggers reload.
  // We can pass "focusTarget" prop? or just call method after a delay.
  setTimeout(() => {
    if (chartRef.value) {
      chartRef.value.focusOnPattern(res.pattern)
    }
  }, 1000) // Delay to allow fetch. Refine later with events if needed.
}

function getPatternType(name = '') {
  if (name.startsWith('Hammer')) return 'hammer'
  if (name.startsWith('Inv Hammer')) return 'inverted_hammer'
  if (name.startsWith('Shooting Star')) return 'shooting_star'
  if (name.startsWith('Bullish Engulfing')) return 'bullish_engulfing'
  if (name.startsWith('Bearish Engulfing')) return 'bearish_engulfing'
  if (name.startsWith('Doji')) return 'doji'
  return 'other'
}

function selectAllPatternTypes() {
  selectedPatternTypes.value = patternFilterOptions.map(option => option.value)
}

function clearPatternTypes() {
  selectedPatternTypes.value = []
}

async function scanPatterns() {
  scanning.value = true
  scanResults.value = []
  try {
    const res = await marketInsight.scanPatterns({
      interval: '1h',
      tolerance: patternTolerance.value
    })
    scanResults.value = res || []
  } catch (err) {
    console.error(err)
  } finally {
    scanning.value = false
  }
}

function handlePatternToleranceChange() {
  scanPatterns()
}

async function loadData(silent = false) {
  if (!silent) {
    loading.value = true
  }
  
  try {
    const watchlistParam = userWatchlist.value.join(',')
    const response = await marketInsight.getDashboard({ watchlist: watchlistParam })
    
    overview.value = response.overview
    altcoinStarters.value = response.altcoin_starters || []
    topVolume.value = response.top_volume
    watchlist.value = response.watchlist
    fundingRateHigh.value = response.funding_rate_high || []
    fundingRateLow.value = response.funding_rate_low || []
    sentiment.value = response.sentiment
    fearGreedIndex.value = response.fear_greed_index
    fearGreedHistory.value = response.fear_greed_history
    rainbowBands.value = response.rainbow_bands
    signals.value = response.signals
    aiAnalysis.value = response.ai_analysis
    activeAnomalies.value = response.active_anomalies || []
    lastAnomalyScanAt.value = response.last_anomaly_scan_at || ''
    
    if (!silent) {
      ElMessage.success('数据加载成功')
    }
  } catch (error) {
    console.error('Failed to load market insight data:', error)
    if (!silent) {
      ElMessage.error('数据加载失败')
    }
  } finally {
    loading.value = false
  }
}

function refreshData() {
  loadData()
}

async function triggerAnomalyScan() {
  anomalyScanLoading.value = true
  try {
    const response = await marketInsight.scanAnomalies(8)
    activeAnomalies.value = response || []
    lastAnomalyScanAt.value = new Date().toISOString()
    ElMessage.success('异常扫描已完成')
  } catch (error) {
    console.error('Failed to scan anomalies:', error)
    ElMessage.error('异常扫描失败')
  } finally {
    anomalyScanLoading.value = false
  }
}

async function openAnomalyDetail(row) {
  if (!row?.id) return
  anomalyDrawerVisible.value = true
  anomalyDetailLoading.value = true
  try {
    selectedAnomaly.value = await marketInsight.getAnomalyDetail(row.id)
  } catch (error) {
    console.error('Failed to load anomaly detail:', error)
    ElMessage.error('异常详情加载失败')
  } finally {
    anomalyDetailLoading.value = false
  }
}

function selectSymbol(row) {
  currentChartSymbol.value = row.symbol
  ElMessage.info(`切换行情至: ${formatSymbol(row.symbol)}`)
  // 滚动到 K 线图位置
  const el = document.querySelector('.kline-card')
  if (el) {
    el.scrollIntoView({ behavior: 'smooth' })
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  // 极简 Markdown 转换
  return text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*)\*/gim, '<em>$1</em>')
    .replace(/\n/gim, '<br>')
}

function formatSymbol(symbol) {
  return symbol.replace('USDT', '')
}

function formatPrice(price) {
  if (price == null || Number.isNaN(Number(price))) return '--'
  if (price < 1) return price.toFixed(4)
  if (price < 10) return price.toFixed(3)
  return price.toFixed(2)
}

function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B'
  if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M'
  if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K'
  return num.toFixed(2)
}

function formatDateTime(rawValue) {
  return formatDisplayDateTime(rawValue, displayTimezone.value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatShortDate(rawValue) {
  return formatDisplayShortDate(rawValue, displayTimezone.value)
}

function safeFixed(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '--'
  return Number(value).toFixed(digits)
}

function getAnomalyLevelLabel(level) {
  const labels = {
    critical: '极高',
    high: '高',
    medium: '中',
    low: '低'
  }
  return labels[level] || level || '未知'
}

function getAnomalyLevelTagType(level) {
  const types = {
    critical: 'danger',
    high: 'danger',
    medium: 'warning',
    low: 'info'
  }
  return types[level] || 'info'
}

function getCredibilityTagType(label) {
  const types = {
    可信: 'success',
    待核实: 'warning',
    高风险谣言: 'danger'
  }
  return types[label] || 'info'
}

function getTradeBiasLabel(bias) {
  const labels = {
    long: '偏多',
    short: '偏空',
    neutral: '观望'
  }
  return labels[bias] || bias || '观望'
}

function getTradeBiasTagType(bias) {
  const types = {
    long: 'success',
    short: 'danger',
    neutral: 'info'
  }
  return types[bias] || 'info'
}

function getSentimentLabel(score) {
  const labels = {
    extreme_fear: '极度恐慌',
    fear: '恐慌',
    neutral: '中性',
    greed: '贪婪',
    extreme_greed: '极度贪婪'
  }
  return labels[score] || '未知'
}

function getSentimentTagType(score) {
  const types = {
    extreme_fear: 'danger',
    fear: 'warning',
    neutral: 'info',
    greed: 'success',
    extreme_greed: 'success'
  }
  return types[score] || 'info'
}

function getFundingRateClass(rate) {
  if (!rate) return ''
  return rate > 0 ? 'positive' : 'negative'
}

function getLongShortRatioClass(ratio) {
  if (!ratio) return ''
  return ratio > 1 ? 'positive' : 'negative'
}

function getSignalLabel(type) {
  const labels = {
    long: '做多',
    short: '做空',
    neutral: '观望'
  }
  return labels[type] || type
}

function getSignalTagType(type) {
  const types = {
    long: 'success',
    short: 'danger',
    neutral: 'info'
  }
  return types[type] || 'info'
}

function getSignalColor(type) {
  const colors = {
    long: '#67C23A',
    short: '#F56C6C',
    neutral: '#909399'
  }
  return colors[type] || '#909399'
}

function getRRRatioLabel(signal) {
  if (signal.rr_ratio != null && signal.rr_ratio > 0) {
    return `1 : ${signal.rr_ratio.toFixed(1)}`
  }
  return '1 : 2.5'
}

function getFngTagType(label) {
  if (!label) return 'info'
  const l = label.toLowerCase()
  if (l.includes('extreme greed')) return 'success'
  if (l.includes('greed')) return 'warning'
  if (l.includes('fear')) return 'danger'
  return 'info'
}

function getFngColor(val) {
  if (!val) return '#909399'
  if (val >= 75) return '#67C23A' // Extreme Greed
  if (val >= 55) return '#E6A23C' // Greed
  if (val >= 45) return '#909399' // Neutral
  if (val >= 25) return '#F56C6C' // Fear
  return '#FF0000' // Extreme Fear
}

function addToWatchlist() {
  let symbol = newWatchSymbol.value.trim().toUpperCase()
  if (!symbol) {
    ElMessage.warning('请输入币种符号')
    return
  }
  
  // 智能补充 USDT
  if (!symbol.endsWith('USDT') && !symbol.endsWith('BUSD')) {
    symbol = symbol + 'USDT'
  }
  
  if (userWatchlist.value.includes(symbol)) {
    ElMessage.warning('该币种已在自选列表中')
    return
  }
  
  userWatchlist.value.push(symbol)
  saveUserWatchlist() // 保存到本地存储
  newWatchSymbol.value = ''
  ElMessage.success('添加成功')
  loadData(true)
}

function removeFromWatchlist(symbol) {
  const index = userWatchlist.value.indexOf(symbol)
  if (index > -1) {
    userWatchlist.value.splice(index, 1)
    saveUserWatchlist() // 保存到本地存储
    ElMessage.success('移除成功')
    loadData(true)
  }
}
</script>

<style scoped>
.market-insight {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.overview-card {
  margin-bottom: 20px;
}

.kline-card {
  margin-bottom: 20px;
  padding: 0;
}

.scanner-card {
  margin-bottom: 20px;
}

.anomaly-card {
  margin-bottom: 20px;
}

.anomaly-header .header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.source-summary {
  color: #606266;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.control-label {
  font-size: 14px;
  color: #606266;
  margin-right: 10px;
}

.pattern-strictness-control {
  display: flex;
  align-items: center;
}

.strictness-select {
  width: 120px;
}

.pattern-filter-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.filter-panel-title {
  font-size: 13px;
  color: #606266;
}

.pattern-filter-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}

.pattern-filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.scanning-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 30px;
  color: #909399;
}

.empty-scan {
  text-align: center;
  padding: 30px;
  color: #909399;
}

.scan-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 15px;
  margin-bottom: 15px;
  cursor: pointer;
  transition: all 0.3s;
}

.scan-item:hover {
  box-shadow: 0 2px 12px 0 rgba(0,0,0,.1);
}

.scan-item.bullish {
  border-left: 4px solid #67C23A;
}

.scan-item.bearish {
  border-left: 4px solid #F56C6C;
}

.scan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.scan-symbol {
  font-weight: bold;
  font-size: 16px;
}

.pattern-name {
  font-size: 14px;
  color: #303133;
  margin-bottom: 5px;
}

.pattern-info {
  font-size: 12px;
  color: #909399;
}

.ai-analysis-card {
  margin-bottom: 20px;
  background-color: #f0f9eb;
  border-left: 5px solid #67c23a;
}

.ai-content {
  line-height: 1.6;
  color: #606266;
  font-size: 15px;
}

.ai-content h3 {
  margin-top: 0;
  color: #303133;
}

.stat-item {
  text-align: center;
  padding: 10px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

.signals-card {
  margin-bottom: 20px;
}

.signal-item {
  padding: 15px;
  border-radius: 8px;
  background: #f5f7fa;
  height: 100%;
}

.signal-item.signal-long {
  border-left: 4px solid #67C23A;
}

.signal-item.signal-short {
  border-left: 4px solid #F56C6C;
}

.signal-item.signal-neutral {
  border-left: 4px solid #909399;
}

.signal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.signal-symbol {
  font-size: 16px;
  font-weight: bold;
}

.signal-strength {
  margin: 10px 0;
  font-size: 12px;
  color: #606266;
}

.signal-reasons {
  margin: 10px 0;
  font-size: 13px;
  color: #606266;
}

.reason {
  margin: 5px 0;
}

.signal-prices {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #dcdfe6;
}

.price-item {
  display: flex;
  justify-content: space-between;
  margin: 5px 0;
  font-size: 13px;
}

.price-item .label {
  color: #909399;
}

.price-item .value.success {
  color: #67C23A;
  font-weight: bold;
}

.price-item .value.danger {
  color: #F56C6C;
  font-weight: bold;
}

.price-row {
  display: flex;
  gap: 10px;
}

.price-row .price-item {
  flex: 1;
}

.rr-ratio {
  margin-top: 8px;
  font-size: 11px;
  color: #909399;
  text-align: right;
}

.neutral-prices {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #dcdfe6;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.neutral-direction {
  font-size: 12px;
  color: #909399;
}

.neutral-direction.long-dir {
  color: #67C23A;
}

.neutral-direction.short-dir {
  color: #F56C6C;
}

.sentiment-card {
  margin-bottom: 20px;
}

.sentiment-item {
  padding: 15px;
  border-radius: 8px;
  background: #f5f7fa;
}

.sentiment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.sentiment-header .symbol {
  font-size: 16px;
  font-weight: bold;
}

.sentiment-data .data-row {
  display: flex;
  justify-content: space-between;
  margin: 8px 0;
  font-size: 14px;
}

.sentiment-data .label {
  color: #909399;
}

.positive {
  color: #67C23A;
  font-weight: bold;
}

.negative {
  color: #F56C6C;
  font-weight: bold;
}

.rankings {
  margin-bottom: 20px;
}

.sentiment-rankings {
  margin-bottom: 20px;
}

.sentiment-macro-card {
  height: 100%;
}

.macro-compact-card {
  border: 1px solid #ebeef5;
  border-radius: 14px;
  padding: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
}

.macro-summary-row {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
}

.macro-hero {
  min-width: 0;
  flex: 1;
}

.macro-hero-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.macro-hero-value {
  font-size: 34px;
  line-height: 1;
  font-weight: 700;
  color: #303133;
}

.macro-hero-subtitle {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}

.rainbow-price {
  font-size: 28px;
  color: #ff8f00;
}

.macro-meta-list {
  width: 160px;
  display: grid;
  gap: 10px;
}

.macro-meta-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: #f7f8fa;
  border: 1px solid #edf0f5;
}

.meta-label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.meta-value {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}

.meta-value.is-up {
  color: #67c23a;
}

.meta-value.is-down {
  color: #f56c6c;
}

.macro-chart {
  width: 100%;
  height: 220px;
}

.symbol-name {
  font-weight: bold;
  color: #303133;
}

.clickable-row {
  cursor: pointer;
  transition: background-color 0.2s;
}

.clickable-row:hover {
  background-color: #f5f7fa !important;
}

.price {
  color: #606266;
}

.volume {
  color: #606266;
  font-size: 13px;
}

.watchlist-items {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #dcdfe6;
}

.anomaly-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 12px;
}

.detail-symbol {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.detail-meta {
  color: #909399;
  margin-top: 6px;
}

.detail-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.anomaly-descriptions {
  margin-bottom: 20px;
}

.detail-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 10px;
  color: #303133;
}

.detail-bullets {
  display: grid;
  gap: 8px;
  color: #606266;
}

.detail-paragraph {
  line-height: 1.7;
  color: #606266;
}

.advice-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.advice-card {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fafafa;
}

.advice-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.advice-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.risk-note {
  margin-top: 12px;
  color: #e6a23c;
}

.news-list {
  display: grid;
  gap: 12px;
}

.news-item {
  display: block;
  padding: 14px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
  text-decoration: none;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.news-item:hover {
  border-color: #dcdfe6;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.06);
}

.news-title {
  color: #303133;
  font-weight: 600;
  margin-bottom: 8px;
}

.news-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  color: #909399;
  font-size: 12px;
  margin-bottom: 6px;
}

.news-summary {
  color: #606266;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .header-controls {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .pattern-strictness-control {
    width: 100%;
    justify-content: flex-end;
  }

  .strictness-select {
    width: 110px;
  }

  .pattern-filter-group {
    grid-template-columns: 1fr;
  }

  .macro-summary-row {
    flex-direction: column;
  }

  .macro-meta-list {
    width: 100%;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .macro-chart {
    height: 200px;
  }

  .anomaly-detail-header {
    flex-direction: column;
  }

  .advice-grid {
    grid-template-columns: 1fr;
  }
}
</style>
