# 数字货币合约交易风控系统

这是一个基于 FastAPI 和 Vue 3 的数字货币合约交易风控与监控系统，侧重实时监控、风险预警、异常新闻归因和辅助决策，不直接代替用户自动执行交易。

## 项目定位

- 面向数字货币合约交易场景的风控监控平台
- 提供市场洞察、账户同步、风险检查和异常事件追踪
- 支持将异常扫描和新闻入库拆成独立 worker，提高信息库更新稳定性

## 技术栈

### 后端

- Web 框架: FastAPI
- 数据库: MySQL
- 缓存: Redis
- HTTP 客户端: httpx
- ORM: SQLAlchemy

### 前端

- 框架: Vue 3
- 状态管理: Vuex 4
- 路由: Vue Router 4
- UI: Element Plus
- 图表: ECharts
- 构建工具: Vite

## 核心功能

### 市场洞察看板

- 24 小时成交量、总市值、BTC 市值占比、活跃币种数
- 涨幅榜、跌幅榜、成交量榜 Top 10
- 恐惧贪婪指数、资金费率、多空比、未平仓合约量
- 市场情绪驱动的交易信号和价格区间建议

### 异常代币监控

- 持续扫描 Binance USDT 永续前 100 成交额币种
- 优先使用官方公告源和 RSS 新闻池做低成本匹配
- 对异常事件抓取相关新闻、标注来源并给出可信度判断
- 结合本地启发式规则或可选远程 LLM 输出交易建议

### 风控能力

- 资金上限、仓位规模、杠杆倍数、订单频率控制
- 强平风险预警、账户风险度计算、多级告警
- 账户异常行为检测与风险配置管理

### 实时同步与推送

- Binance 持仓同步
- 行情轮询与看板刷新
- WebSocket 实时推送

## 运行角色

项目现在支持两种后端运行方式。

| 角色 | 负责内容 | 关键开关 |
| --- | --- | --- |
| backend | API、WebSocket、行情轮询、仓位同步 | `START_MARKET_POLLER=True` `START_POSITION_SYNC=True` `START_ANOMALY_MONITOR=False` |
| insight-worker | 异常扫描、新闻抓取、信息库更新 | `START_MARKET_POLLER=False` `START_POSITION_SYNC=False` `START_ANOMALY_MONITOR=True` |
| 单进程开发 | 本地快速调试，全部任务在一个进程里跑 | 三个开关都设为 `True` |

使用 Docker Compose 时，默认已经拆成 `backend` 和 `insight-worker` 两个角色。

## 新闻与异常监控说明

- 官方源优先: Binance、OKX、Bybit、Coinbase
- 默认 RSS 池包含 CoinDesk、Cointelegraph、PANews 中文快讯、Decrypt、Blockworks、The Block、CryptoSlate、Bitcoin Magazine、The Defiant、AMBCrypto、CoinGape、Bitcoin.com News
- PANews 当前可用中文 RSS 地址是 `https://www.panewslab.com/zh/rss/newsflash.xml`
- `zh.panewslab.com` 目前没有可解析的 RSS 主机记录，不建议配置到源列表里
- `NEWS_PROVIDER=auto` 时，只有当主新闻池没有命中时，才会回退到 CryptoPanic 或 Brave News Search
- `NEWS_SYMBOL_ALIAS_MAP` 和 `NEWS_SYMBOL_OFFICIAL_FEEDS` 都是 JSON 字符串，用来提升币种匹配和补充项目方官方 feed
- `ENABLE_GPT_5_1` 只控制市场看板里的本地摘要文案，不会触发 OpenAI 请求
- 异常新闻真实性分析是否调用远程模型，由 `ANOMALY_LLM_PROVIDER` 决定；设为 `disabled` 时只走本地启发式分析

## 系统要求

- Python 3.8+
- Node.js >= 14
- MySQL 8.0+
- Redis 6+
- npm >= 6.14.0
- Docker，可选

## 目录结构

```text
trade-helper/
├── app/                  # 后端应用
│   ├── api/              # API 路由
│   ├── core/             # 核心模块
│   ├── models/           # SQLAlchemy 模型
│   ├── schemas/          # Pydantic 模型
│   └── services/         # 业务服务
├── config/               # 配置文件
├── frontend/             # 前端应用
│   ├── src/
│   │   ├── api/          # 前端 API 封装
│   │   ├── components/   # 通用组件
│   │   ├── router/       # 路由配置
│   │   ├── store/        # Vuex 状态管理
│   │   ├── views/        # 页面视图
│   │   └── main.js       # 应用入口
│   └── package.json
├── scripts/              # 管理脚本
├── tests/                # 测试用例
├── docker-compose.yml    # 本地容器编排
├── Dockerfile            # 后端镜像定义
└── requirements.txt      # Python 依赖
```

## 快速开始

### 1. 后端开发

1. 创建并激活虚拟环境

```bash
python -m venv venv
source venv/bin/activate
```

Windows:

```bash
.\venv\Scripts\activate
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 复制环境变量文件

```bash
cp .env.example .env
```

4. 初始化数据库

```bash
python scripts/init_db.py
```

5. 启动后端

```bash
python main.py
```

默认地址:

- API 文档: http://localhost:8000/api/docs
- 健康检查: http://localhost:8000/health
- API 基础路径: http://localhost:8000/api/v1

### 2. 前端开发

```bash
cd frontend
npm install
npm run dev
```

默认前端开发地址:

- http://localhost:3000

构建生产包:

```bash
npm run build
```

本地预览构建结果:

```bash
npm run preview
```

### 3. 推荐的分离运行模式

如果你希望“信息库更新”和 API 分开跑，建议使用两个进程。

API 进程:

```bash
START_ANOMALY_MONITOR=False python main.py
```

异常扫描 worker:

```bash
python scripts/run_anomaly_worker.py
```

### 4. Docker Compose

```bash
docker compose up -d --build
```

默认服务角色:

- `backend`: API、WebSocket、行情轮询、仓位同步
- `insight-worker`: 异常扫描、新闻抓取、信息库更新
- `mysql`: MySQL 8
- `redis`: Redis 6
- `frontend`: Nginx 承载的前端静态页面

默认容器访问地址:

- API 文档: http://localhost:8029/api/docs
- 前端页面: http://localhost:8030

## 关键环境变量

完整示例请看 `.env.example`。下面是最常用的一组。

| 变量 | 作用 |
| --- | --- |
| `START_MARKET_POLLER` | 控制当前进程是否启动行情轮询 |
| `START_POSITION_SYNC` | 控制当前进程是否启动仓位同步 |
| `START_ANOMALY_MONITOR` | 控制当前进程是否启动异常扫描和新闻入库 |
| `ANOMALY_LLM_PROVIDER` | 异常新闻分析模式，常见值为 `disabled` 或 `openai-compatible` |
| `NEWS_PROVIDER` | 新闻兜底提供方，常见值为 `auto`、`brave`、`cryptopanic` |
| `NEWS_RSS_FEED_URLS` | 逗号分隔的 RSS 源列表 |
| `NEWS_SYMBOL_ALIAS_MAP` | 币种别名 JSON，用于提升匹配率 |
| `NEWS_SYMBOL_OFFICIAL_FEEDS` | 币种到官方 RSS 的 JSON 映射 |
| `BRAVE_SEARCH_API_KEY` | Brave Search API Key，`NEWS_PROVIDER=auto` 或 `brave` 时可用 |
| `NEWS_API_KEY` | CryptoPanic API Key，`NEWS_PROVIDER=auto` 或 `cryptopanic` 时可用 |

如果你要启用兼容 OpenAI 的远程分析接口，可以额外配置:

```bash
ANOMALY_LLM_PROVIDER=openai-compatible
LLM_API_KEY=your-llm-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

## 风控规则配置示例

系统支持通过配置或管理界面设置核心风控规则。

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

## 告警方式

当前支持以下告警通道:

- 邮件通知
- Webhook 回调
- 企业微信
- Telegram Bot

## 项目当前状态

### 后端

- FastAPI 主框架、MySQL、Redis 已接通
- 用户认证和核心风控逻辑已实现
- PositionSyncService 已支持 Binance 合约持仓同步
- MarketDataService 已支持行情轮询和看板数据更新
- 异常扫描支持独立 worker 运行

### 前端

- 已包含 Dashboard、Login、Positions、RiskAlerts、Settings、Accounts 等页面
- 已接入 WebSocket 客户端用于接收后端推送
- Vite 开发和生产构建链路可用

### 基础设施

- `docker-compose.yml` 已包含 MySQL、Redis、Backend、Insight Worker、Frontend
- 本地容器模式已支持 API 与信息库更新分离部署

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交变更
4. 发起 Pull Request

## 许可证

MIT License

## 联系方式

- 项目维护者: [Your Name]
- 邮箱: [Your Email]
- 项目 Issues: [Repository Issues URL]
