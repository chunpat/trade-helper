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

### 1. 资金风控
- 总资金监控与预警
- 单币种资金上限控制
- 资金利用率实时计算
- 智能资金分配策略

### 2. 仓位风控
- 最大仓位限制
- 杠杆倍数管理
- 强平风险预警系统
- 仓位集中度监控

### 3. 订单风控
- 订单频率限制
- 单笔订单规模控制
- 委托价格偏离度检查
- 错误订单智能拦截

### 4. 账户风控
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

#### 1. 后端 (Backend - FastAPI)
*   **基础架构**: FastAPI 框架搭建完成，数据库 (MySQL) 和缓存 (Redis) 连接已配置。
*   **核心服务**:
    *   `Auth`: 用户认证 (JWT) 已实现。
    *   `RiskControlService`: 实现了核心风控逻辑（持仓价值检查、杠杆检查、订单风险检查）。
    *   `PositionSyncService`: 实现了从 Binance 合约接口**同步持仓**的功能（目前是轮询机制）。
    *   `MarketDataService`: 实现了市场价格的**轮询获取**，用于计算持仓盈亏和风险。
    *   `WSBroadcast`: 实现了 WebSocket 广播，用于向前端推送实时数据。
*   **API 接口**: 暴露了 `auth`, `market`, `risk_control` 等 API。

#### 2. 前端 (Frontend - Vue 3)
*   **页面结构**: 搭建了 Dashboard, Login, Positions, RiskAlerts, Settings, Accounts 等页面。
*   **Dashboard**: 实现了总持仓价值、风险预警数、日内盈亏的展示组件。
*   **交互**: 初步集成了 WebSocket (`wsClient.js`) 用于接收后端推送。

#### 3. 基础设施 (Infrastructure)
*   **Docker**: 完整的 `docker-compose.yml`，包含 MySQL, Redis, Backend, Frontend 服务。

### 📝 待办事项清单 (Todo List)

#### 1. 核心功能完善 (Core Features)
- [ ] **风控配置**: 实现风控参数的增删改查 (CRUD) 接口及前端页面。
- [ ] **报警通知渠道集成**: 目前 `RiskAlert` 只是存入数据库。需要实现实际的通知发送功能（如：邮件、Telegram Bot、钉钉/飞书 Webhook）。
- [ ] **优化行情获取**: 目前 `MarketDataService` 使用的是 REST API 轮询 (10秒一次)。建议接入 Binance WebSocket 市场流，以实现毫秒级风控。
- [ ] **完善交易所适配器**: `BinanceAdapter` 目前仅支持 `fetch_positions`。如果未来需要“一键平仓”或“减仓”等风控操作，需要实现 `place_order` / `cancel_order` 接口。
- [ ] **历史数据归档**: 考虑添加定时任务，归档旧的 `OrderLog` 和 `TickerHistory` 数据，防止数据库过大。

#### 2. 前端对接与优化 (Frontend Integration)
- [ ] **全页面数据联调**: 确认 `Positions.vue` (持仓列表) 和 `RiskAlerts.vue` (报警历史) 是否已完全对接后端 API 并能正确渲染。
- [ ] **WebSocket 断线重连**: 检查 `wsClient.js` 的健壮性，确保在网络波动或后端重启后能自动重连。
- [ ] **配置页面**: 完善 `Settings.vue`，允许用户在前端动态配置风控参数（如最大杠杆、单笔亏损限额等）。

#### 3. 测试与质量 (Testing & QA)
- [ ] **单元测试**: 为 `RiskControlService` 添加单元测试，覆盖各种边界条件（如：刚好达到最大持仓、杠杆计算等）。
- [ ] **集成测试**: 编写 API 集成测试，模拟从“同步持仓”到“触发风控”的全流程。
- [ ] **模拟脚本**: 完善 `scripts/` 目录下的测试脚本，使其能模拟生成大量订单或极端行情，测试系统的抗压能力。

#### 4. 部署与文档 (DevOps & Docs)
- [ ] **生产环境配置**: 优化 `docker-compose.yml` 或新建 `docker-compose.prod.yml`，配置 Nginx HTTPS 证书，关闭调试模式。
- [ ] **API 文档**: 虽然 FastAPI 自带 Swagger，但建议在 README 中补充核心风控逻辑的说明文档，方便团队成员理解。

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
