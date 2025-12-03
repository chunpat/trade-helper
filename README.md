# 数字货币合约交易风控系统

一个基于Python和Vue.js的完整的数字货币合约交易风险管控系统，提供实时监控、风险预警、资金管理等功能。

## 系统架构

### 后端技术栈

- **Web框架**: FastAPI
- **数据库**: MySQL
- **消息队列**: Redis PubSub
- **缓存系统**: Redis
- **监控系统**: Prometheus + Grafana
- **日志系统**: ELK Stack

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

## 开发计划

### 基础版本 (v1.0)
- [x] 基础API集成
- [x] 简单资金和仓位控制
- [x] 基础监控和告警功能
- [x] 前端管理界面

### 进阶版本 (v2.0)
- [ ] 高级风控策略
- [ ] 性能优化
- [ ] 机器学习风险预测
- [ ] 完善的监控和告警系统
- [ ] 移动端适配

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
