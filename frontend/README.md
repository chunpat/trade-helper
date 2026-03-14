# 数字货币合约交易风控系统前端

这是项目的 Vue 3 前端部分，负责展示市场洞察、账户管理、仓位监控、异常事件和风控配置。

## 技术栈

- Vue 3
- Vuex 4
- Vue Router 4
- Element Plus
- ECharts
- Axios
- Vite

## 开发环境要求

- Node.js >= 14
- npm >= 6.14.0

## 快速开始

安装依赖并启动开发环境：

```bash
npm install
npm run dev
```

默认开发地址：

- http://localhost:3000

构建生产包：

```bash
npm run build
```

本地预览构建结果：

```bash
npm run preview
```

代码检查：

```bash
npm run lint
```

## 开发代理说明

- Vite 开发服务器默认监听 3000 端口
- `/api` 请求会代理到 `http://localhost:8029`
- 代理层会去掉请求前缀 `/api`
- 如果后端端口变了，需要同步修改 `vite.config.js`

## 目录结构

```text
frontend/
├── src/
│   ├── api/            # API 请求封装
│   ├── components/     # 通用组件
│   ├── router/         # 路由配置
│   ├── services/       # WebSocket 等服务封装
│   ├── store/          # Vuex 状态管理
│   ├── views/          # 页面视图
│   ├── App.vue         # 根组件
│   └── main.js         # 应用入口
├── index.html          # HTML 模板
├── nginx.conf          # 生产环境 Nginx 配置
├── vite.config.js      # Vite 配置
└── package.json        # 前端依赖与脚本
```

## 主要页面

### Dashboard

- 市场总览、仓位概览、风险统计
- 异常事件与相关新闻展示
- 市场情绪、排行榜和图表可视化

### Accounts

- 账户列表
- 账户新增、编辑、删除
- 账户启停状态切换
- 账户连通性测试

### Positions

- 实时持仓列表
- 风险评估
- 强平价格相关数据展示

### Risk Alerts

- 风险告警列表
- 告警详情
- 历史预警记录查看

### Settings

- 风控参数管理
- 前端基础配置入口

## 开发约定

### API 调用

- API 封装统一放在 `src/api`
- 所有请求都通过同一个 Axios 实例发出
- 新接口优先和现有模块风格保持一致

示例：

```javascript
import { riskControl } from '@/api'

const accounts = await riskControl.getAccounts()
const result = await riskControl.testAccountConnectivity(accountId)
```

### 状态管理

当前主要模块包括：

- accounts
- positions
- alerts
- riskConfigs

### 路由

- 路由配置位于 `src/router/index.js`
- 页面组件默认使用懒加载

### 组件与样式

- 组件文件名使用 PascalCase
- Props 使用 camelCase，并显式声明类型
- 自定义事件名使用 kebab-case
- 优先复用 Element Plus 样式和组件能力

## 部署

### 静态部署

```bash
npm run build
```

构建产物输出到 `dist` 目录，可部署到任意静态文件服务器。

### Docker

```bash
docker build -t trade-helper-frontend .
docker run -d -p 8030:80 trade-helper-frontend
```

### 与后端联调

本地联调时，通常对应下面两种方式：

- 后端容器模式：前端访问 `http://localhost:8029`
- 后端本地模式：需要同步调整 `vite.config.js` 中的代理目标

## 注意事项

- 不要在前端代码中直接保存真实 API Key 或 Secret
- 大数据量表格要优先考虑分页和渲染性能
- WebSocket 或定时器在组件销毁时要及时清理
- 新增接口时要补基础错误处理，避免页面静默失败
