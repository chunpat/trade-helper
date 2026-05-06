<template>
  <div class="landing">
    <!-- Navbar -->
    <nav class="nav" :class="{ 'nav-scrolled': scrolled }">
      <div class="nav-inner">
        <div class="nav-brand">
          <span class="nav-logo">⛓️</span>
          <span class="nav-title">TradeHelper</span>
        </div>
        <div class="nav-links">
          <a href="#features" class="nav-link">核心功能</a>
          <a href="#how-it-works" class="nav-link">系统架构</a>
          <a href="#tech" class="nav-link">技术栈</a>
          <router-link to="/pricing" class="nav-link">价格方案</router-link>
        </div>
        <div class="nav-actions">
          <el-button v-if="isLoggedIn" type="primary" round @click="$router.push('/dashboard')">进入控制台</el-button>
          <template v-else>
            <el-button text @click="$router.push('/login')">登录</el-button>
            <el-button type="primary" round @click="$router.push('/login')">免费试用</el-button>
          </template>
        </div>
      </div>
    </nav>

    <!-- Hero -->
    <section class="hero">
      <div class="hero-bg"></div>
      <div class="hero-content">
        <div class="hero-badge">🔒 专业的数字货币合约风控平台</div>
        <h1 class="hero-title">
          让每一笔合约交易<br />
          <span class="hero-highlight">都在风险可控范围内</span>
        </h1>
        <p class="hero-subtitle">
          实时监控多交易所持仓，智能识别市场异动与重大利好叙事，<br />
          AI 辅助决策，为您的数字资产提供全方位的风控保障。
        </p>
        <div class="hero-actions">
          <el-button v-if="isLoggedIn" type="primary" size="large" round @click="$router.push('/dashboard')">
            进入控制台 <span style="margin-left:4px">→</span>
          </el-button>
          <el-button v-else type="primary" size="large" round @click="$router.push('/login')">
            立即开始 <span style="margin-left:4px">→</span>
          </el-button>
          <el-button size="large" round @click="scrollTo('features')">了解更多</el-button>
        </div>
        <div class="hero-stats">
          <div class="hero-stat">
            <span class="hero-stat-num">Binance + OKX</span>
            <span class="hero-stat-label">多交易所支持</span>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-num">7×24</span>
            <span class="hero-stat-label">实时监控</span>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-num">AI</span>
            <span class="hero-stat-label">智能分析引擎</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Features -->
    <section id="features" class="features">
      <div class="section-header">
        <span class="section-tag">核心功能</span>
        <h2 class="section-title">六大模块，全面覆盖风控场景</h2>
        <p class="section-desc">从实时监控到智能预警，从市场洞察到交易复盘，一站式解决合约交易风控难题</p>
      </div>
      <div class="features-grid">
        <div class="feature-card" v-for="f in features" :key="f.title">
          <div class="feature-icon">{{ f.icon }}</div>
          <h3 class="feature-title">{{ f.title }}</h3>
          <p class="feature-desc">{{ f.desc }}</p>
          <ul class="feature-points">
            <li v-for="p in f.points" :key="p">{{ p }}</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- How It Works -->
    <section id="how-it-works" class="how-it-works">
      <div class="section-header">
        <span class="section-tag">系统架构</span>
        <h2 class="section-title">数据驱动的风控闭环</h2>
        <p class="section-desc">从数据采集到智能分析，从预警触发到决策辅助，形成完整的风控闭环</p>
      </div>
      <div class="pipeline">
        <div class="pipeline-step" v-for="(step, i) in pipeline" :key="step.title">
          <div class="pipeline-num">{{ i + 1 }}</div>
          <h3>{{ step.title }}</h3>
          <p>{{ step.desc }}</p>
          <div class="pipeline-arrow" v-if="i < pipeline.length - 1">→</div>
        </div>
      </div>
    </section>

    <!-- Narrative Detection Highlight -->
    <section class="highlight">
      <div class="highlight-card">
        <div class="highlight-text">
          <span class="section-tag">🆕 重大利好叙事检测</span>
          <h2>不止监控价格，更理解<span class="hero-highlight">叙事</span></h2>
          <p>
            当市场出现异动时，AI 自动聚合多源新闻，识别驱动因素：
            产品上线、交易所上币、重大合作、监管利好……
            帮你快速判断是"真利好"还是"纯炒作"。
          </p>
          <div class="highlight-tags">
            <span class="narrative-tag">🚀 产品上线</span>
            <span class="narrative-tag">📈 交易所上币</span>
            <span class="narrative-tag">🤝 重大合作</span>
            <span class="narrative-tag">📰 监管利好</span>
            <span class="narrative-tag">⚠️ 内幕/传闻</span>
            <span class="narrative-tag">📊 纯市场炒作</span>
          </div>
        </div>
        <div class="highlight-visual">
          <div class="narrative-card">
            <div class="narrative-card-header">
              <span class="narrative-badge success">重大利好</span>
              <span class="narrative-score">置信度 88%</span>
            </div>
            <div class="narrative-card-body">
              <h4>🚀 产品/功能上线</h4>
              <p>检测到 LAB 代币于 5月3日 上线移动端 App，币安合约交易量激增 1,226%，24H 涨幅 161%，交易额进入全市场前10</p>
            </div>
            <div class="narrative-card-footer">
              <span>📎 5 个来源交叉验证</span>
              <span class="narrative-action">建议关注回调做多 →</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Tech Stack -->
    <section id="tech" class="tech">
      <div class="section-header">
        <span class="section-tag">技术栈</span>
        <h2 class="section-title">现代技术架构</h2>
        <p class="section-desc">高性能、可扩展的技术选型，保障系统稳定可靠运行</p>
      </div>
      <div class="tech-grid">
        <div class="tech-layer" v-for="layer in techStack" :key="layer.name">
          <div class="tech-layer-name">{{ layer.name }}</div>
          <div class="tech-items">
            <span class="tech-item" v-for="item in layer.items" :key="item">{{ item }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="cta">
      <h2>准备好提升你的风控能力了吗？</h2>
      <p>立即接入 TradeHelper，让 AI 为你的每一笔交易保驾护航</p>
      <div class="cta-actions">
        <el-button v-if="isLoggedIn" type="primary" size="large" round @click="$router.push('/dashboard')">进入控制台</el-button>
        <el-button v-else type="primary" size="large" round @click="$router.push('/login')">免费开始使用</el-button>
      </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <span class="nav-logo">⛓️</span>
          <span>TradeHelper</span>
          <p>数字货币合约交易智能风控系统</p>
        </div>
        <div class="footer-links">
          <div class="footer-col">
            <h4>产品</h4>
            <a href="#features">核心功能</a>
            <a href="#how-it-works">系统架构</a>
            <router-link to="/pricing">价格方案</router-link>
          </div>
          <div class="footer-col">
            <h4>功能</h4>
            <a href="/dashboard">风控仪表盘</a>
            <a href="/market-insight">市场洞察</a>
            <a href="/positions">持仓监控</a>
          </div>
          <div class="footer-col">
            <h4>关于</h4>
            <a href="#">隐私政策</a>
            <a href="#">服务条款</a>
            <a href="#">联系我们</a>
          </div>
        </div>
      </div>
      <div class="footer-bottom">
        <p>&copy; {{ currentYear }} TradeHelper. All rights reserved.</p>
      </div>
    </footer>
  </div>
</template>

<script>
export default {
  name: 'Landing',
  data() {
    return {
      scrolled: false,
      features: [
        {
          icon: '📊',
          title: '风控仪表盘',
          desc: '一站式风险总览，核心指标一目了然',
          points: ['持仓价值总览', '收益率曲线图', '风险分布饼图', '实时预警列表']
        },
        {
          icon: '🔍',
          title: '市场洞察',
          desc: '多维度市场数据，辅助交易决策',
          points: ['AI 市场分析', 'K线形态识别', '恐惧贪婪指数', '资金费率排名']
        },
        {
          icon: '📈',
          title: '持仓监控',
          desc: '实时同步多交易所持仓数据',
          points: ['Binance/OKX 支持', '未实现盈亏计算', 'WebSocket 实时推送', '历史交易查询']
        },
        {
          icon: '🤖',
          title: '异动检测',
          desc: 'AI 驱动的市场异动智能识别',
          points: ['量价异动扫描', '多因子评分模型', '新闻交叉验证', '叙事类型分类']
        },
        {
          icon: '📝',
          title: '交易复盘',
          desc: '完整的交易记录与绩效分析',
          points: ['胜率/盈亏比统计', '持仓周期分析', '每日复盘笔记', '90天历史回填']
        },
        {
          icon: '⚠️',
          title: '风险预警',
          desc: '多层次风险规则，及时告警',
          points: ['自定义风控阈值', '杠杆/仓位限制', '频率/偏离监控', '邮件实时告警']
        }
      ],
      pipeline: [
        { title: '数据采集', desc: '多交易所 API 实时同步：行情、持仓、订单、成交记录' },
        { title: '风险扫描', desc: 'Top100 代币异动扫描，多因子评分，异常事件自动分级' },
        { title: '新闻聚合', desc: 'RSS/API 多源新闻聚合，Brave/CryptoPanic 搜索，符号智能提取' },
        { title: 'AI 分析', desc: 'LLM 可信度评估，叙事类型识别，交易建议生成' },
        { title: '预警推送', desc: 'WebSocket 实时推送 + 邮件告警，前端即时展示' }
      ],
      techStack: [
        { name: '后端', items: ['Python 3.11', 'FastAPI', 'SQLAlchemy', 'Redis', 'MySQL 8.0'] },
        { name: '前端', items: ['Vue 3', 'Vuex 4', 'Element Plus', 'ECharts 5', 'Vite 4'] },
        { name: 'AI 引擎', items: ['OpenAI API', 'GPT-4o', '多源新闻聚合', '叙事分类'] },
        { name: '基础设施', items: ['Docker Compose', 'Nginx', 'WebSocket', 'JWT 双Token'] }
      ]
    }
  },
  computed: {
    isLoggedIn() {
      return !!this.$store.state.token
    },
    currentYear() {
      return new Date().getFullYear()
    }
  },
  mounted() {
    window.addEventListener('scroll', this.onScroll)
  },
  beforeUnmount() {
    window.removeEventListener('scroll', this.onScroll)
  },
  methods: {
    onScroll() {
      this.scrolled = window.scrollY > 60
    },
    scrollTo(id) {
      const el = document.getElementById(id)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
  }
}
</script>

<style lang="scss" scoped>
// === Variables ===
$bg-primary: #0a0e1a;
$bg-secondary: #111827;
$bg-card: #1a1f2e;
$text-primary: #f1f5f9;
$text-secondary: #94a3b8;
$accent: #3b82f6;
$accent-light: #60a5fa;
$accent-gradient: linear-gradient(135deg, #3b82f6, #8b5cf6);
$border: rgba(255, 255, 255, 0.08);
$radius: 12px;

// === Reset ===
.landing {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
  color: $text-primary;
  background: $bg-primary;
  overflow-x: hidden;
}

// === Navbar ===
.nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  padding: 16px 0;
  transition: all 0.3s ease;

  &.nav-scrolled {
    background: rgba(10, 14, 26, 0.92);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid $border;
    padding: 10px 0;
  }
}

.nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-logo {
  font-size: 28px;
}

.nav-title {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.3px;
}

.nav-links {
  display: flex;
  gap: 32px;

  @media (max-width: 768px) {
    display: none;
  }
}

.nav-link {
  color: $text-secondary;
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s;

  &:hover {
    color: $text-primary;
  }
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

// === Hero ===
.hero {
  position: relative;
  padding: 180px 24px 120px;
  text-align: center;
  overflow: hidden;
}

.hero-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 50% 0%, rgba(59, 130, 246, 0.15), transparent),
    radial-gradient(ellipse 60% 50% at 80% 80%, rgba(139, 92, 246, 0.1), transparent),
    radial-gradient(ellipse 50% 40% at 20% 70%, rgba(59, 130, 246, 0.08), transparent);
  pointer-events: none;
}

.hero-content {
  position: relative;
  max-width: 800px;
  margin: 0 auto;
}

.hero-badge {
  display: inline-block;
  padding: 6px 16px;
  border-radius: 20px;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: $accent-light;
  font-size: 13px;
  margin-bottom: 32px;
}

.hero-title {
  font-size: 48px;
  font-weight: 800;
  line-height: 1.25;
  letter-spacing: -1px;
  margin: 0 0 24px;

  @media (max-width: 768px) {
    font-size: 32px;
  }
}

.hero-highlight {
  background: $accent-gradient;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-subtitle {
  font-size: 17px;
  color: $text-secondary;
  line-height: 1.7;
  margin: 0 0 40px;
}

.hero-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
  margin-bottom: 64px;
}

.hero-stats {
  display: flex;
  justify-content: center;
  gap: 48px;
  padding-top: 48px;
  border-top: 1px solid $border;

  @media (max-width: 640px) {
    flex-direction: column;
    gap: 24px;
  }
}

.hero-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.hero-stat-num {
  font-size: 24px;
  font-weight: 700;
  color: $accent-light;
}

.hero-stat-label {
  font-size: 13px;
  color: $text-secondary;
}

// === Section shared ===
section {
  padding: 100px 24px;
}

.section-header {
  text-align: center;
  max-width: 600px;
  margin: 0 auto 64px;
}

.section-tag {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(59, 130, 246, 0.12);
  color: $accent-light;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 16px;
}

.section-title {
  font-size: 32px;
  font-weight: 700;
  margin: 0 0 16px;
  letter-spacing: -0.5px;
}

.section-desc {
  font-size: 15px;
  color: $text-secondary;
  line-height: 1.6;
  margin: 0;
}

// === Features ===
.features {
  background: $bg-secondary;
}

.features-grid {
  max-width: 1200px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;

  @media (max-width: 960px) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }
}

.feature-card {
  background: $bg-card;
  border: 1px solid $border;
  border-radius: $radius;
  padding: 32px;
  transition: all 0.3s ease;

  &:hover {
    border-color: rgba(59, 130, 246, 0.3);
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }
}

.feature-icon {
  font-size: 32px;
  margin-bottom: 16px;
}

.feature-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
}

.feature-desc {
  font-size: 14px;
  color: $text-secondary;
  margin: 0 0 16px;
  line-height: 1.5;
}

.feature-points {
  list-style: none;
  padding: 0;
  margin: 0;

  li {
    font-size: 13px;
    color: $text-secondary;
    padding: 3px 0;
    padding-left: 16px;
    position: relative;

    &::before {
      content: '•';
      position: absolute;
      left: 0;
      color: $accent;
    }
  }
}

// === How It Works ===
.pipeline {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
}

.pipeline-step {
  background: $bg-card;
  border: 1px solid $border;
  border-radius: $radius;
  padding: 32px 24px;
  text-align: center;
  flex: 1 1 180px;
  max-width: 220px;
  position: relative;

  h3 {
    font-size: 16px;
    margin: 12px 0 8px;
  }

  p {
    font-size: 13px;
    color: $text-secondary;
    line-height: 1.5;
    margin: 0;
  }
}

.pipeline-num {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: $accent-gradient;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
  margin: 0 auto;
}

.pipeline-arrow {
  position: absolute;
  right: -20px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 20px;
  color: $accent;

  @media (max-width: 1200px) {
    display: none;
  }
}

// === Highlight ===
.highlight {
  background: $bg-primary;
}

.highlight-card {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 64px;
  background: $bg-card;
  border: 1px solid $border;
  border-radius: 16px;
  padding: 56px;

  @media (max-width: 960px) {
    flex-direction: column;
    padding: 40px 24px;
    gap: 40px;
  }
}

.highlight-text {
  flex: 1;

  h2 {
    font-size: 28px;
    font-weight: 700;
    margin: 16px 0;
    line-height: 1.4;
  }

  p {
    font-size: 15px;
    color: $text-secondary;
    line-height: 1.7;
    margin: 0 0 24px;
  }
}

.highlight-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.narrative-tag {
  padding: 6px 14px;
  border-radius: 16px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.2);
  font-size: 13px;
  color: $text-primary;
}

.highlight-visual {
  flex: 1;
}

.narrative-card {
  background: linear-gradient(135deg, #1e293b, #1a1f2e);
  border: 1px solid rgba(139, 92, 246, 0.3);
  border-radius: 12px;
  padding: 24px;
}

.narrative-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.narrative-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;

  &.success {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
  }
}

.narrative-score {
  font-size: 13px;
  color: $accent-light;
}

.narrative-card-body {
  h4 {
    font-size: 16px;
    margin: 0 0 8px;
  }

  p {
    font-size: 13px;
    color: $text-secondary;
    line-height: 1.6;
    margin: 0;
  }
}

.narrative-card-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid $border;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: $text-secondary;
}

.narrative-action {
  color: $accent-light;
  font-weight: 500;
}

// === Tech ===
.tech {
  background: $bg-secondary;
}

.tech-grid {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.tech-layer {
  background: $bg-card;
  border: 1px solid $border;
  border-radius: $radius;
  padding: 24px 28px;
  display: flex;
  align-items: flex-start;
  gap: 24px;

  @media (max-width: 640px) {
    flex-direction: column;
    gap: 12px;
  }
}

.tech-layer-name {
  font-size: 15px;
  font-weight: 600;
  min-width: 100px;
  color: $accent-light;
  padding-top: 2px;
}

.tech-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tech-item {
  padding: 4px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  font-size: 13px;
  color: $text-secondary;
}

// === CTA ===
.cta {
  text-align: center;
  padding: 100px 24px;
  background:
    radial-gradient(ellipse 60% 60% at 50% 0%, rgba(59, 130, 246, 0.12), transparent),
    $bg-primary;

  h2 {
    font-size: 32px;
    font-weight: 700;
    margin: 0 0 16px;
  }

  p {
    font-size: 16px;
    color: $text-secondary;
    margin: 0 0 32px;
  }
}

.cta-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}

// === Footer ===
.footer {
  background: $bg-secondary;
  border-top: 1px solid $border;
  padding: 64px 24px 0;
}

.footer-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  gap: 48px;

  @media (max-width: 640px) {
    flex-direction: column;
    gap: 32px;
  }
}

.footer-brand {
  max-width: 240px;

  span {
    font-size: 18px;
    font-weight: 700;
  }

  p {
    font-size: 13px;
    color: $text-secondary;
    line-height: 1.6;
    margin-top: 8px;
  }
}

.footer-links {
  display: flex;
  gap: 64px;
}

.footer-col {
  h4 {
    font-size: 14px;
    font-weight: 600;
    margin: 0 0 12px;
  }

  a {
    display: block;
    color: $text-secondary;
    text-decoration: none;
    font-size: 13px;
    padding: 4px 0;
    transition: color 0.2s;

    &:hover {
      color: $text-primary;
    }
  }
}

.footer-bottom {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 0;
  border-top: 1px solid $border;
  margin-top: 48px;
  text-align: center;

  p {
    font-size: 13px;
    color: $text-secondary;
    margin: 0;
  }
}
</style>
