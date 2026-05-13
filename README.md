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
- 新闻会写入持久化归档表，Dashboard 和 `/api/v1/market-insight/news` 会优先读取归档，只有归档过期时才回源抓取
- `NEWS_SYMBOL_ALIAS_MAP` 和 `NEWS_SYMBOL_OFFICIAL_FEEDS` 都是 JSON 字符串，用来提升币种匹配和补充项目方官方 feed
- `ENABLE_GPT_5_1` 只控制市场看板里的本地摘要文案，不会触发 OpenAI 请求
- 异常新闻真实性分析是否调用远程模型，由 `ANOMALY_LLM_PROVIDER` 决定；设为 `disabled` 时只走本地启发式分析

## 认证与会话续期

- 后端采用双 JWT 方案: 短效 `access token` + 长效 `refresh token`
- 前端登录后会同时保存两种 token，并记录 access token 的本地过期时间
- 当前端检测到 access token 快过期，或业务请求收到 `401` 时，会自动调用 `/api/v1/auth/refresh` 静默续期
- Refresh token 使用轮换策略: 每次刷新成功后，旧 refresh token 会立即失效
- 调用 `/api/v1/auth/logout` 时，当前 refresh token 会被吊销，之后不能继续换取新的 access token
- 业务接口只接受 `access token`；`refresh token` 不能直接访问受保护接口

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
│   ├── package.json
│   └── vite.config.js
├── scripts/              # 管理脚本
├── tests/                # 测试用例
├── docker-compose.yml    # 公共容器编排，默认不内置 MySQL
├── docker-compose.dev.yml   # 开发环境覆盖，包含 MySQL 和代码挂载
├── docker-compose.prod.yml  # 生产环境覆盖，适合接宿主机 MySQL
├── .env.example          # 后端环境变量示例
├── Dockerfile            # 后端镜像定义
└── requirements.txt      # Python 依赖
```

## 快速开始

推荐先按“本地单进程开发”跑通，再根据需要切到“双进程开发”或 Docker Compose。

### 1. 环境准备

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

前端依赖:

```bash
cd frontend
npm install
```

回到项目根目录:

```bash
cd ..
```

3. 复制环境变量文件

```bash
cp .env.example .env
```

建议本地开发时让后端监听 `8029`，这样能直接和前端 Vite 默认代理配置对齐。

4. 初始化数据库

```bash
python scripts/init_db.py
```

### 2. 端口约定

| 场景 | 默认地址 |
| --- | --- |
| 本地后端 API | `http://localhost:8029/api/v1` |
| 本地后端文档 | `http://localhost:8029/api/docs` |
| 本地健康检查 | `http://localhost:8029/health` |
| 本地前端 Vite | `http://localhost:8030` |
| Docker 前端页面 | `http://localhost:8030` |

说明:

- 直接运行 `python main.py` 时，后端默认读取 `PORT` 环境变量；`.env.example` 里的默认值是 `8000`
- 本 README 的本地联调示例统一使用 `8029`，避免和前端代理配置不一致
- Docker 模式下，容器内后端仍监听 `8000`，宿主机映射为 `8029`

### 3. 本地单进程开发

适合快速调试，API、行情轮询、仓位同步和异常扫描都在一个进程里运行。

```bash
START_MARKET_POLLER=True \
START_POSITION_SYNC=True \
START_ANOMALY_MONITOR=True \
uvicorn main:app --host 0.0.0.0 --port 8029 --reload
```

启动前端:

```bash
cd frontend
npm run dev
```

访问地址:

- 前端: `http://localhost:8030`
- API 文档: `http://localhost:8029/api/docs`
- API 基础路径: `http://localhost:8029/api/v1`

### 4. 本地双进程开发

适合稳定观察“信息库”更新，不让异常扫描影响 API 响应。

API 进程:

```bash
START_MARKET_POLLER=True \
START_POSITION_SYNC=True \
START_ANOMALY_MONITOR=False \
uvicorn main:app --host 0.0.0.0 --port 8029 --reload
```

Worker 进程:

```bash
START_MARKET_POLLER=False \
START_POSITION_SYNC=False \
START_ANOMALY_MONITOR=True \
python scripts/run_anomaly_worker.py
```

### 5. Docker Compose

#### 开发环境

适合本地完整联调，使用容器内 MySQL，并为后端启用代码挂载和热重载。

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

开发环境默认服务:

- `mysql`: MySQL 8.0
- `redis`: Redis 6
- `backend`: API、WebSocket、行情轮询、仓位同步
- `insight-worker`: 异常扫描、新闻抓取、信息库更新
- `frontend`: Nginx 承载的前端静态页面

#### 生产环境

适合接宿主机 MySQL，容器内只启动 Redis、后端角色和前端静态站点。

首次启动:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d redis backend insight-worker frontend
```

代码有变更时重建并更新:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build backend insight-worker frontend
```

仅更新后端:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build backend insight-worker
```

仅更新前端:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build frontend
```

仅重启容器:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart backend insight-worker frontend
```

查看日志:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend insight-worker frontend
```

默认容器访问地址:

- API 文档: `http://localhost:8029/api/docs`
- 前端页面: `http://localhost:8030`

环境文件说明:

- `docker-compose.yml`: 公共基础配置，默认不包含 MySQL，适合生产或接外部数据库
- `docker-compose.dev.yml`: 开发环境覆盖，提供 MySQL、代码挂载和后端热重载
- `docker-compose.prod.yml`: 生产环境覆盖，提供容器访问宿主机的能力

前端生产部署建议:

- 推荐先构建前端静态资源，再由 Nginx 提供静态文件服务
- 浏览器统一访问同域 `/api/v1` 和 `/ws`，由 Nginx 反向代理到后端容器
- 不建议生产环境让浏览器直接请求 `http://后端主机:8029/api/v1`，这样会引入跨域、端口暴露和代理链路不一致问题

## 关键环境变量

完整示例请看 `.env.example`。下面是最常用的一组。

| 变量 | 作用 |
| --- | --- |
| `START_MARKET_POLLER` | 控制当前进程是否启动行情轮询 |
| `START_POSITION_SYNC` | 控制当前进程是否启动仓位同步 |
| `START_ANOMALY_MONITOR` | 控制当前进程是否启动异常扫描和新闻入库 |
| `SECRET_KEY` | JWT 签名密钥，生产环境必须替换 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token 有效期，建议保持短效，例如 `15` 到 `30` 分钟 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token 有效期，建议 `7` 到 `30` 天 |
| `ANOMALY_LLM_PROVIDER` | 异常新闻分析模式，常见值为 `disabled` 或 `openai-compatible` |
| `NEWS_PROVIDER` | 新闻兜底提供方，常见值为 `auto`、`brave`、`cryptopanic` |
| `NEWS_ARCHIVE_ENABLED` | 是否启用持久化新闻归档 |
| `NEWS_ARCHIVE_STALE_AFTER_SECONDS` | 全局新闻归档多久视为过期 |
| `NEWS_RSS_FEED_URLS` | 逗号分隔的 RSS 源列表 |
| `NEWS_SYMBOL_ALIAS_MAP` | 币种别名 JSON，用于提升匹配率 |
| `NEWS_SYMBOL_OFFICIAL_FEEDS` | 币种到官方 RSS 的 JSON 映射 |
| `BRAVE_SEARCH_API_KEY` | Brave Search API Key，`NEWS_PROVIDER=auto` 或 `brave` 时可用 |
| `NEWS_API_KEY` | CryptoPanic API Key，`NEWS_PROVIDER=auto` 或 `cryptopanic` 时可用 |

新闻归档接口示例:

```bash
curl "http://localhost:8029/api/v1/market-insight/news?limit=20&symbol=BTCUSDT&hours=24"
```

如果你要启用兼容 OpenAI 的远程分析接口，可以额外配置:

```bash
ANOMALY_LLM_PROVIDER=openai-compatible
LLM_API_KEY=your-llm-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

认证相关的最小配置示例:

```bash
SECRET_KEY=replace-with-a-long-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

默认登录与续期接口:

```text
POST /api/v1/auth/token
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

如果你希望缩短 access token 生命周期来提高安全性，只需要调小 `ACCESS_TOKEN_EXPIRE_MINUTES`。前端仍会通过 refresh token 做无感续期，不需要同步改页面逻辑。

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

- `docker-compose.yml` 提供 Redis、Backend、Insight Worker、Frontend 的公共编排
- `docker-compose.dev.yml` 额外提供 MySQL 和后端代码挂载，适合本地联调
- 容器模式已支持 API 与信息库更新分离部署

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
