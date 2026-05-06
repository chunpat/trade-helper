<template>
  <div class="pricing">
    <!-- Navbar -->
    <nav class="nav" :class="{ 'nav-scrolled': scrolled }">
      <div class="nav-inner">
        <div class="nav-brand" @click="$router.push('/')" style="cursor:pointer">
          <span class="nav-logo">⛓️</span>
          <span class="nav-title">TradeHelper</span>
        </div>
        <div class="nav-links">
          <a href="/#features" class="nav-link">核心功能</a>
          <a href="/#how-it-works" class="nav-link">系统架构</a>
          <router-link to="/pricing" class="nav-link active">价格方案</router-link>
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
        <div class="hero-badge">💎 灵活的定价方案</div>
        <h1 class="hero-title">选择适合你的<span class="hero-highlight">风控方案</span></h1>
        <p class="hero-subtitle">
          从个人交易者到专业机构，我们都提供匹配的账号等级。<br />
          所有方案均支持 7 天免费试用，随时可升级或降级。
        </p>
      </div>
    </section>

    <!-- Pricing Cards -->
    <section class="plans">
      <div class="plans-grid">
        <!-- Free -->
        <div class="plan-card">
          <div class="plan-header">
            <h3 class="plan-name">免费版</h3>
            <p class="plan-desc">适合入门交易者，体验基础风控</p>
            <div class="plan-price">
              <span class="price-num">¥0</span>
              <span class="price-unit">/月</span>
            </div>
          </div>
          <div class="plan-body">
            <ul class="plan-features">
              <li><span class="check">✓</span> 1 个交易所账户绑定</li>
              <li><span class="check">✓</span> 实时持仓监控</li>
              <li><span class="check">✓</span> 基础风险预警（3条规则）</li>
              <li><span class="check">✓</span> 7天交易复盘记录</li>
              <li><span class="check">✓</span> 市场情绪概览</li>
              <li><span class="check">✓</span> 恐惧贪婪指数</li>
              <li class="disabled"><span>✗</span> AI 市场分析</li>
              <li class="disabled"><span>✗</span> 异动检测与叙事识别</li>
              <li class="disabled"><span>✗</span> 多交易所同时监控</li>
              <li class="disabled"><span>✗</span> 高级 K 线形态识别</li>
              <li class="disabled"><span>✗</span> 邮件/Webhook 告警</li>
              <li class="disabled"><span>✗</span> API 接口调用</li>
            </ul>
          </div>
          <div class="plan-footer">
            <el-button size="large" round plain @click="$router.push('/login')">免费开始</el-button>
          </div>
        </div>

        <!-- Pro - Highlighted -->
        <div class="plan-card featured">
          <div class="plan-ribbon">最受欢迎</div>
          <div class="plan-header">
            <h3 class="plan-name">专业版</h3>
            <p class="plan-desc">适合活跃交易者，全功能风控</p>
            <div class="plan-price">
              <span class="price-num">¥199</span>
              <span class="price-unit">/月</span>
            </div>
            <div class="plan-yearly">年付 ¥1,990/年 <span class="save-tag">省 ¥398</span></div>
          </div>
          <div class="plan-body">
            <ul class="plan-features">
              <li><span class="check">✓</span> <strong>5 个</strong>交易所账户绑定</li>
              <li><span class="check">✓</span> 实时持仓监控 + WebSocket 推送</li>
              <li><span class="check">✓</span> 全量风险预警（10+条规则）</li>
              <li><span class="check">✓</span> 90天交易复盘 + 每日笔记</li>
              <li><span class="check">✓</span> 完整市场洞察数据看板</li>
              <li><span class="check">✓</span> K 线形态自动识别（15种）</li>
              <li><span class="check">✓</span> <strong>AI 市场分析</strong>（GPT-4o）</li>
              <li><span class="check">✓</span> <strong>异动检测 + 叙事识别</strong></li>
              <li><span class="check">✓</span> 资金费率/多空比排名</li>
              <li><span class="check">✓</span> Binance + OKX 双交易所</li>
              <li><span class="check">✓</span> 邮件实时告警</li>
              <li class="disabled"><span>✗</span> API 接口调用</li>
            </ul>
          </div>
          <div class="plan-footer">
            <el-button size="large" type="primary" round @click="$router.push('/login')">7 天免费试用</el-button>
          </div>
        </div>

        <!-- Enterprise -->
        <div class="plan-card">
          <div class="plan-header">
            <h3 class="plan-name">企业版</h3>
            <p class="plan-desc">适合专业机构/做市商团队</p>
            <div class="plan-price">
              <span class="price-num">¥999</span>
              <span class="price-unit">/月</span>
            </div>
            <div class="plan-yearly">年付 ¥9,990/年 <span class="save-tag">省 ¥1,998</span></div>
          </div>
          <div class="plan-body">
            <ul class="plan-features">
              <li><span class="check">✓</span> <strong>不限</strong>交易所账户绑定</li>
              <li><span class="check">✓</span> 实时持仓监控 + WebSocket 推送</li>
              <li><span class="check">✓</span> 全量风险预警 + 自定义规则</li>
              <li><span class="check">✓</span> 无限历史交易复盘</li>
              <li><span class="check">✓</span> 完整市场洞察数据看板</li>
              <li><span class="check">✓</span> K 线形态自动识别（15种）</li>
              <li><span class="check">✓</span> <strong>AI 市场分析</strong>（GPT-4o）</li>
              <li><span class="check">✓</span> <strong>异动检测 + 叙事识别</strong></li>
              <li><span class="check">✓</span> 资金费率/多空比排名</li>
              <li><span class="check">✓</span> 全交易所支持（Binance/OKX/Bybit）</li>
              <li><span class="check">✓</span> 邮件 + Webhook + 短信告警</li>
              <li><span class="check">✓</span> <strong>REST API 接口调用</strong></li>
              <li><span class="check">✓</span> 专属数据保留策略</li>
              <li><span class="check">✓</span> 优先技术工单支持</li>
            </ul>
          </div>
          <div class="plan-footer">
            <el-button size="large" round plain @click="$router.push('/login')">联系销售</el-button>
          </div>
        </div>
      </div>
    </section>

    <!-- Comparison Table -->
    <section class="comparison">
      <div class="section-header">
        <span class="section-tag">功能对比</span>
        <h2 class="section-title">详细功能对比</h2>
        <p class="section-desc">选择最适合你交易风格和团队规模的方案</p>
      </div>
      <div class="comparison-table-wrap">
        <table class="comparison-table">
          <thead>
            <tr>
              <th>功能模块</th>
              <th class="col-free">免费版</th>
              <th class="col-pro">专业版</th>
              <th class="col-ent">企业版</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in comparisonRows" :key="row.name">
              <td class="row-name">
                <span class="row-title">{{ row.name }}</span>
                <span class="row-desc" v-if="row.desc">{{ row.desc }}</span>
              </td>
              <td class="col-free"><span v-html="row.free"></span></td>
              <td class="col-pro"><span v-html="row.pro"></span></td>
              <td class="col-ent"><span v-html="row.ent"></span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- FAQ -->
    <section class="faq">
      <div class="section-header">
        <span class="section-tag">常见问题</span>
        <h2 class="section-title">FAQ</h2>
      </div>
      <div class="faq-list">
        <div class="faq-item" v-for="q in faqs" :key="q.q">
          <h4>{{ q.q }}</h4>
          <p>{{ q.a }}</p>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="cta">
      <h2>7天免费试用，无需绑定信用卡</h2>
      <p>注册即享专业版全部功能，试用结束自动降级为免费版，数据不丢失</p>
      <div class="cta-actions">
        <el-button type="primary" size="large" round @click="$router.push('/login')">免费注册试用</el-button>
        <el-button size="large" round @click="$router.push('/login')">联系销售咨询 →</el-button>
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
            <a href="/#features">核心功能</a>
            <a href="/#how-it-works">系统架构</a>
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
  name: 'Pricing',
  data() {
    return {
      scrolled: false,
      comparisonRows: [
        { name: '交易所账户', desc: '可绑定的交易所账户数量', free: '1 个', pro: '<strong>5 个</strong>', ent: '<strong>不限</strong>' },
        { name: '交易所支持', desc: '数据源覆盖范围', free: 'Binance', pro: 'Binance + OKX', ent: 'Binance/OKX/Bybit' },
        { name: '数据刷新频率', desc: '行情与持仓数据更新间隔', free: '60 秒', pro: '<strong>实时 WebSocket</strong>', ent: '<strong>实时 WebSocket</strong>' },
        { name: '风险预警规则', desc: '可配置的风控规则数量', free: '3 条', pro: '10+ 条全量', ent: '全量 + 自定义' },
        { name: '交易复盘周期', desc: '历史交易数据可查询范围', free: '7 天', pro: '90 天', ent: '<strong>无限</strong>' },
        { name: '市场洞察看板', desc: '行情数据、情绪指标、排名', free: '基础版', pro: '完整版', ent: '完整版 + 导出' },
        { name: 'K线形态识别', desc: '自动检测经典K线形态', free: '✗', pro: '✓ 15 种形态', ent: '✓ 15 种形态' },
        { name: 'AI 市场分析', desc: 'GPT-4o 驱动的智能市场解读', free: '✗', pro: '✓', ent: '✓' },
        { name: '异动检测', desc: 'Top100 代币量价异动扫描', free: '✗', pro: '✓ 5分钟/次', ent: '✓ 可调间隔' },
        { name: '叙事识别', desc: 'LLM 驱动的重大利好分类', free: '✗', pro: '✓', ent: '✓' },
        { name: '告警通道', desc: '风险事件通知方式', free: '站内通知', pro: '站内 + 邮件', ent: '站内 + 邮件 + Webhook + 短信' },
        { name: 'API 接口', desc: '对外 REST API 调用', free: '✗', pro: '✗', ent: '✓ 1000次/天' },
        { name: '数据保留', desc: '历史数据存储时长', free: '30 天', pro: '180 天', ent: '自定义' },
        { name: '技术支持', desc: '响应时效', free: '社区', pro: '邮件 24h', ent: '专属工单 4h' },
      ],
      faqs: [
        { q: '免费版有哪些限制？', a: '免费版支持 1 个 Binance 交易所账户绑定，提供基础持仓监控和 3 条风险预警规则。交易复盘数据保留 7 天。如果不需要 AI 分析和异动检测，免费版可以满足基本的持仓查看需求。' },
        { q: '如何升级或降级方案？', a: '在系统设置中可随时切换方案。升级即时生效，按剩余天数折算差价。降级在下个计费周期生效，期间仍可享受当前方案的全部功能。' },
        { q: '7天免费试用需要绑定信用卡吗？', a: '不需要。注册即自动开通专业版 7 天免费试用，无需绑定任何支付方式。试用期结束后自动切换为免费版，你的数据不会丢失。' },
        { q: '专业版和企业版的主要区别是什么？', a: '企业版面向机构和做市商团队，核心区别在于：不限交易所账户数量、支持 API 接口调用集成到自有系统、可自定义告警规则和数据保留策略、专属技术工单 4 小时响应。' },
        { q: '支持哪些交易所？', a: '目前支持 Binance 合约（USDS-M）、OKX 合约和 Bybit 合约。企业版覆盖全部三个交易所，专业版覆盖 Binance + OKX，免费版仅支持 Binance。' },
        { q: '数据安全如何保障？', a: '交易所 API Key 使用 AES-256 加密存储，Secret Key 仅在前端展示一次。系统不存储你的交易所资金，所有交易操作需在交易所侧完成。我们不会将你的持仓数据用于任何商业用途。' },
        { q: '可以开具发票吗？', a: '专业版和企业版年付方案支持开具增值税普通发票和专用发票。月付方案累计满 6 个月后可申请开票。请联系客服获取开票信息。' },
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
    }
  }
}
</script>

<style lang="scss" scoped>
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

.pricing {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
  color: $text-primary;
  background: $bg-primary;
  overflow-x: hidden;
}

// === Navbar (same as landing) ===
.nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
  padding: 16px 0; transition: all 0.3s ease;
  &.nav-scrolled {
    background: rgba(10, 14, 26, 0.92); backdrop-filter: blur(16px);
    border-bottom: 1px solid $border; padding: 10px 0;
  }
}
.nav-inner {
  max-width: 1200px; margin: 0 auto; padding: 0 24px;
  display: flex; align-items: center; justify-content: space-between;
}
.nav-brand { display: flex; align-items: center; gap: 8px; }
.nav-logo { font-size: 28px; }
.nav-title { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
.nav-links { display: flex; gap: 32px;
  @media (max-width: 768px) { display: none; }
}
.nav-link {
  color: $text-secondary; text-decoration: none; font-size: 14px; transition: color 0.2s;
  &:hover { color: $text-primary; }
  &.active { color: $accent-light; font-weight: 500; }
}
.nav-actions { display: flex; align-items: center; gap: 12px; }

// === Hero ===
.hero {
  position: relative; padding: 160px 24px 80px; text-align: center; overflow: hidden;
}
.hero-bg {
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse 60% 50% at 50% 0%, rgba(59, 130, 246, 0.12), transparent),
    radial-gradient(ellipse 40% 40% at 80% 70%, rgba(139, 92, 246, 0.08), transparent);
  pointer-events: none;
}
.hero-content { position: relative; max-width: 700px; margin: 0 auto; }
.hero-badge {
  display: inline-block; padding: 6px 16px; border-radius: 20px;
  background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3);
  color: $accent-light; font-size: 13px; margin-bottom: 24px;
}
.hero-title {
  font-size: 40px; font-weight: 800; line-height: 1.3; letter-spacing: -1px; margin: 0 0 20px;
  @media (max-width: 768px) { font-size: 28px; }
}
.hero-highlight {
  background: $accent-gradient;
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.hero-subtitle {
  font-size: 16px; color: $text-secondary; line-height: 1.7; margin: 0;
}

// === Section shared ===
section { padding: 80px 24px; }
.section-header { text-align: center; max-width: 600px; margin: 0 auto 48px; }
.section-tag {
  display: inline-block; padding: 4px 12px; border-radius: 12px;
  background: rgba(59, 130, 246, 0.12); color: $accent-light; font-size: 13px; font-weight: 500;
  margin-bottom: 12px;
}
.section-title { font-size: 28px; font-weight: 700; margin: 0 0 12px; letter-spacing: -0.5px; }
.section-desc { font-size: 15px; color: $text-secondary; line-height: 1.6; margin: 0; }

// === Plans ===
.plans { background: $bg-secondary; }
.plans-grid {
  max-width: 1160px; margin: 0 auto;
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;
  @media (max-width: 900px) { grid-template-columns: 1fr; max-width: 420px; }
}

.plan-card {
  background: $bg-card; border: 1px solid $border; border-radius: 16px;
  padding: 40px 28px; position: relative;
  display: flex; flex-direction: column;
  transition: all 0.3s ease;
  &:hover { border-color: rgba(59, 130, 246, 0.25); }
  &.featured {
    border-color: rgba(59, 130, 246, 0.4);
    box-shadow: 0 0 40px rgba(59, 130, 246, 0.1);
    transform: scale(1.03);
    @media (max-width: 900px) { transform: none; }
  }
}

.plan-ribbon {
  position: absolute; top: 14px; right: -28px;
  background: $accent-gradient; color: #fff; font-size: 12px; font-weight: 600;
  padding: 4px 32px; transform: rotate(45deg);
}

.plan-header { text-align: center; margin-bottom: 28px; }
.plan-name { font-size: 22px; font-weight: 700; margin: 0 0 6px; }
.plan-desc { font-size: 14px; color: $text-secondary; margin: 0 0 20px; }
.plan-price { margin-bottom: 8px; }
.price-num { font-size: 42px; font-weight: 800; letter-spacing: -1px; }
.price-unit { font-size: 16px; color: $text-secondary; }
.plan-yearly {
  font-size: 13px; color: $text-secondary;
  .save-tag {
    display: inline-block; padding: 1px 8px; border-radius: 8px;
    background: rgba(34, 197, 94, 0.15); color: #22c55e; font-size: 12px; margin-left: 4px;
  }
}

.plan-body { flex: 1; margin-bottom: 28px; }

.plan-features {
  list-style: none; padding: 0; margin: 0;
  li {
    font-size: 13px; padding: 6px 0; color: $text-secondary;
    .check { color: #22c55e; margin-right: 8px; font-weight: 600; }
    span:first-child { display: inline-block; width: 20px; }
    strong { color: $text-primary; }
    &.disabled { color: rgba(255,255,255,0.2); span { color: rgba(255,255,255,0.15); } }
  }
}

.plan-footer { text-align: center; }

// === Comparison Table ===
.comparison { background: $bg-primary; }
.comparison-table-wrap {
  max-width: 1000px; margin: 0 auto; overflow-x: auto;
}
.comparison-table {
  width: 100%; border-collapse: collapse; font-size: 14px;
  th {
    padding: 14px 20px; text-align: center; font-weight: 600; border-bottom: 2px solid $border;
    &:first-child { text-align: left; }
  }
  .col-free { color: $text-secondary; }
  .col-pro { color: $accent-light; background: rgba(59,130,246,0.04); }
  .col-ent { color: #a78bfa; }
  td {
    padding: 14px 20px; border-bottom: 1px solid $border; text-align: center;
    &:first-child { text-align: left; }
  }
  tr:hover td { background: rgba(255,255,255,0.02); }
}
.row-name { display: flex; flex-direction: column; }
.row-title { font-weight: 500; }
.row-desc { font-size: 12px; color: $text-secondary; margin-top: 2px; }

// === FAQ ===
.faq { background: $bg-secondary; }
.faq-list {
  max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px;
}
.faq-item {
  background: $bg-card; border: 1px solid $border; border-radius: $radius; padding: 24px 28px;
  h4 { font-size: 16px; font-weight: 600; margin: 0 0 8px; }
  p { font-size: 14px; color: $text-secondary; line-height: 1.7; margin: 0; }
}

// === CTA ===
.cta {
  text-align: center; padding: 80px 24px;
  background: radial-gradient(ellipse 60% 50% at 50% 0%, rgba(59, 130, 246, 0.1), transparent), $bg-primary;
  h2 { font-size: 28px; font-weight: 700; margin: 0 0 12px; }
  p { font-size: 15px; color: $text-secondary; margin: 0 0 28px; }
}
.cta-actions { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }

// === Footer ===
.footer { background: $bg-secondary; border-top: 1px solid $border; padding: 56px 24px 0; }
.footer-inner {
  max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; gap: 48px;
  @media (max-width: 640px) { flex-direction: column; gap: 32px; }
}
.footer-brand {
  max-width: 240px;
  span { font-size: 18px; font-weight: 700; }
  p { font-size: 13px; color: $text-secondary; line-height: 1.6; margin-top: 8px; }
}
.footer-links { display: flex; gap: 64px; }
.footer-col {
  h4 { font-size: 14px; font-weight: 600; margin: 0 0 12px; }
  a {
    display: block; color: $text-secondary; text-decoration: none; font-size: 13px;
    padding: 4px 0; transition: color 0.2s;
    &:hover { color: $text-primary; }
  }
}
.footer-bottom {
  max-width: 1200px; margin: 0 auto; padding: 28px 0;
  border-top: 1px solid $border; margin-top: 40px; text-align: center;
  p { font-size: 13px; color: $text-secondary; margin: 0; }
}
</style>
