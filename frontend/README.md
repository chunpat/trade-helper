# 数字货币合约交易风控系统 - 前端

## 技术栈

- Vue 3
- Vuex 4
- Vue Router 4
- Element Plus
- ECharts
- Axios
- Vite

## 开发环境要求

- Node.js >= 14.0.0
- npm >= 6.14.0

## 项目设置

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run serve

# 构建生产版本
npm run build

# 代码格式化
npm run lint
```

## 目录结构

```
frontend/
├── src/
│   ├── api/            # API请求
│   ├── assets/         # 静态资源
│   ├── components/     # 通用组件
│   ├── router/         # 路由配置
│   ├── store/          # Vuex状态管理
│   ├── views/          # 页面视图
│   ├── App.vue         # 根组件
│   └── main.js         # 应用入口
├── public/             # 公共资源
├── index.html          # HTML模板
├── vite.config.js      # Vite配置
└── package.json        # 项目依赖
```

## 主要功能模块

### 1. 仪表盘 (Dashboard)
- 总持仓价值监控
- 风险预警统计
- 实时盈亏展示
- 账户状态概览
- 持仓分布图表
- 风险分布饼图

### 2. 账户管理
- 账户列表
- 账户添加/编辑
- API密钥管理
- 风控参数配置

### 3. 持仓监控
- 实时持仓列表
- 持仓风险评估
- 强平价格预警
- 持仓操作记录

### 4. 风险预警
- 实时预警列表
- 预警详情查看
- 预警处理流程
- 历史预警记录

### 5. 风控配置
- 风控规则设置
- 预警阈值配置
- 风控参数管理
- 配置模板管理

## 开发指南

### API调用
API请求统一通过 `src/api` 目录下的模块进行管理。示例：

```javascript
import { riskControl } from '@/api'

// 获取账户列表
const accounts = await riskControl.getAccounts()

// 创建风险预警
const alert = await riskControl.createRiskAlert(alertData)
```

### 状态管理
使用Vuex进行状态管理，主要模块包括：

- accounts: 账户管理
- positions: 持仓管理
- alerts: 风险预警
- riskConfigs: 风控配置

### 路由配置
路由配置位于 `src/router/index.js`，采用懒加载方式：

```javascript
{
  path: '/dashboard',
  name: 'Dashboard',
  component: () => import('@/views/Dashboard.vue')
}
```

### 组件开发规范

1. 文件命名：使用PascalCase
2. 组件名称：使用PascalCase
3. Props定义：使用camelCase，必须声明类型
4. 事件命名：使用kebab-case

### 样式指南

1. 使用SCSS预处理器
2. BEM命名规范
3. 优先使用Element Plus组件库样式
4. 自定义主题配置

## 部署

### 测试环境
```bash
npm run build:stage
```

### 生产环境
```bash
npm run build
```

构建产物将生成在 `dist` 目录下，可以部署到任何静态文件服务器。

### Docker部署
```bash
# 构建镜像
docker build -t trade-helper-frontend .

# 运行容器
docker run -d -p 80:80 trade-helper-frontend
```

## 性能优化

1. 路由懒加载
2. 组件按需导入
3. 生产环境代码分割
4. 图片资源优化
5. 缓存策略实现

## 注意事项

1. 敏感信息（如API密钥）不要直接存储在前端代码中
2. 所有API请求需要进行错误处理
3. 大数据量的表格需要实现分页
4. 定时任务需要在组件销毁时清理
5. 及时更新依赖包的安全补丁
