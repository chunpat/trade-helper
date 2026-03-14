# 数字货币合约交易风控系统

一个基于Python和Vue.js的完整的数字货币合约交易风险管控系统，提供实时监控、风险预警、资金管理等功能。

## 系统架构

### 后端技术栈

- **Web框架**: FastAPI
- **数据库**: MySQL
- **消息队列**: Redis PubSub
- **缓存系统**: Redis

### 前端技术栈

- **框架**: Vue 3
- **状态管理**: Vuex 4
- **路由**: Vue Router 4
- **UI库**: Element Plus
- **图表**: ECharts
- **构建工具**: Vite

## 功能特点

### 1. 市场洞察数据看板 🆕
- **市场总览**: 24小时总成交量、总市值、BTC市值占比、活跃币种数
- **排行榜**: 涨幅榜、跌幅榜、成交量榜Top10实时更新
- **市场情绪**: 
  - 恐惧贪婪指数监测
  - 资金费率分析
  - 多空比数据
  - 未平仓合约量追踪
- **交易信号**: 
  - 基于市场情绪的智能信号生成
  - 做多/做空建议
  - 入场、止损、止盈价格推荐
- **异常代币监控**:
  - 后台持续扫描 Binance USDT 永续前100成交额币种
  - 优先从全局 RSS 新闻池和公告源抓取新闻并在本地匹配异常币种
  - 对异常币种抓取相关新闻并标注来源
  - 结合可选远程 LLM 或本地启发式规则输出真实性评级与交易建议
- **自选币种**: 自定义监控币种，实时查看价格、涨跌幅、成交量
- **自动刷新**: 每30秒自动更新数据，把握市场脉搏

### 2. 资金风控
- 总资金监控与预警
- 单币种资金上限控制
- 资金利用率实时计算
- 智能资金分配策略

### 3. 仓位风控
- 最大仓位限制
- 杠杆倍数管理
- 强平风险预警系统
- 仓位集中度监控

### 4. 订单风控
- 订单频率限制
- 单笔订单规模控制
- 委托价格偏离度检查
- 错误订单智能拦截

### 5. 账户风控
- 实时盈亏监控
- 风险度动态计算
- 多级风险预警
- 账户异常行为检测

## 系统要求

- Python 3.8+
- Node.js >= 14.0.0
- MySQL 8.0+
- Redis 6+
- npm >= 6.14.0
- Docker (可选，用于容器化部署)

## 目录结构

```
trade-helper/
├── app/                 # 后端应用
│   ├── api/            # API 路由
│   ├── core/           # 核心功能模块
│   ├── models/         # 数据模型
│   ├── schemas/        # Pydantic 模型
│   └── services/       # 业务逻辑服务
├── frontend/           # 前端应用
│   ├── src/
│   │   ├── api/       # API请求
│   │   ├── components/# 通用组件
│   │   ├── router/    # 路由配置
│   │   ├── store/     # Vuex状态管理
│   │   ├── views/     # 页面视图
│   │   └── main.js    # 应用入口
│   └── package.json   
├── config/             # 配置文件
├── scripts/            # 管理脚本
├── tests/             # 测试用例
└── requirements.txt    # Python依赖
```

## 快速开始

### 后端设置

1. 创建并激活Python虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
.\venv\Scripts\activate  # Windows
```

2. 安装Python依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的配置信息
```

异常代币监控功能需要额外配置以下变量：
```bash
ENABLE_GPT_5_1=False
ANOMALY_LLM_PROVIDER=disabled
NEWS_PROVIDER=auto
NEWS_API_KEY=your-cryptopanic-token
BRAVE_SEARCH_API_KEY=your-brave-search-token
NEWS_ENABLE_BINANCE_ANNOUNCEMENTS=True
NEWS_ENABLE_OKX_ANNOUNCEMENTS=True
NEWS_ENABLE_BYBIT_ANNOUNCEMENTS=True
NEWS_ENABLE_COINBASE_BLOG=True
NEWS_OFFICIAL_PAGE_ITEM_LIMIT=12
NEWS_RSS_FEED_URLS=https://www.coindesk.com/arc/outboundfeeds/rss/,https://cointelegraph.com/rss,https://decrypt.co/feed,https://blockworks.co/feed,https://www.theblock.co/rss.xml
NEWS_SYMBOL_OFFICIAL_FEEDS={"KAT":["https://medium.com/feed/@katana"]}
ANOMALY_SCAN_INTERVAL=300
ANOMALY_ALERT_THRESHOLD=0.58
ANOMALY_COOLDOWN_MINUTES=30
```

说明：
- `ENABLE_GPT_5_1` 只控制市场看板里的本地摘要文案，不会调用 OpenAI。
- 异常新闻真实性分析是否调用远程模型由 `ANOMALY_LLM_PROVIDER` 控制；设为 `disabled` 时只走本地启发式分析，不产生 OpenAI 费用。
- Binance 目前我没有接入稳定 RSS，因为探测到常见 RSS 路径只返回 202 空壳；现在改为直接抓 Binance 官方公告 CMS 接口，作为全局新闻池的一部分。
- 新闻获取默认先走 Binance / OKX / Bybit 官方公告、Coinbase 官方博客和 RSS 全局新闻池，再在本地按币种匹配；只有主新闻池没有命中时，`NEWS_PROVIDER=auto` 才会尝试 CryptoPanic 和 Brave News Search 兜底。
- 默认 RSS 源已经扩展到 CoinDesk、Cointelegraph、Decrypt、Blockworks、The Block、CryptoSlate、Bitcoin Magazine、The Defiant、AMBCrypto、CoinGape、Bitcoin.com News。
- 可以通过 `NEWS_SYMBOL_ALIAS_MAP` 给歧义币种补充别名，例如 `TRUMP -> official trump`，提升本地匹配率。
- 可以通过 `NEWS_SYMBOL_OFFICIAL_FEEDS` 按币种补充项目方官方 RSS / Atom / Medium feed，例如 `KAT -> https://medium.com/feed/@katana`；这些官方 feed 会在外部搜索之前优先使用。
- `NEWS_SEARCH_CACHE_SECONDS` 和 `NEWS_SEARCH_EMPTY_CACHE_SECONDS` 用于降低 Brave/CryptoPanic 的重复查询频率。
- 如果仍需接入兼容 OpenAI 的接口，可配置：

```bash
ANOMALY_LLM_PROVIDER=openai-compatible
LLM_API_KEY=your-llm-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

4. 初始化数据库：
```bash
python scripts/init_db.py
```

5. 启动后端服务：
```bash
python main.py
```

后端服务将在以下地址提供：
- API文档：http://localhost:8000/api/docs
- 健康检查：http://localhost:8000/health
- API基础URL：http://localhost:8000/api/v1

### 前端设置

1. 安装前端依赖：
```bash
cd frontend
npm install
```

2. 启动开发服务器：
```bash
npm run serve
```

3. 构建生产版本：
```bash
npm run build
```

前端应用将在以下地址提供：
- 开发环境：http://localhost:3000
- 生产环境：将dist目录部署到Web服务器

## 部署

### Docker部署

1. 构建后端镜像：
```bash
docker build -t trade-helper-backend .
```

2. 构建前端镜像：
```bash
cd frontend
docker build -t trade-helper-frontend .
```

3. 使用docker-compose启动服务：
```bash
docker-compose up -d
```

## 风控规则配置

系统支持灵活的风控规则配置，可以通过配置文件或管理界面设置：

```yaml
risk_control:
  position:
    max_leverage: 20
    max_position_value: 1000000
    risk_ratio_threshold: 0.8
  order:
    max_single_order: 100000
    price_deviation_limit: 0.05
    order_frequency_limit: 10
  account:
    max_daily_loss: 50000
    risk_level_threshold: 0.9
```

## 告警配置

支持多种告警方式：
- 邮件通知
- Webhook回调
- 企业微信/钉钉集成
- Telegram Bot

## 📊 项目当前进度 (Current Status)

这是一个 **数字货币合约交易风控监控系统**，主要侧重于**监控**和**风险预警**，而非自动交易执行。

### 3. 后端 (Backend - FastAPI)
*   **基础架构**: FastAPI 框架搭建完成，数据库 (MySQL) 和缓存 (Redis) 连接已配置。
*   **核心服务**:
    *   `Auth`: 用户认证 (JWT) 已实现。
    *   `RiskControlService`: 实现了核心风控逻辑（持仓价值检查、杠杆检查、订单风险检查）。
    *   `PositionSyncService`: 实现了从 Binance 合约接口**同步持仓**的功能（目前是轮询机制）。
    *   `MarketDataService`: 实现了市场价格的**轮询获取**，用于计算持仓盈亏和风险。
    *   `WSBroadcast`: 实现了 WebSocket 广播，用于向前端推送实时数据。
*   **API 接口**: 暴露了 `auth`, `market`, `risk_control` 等 API。

### 4. 前端 (Frontend - Vue 3)
*   **页面结构**: 搭建了 Dashboard, Login, Positions, RiskAlerts, Settings, Accounts 等页面。
*   **Dashboard**: 实现了总持仓价值、风险预警数、日内盈亏的展示组件。
*   **交互**: 初步集成了 WebSocket (`wsClient.js`) 用于接收后端推送。

### 5. 基础设施 (Infrastructure)
*   **Docker**: 完整的 `docker-compose.yml`，包含 MySQL, Redis, Backend, Frontend 服务。

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交变更
4. 发起 Pull Request

## 许可证

MIT License

## 联系方式

- 项目维护者：[Your Name]
- 邮箱：[Your Email]
- 项目Issues：[Repository Issues URL]
