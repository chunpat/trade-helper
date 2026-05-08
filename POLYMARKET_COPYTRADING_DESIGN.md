# Polymarket 跟单与自动化交易设计

## 1. 目标与边界

目标不是做一个无约束的通用机器人，而是在现有风控监控系统中新增一套可审计、可限权、可随时停用的 Polymarket 跟单能力。

建议把功能边界拆成 4 层：

1. 交易员发现：展示候选交易员、基础画像、近期收益与活跃度。
2. 可跟单性分析：判断对方是否高频、是否更像机器人、是否具备足够流动性让我们复制。
3. 策略配置：选定要跟的交易员、资金比例、市场白名单、滑点与延迟阈值。
4. 自动执行：监听目标交易员行为，做风控校验后下单、撤单、减仓或跳过。

当前仓库在 [CLAUDE.md](CLAUDE.md) 中把产品定义为“监控和决策支持平台，不是自动交易机器人”。因此如果要落地自动跟单，建议用单独 feature flag 控制，例如：

- ENABLE_POLYMARKET_COPYTRADING
- ENABLE_POLYMARKET_LIVE_EXECUTION

默认应该只开“分析”和“模拟跟单”，实盘执行后置。

## 2. Polymarket API 能不能整合

可以，而且建议拆成两类接口使用。

### 2.1 公开数据接口，适合做交易员分析

Polymarket 官方文档已经提供公开的 Data API，可以直接支撑交易员筛选：

1. `https://data-api.polymarket.com/trades`
   用途：按钱包地址拉取成交记录，可带 `user`、`limit`、`offset`、`market`、`side`、`takerOnly` 等参数。
2. `https://data-api.polymarket.com/activity`
   用途：按钱包地址拉取链上活动，可过滤 `TRADE`、`SPLIT`、`MERGE`、`REDEEM`、`REWARD`、`CONVERSION`。
3. `https://data-api.polymarket.com/positions`
   用途：读取当前持仓，包含 `size`、`avgPrice`、`currentValue`、`cashPnl`、`percentPnl`、`curPrice` 等字段。
4. 官方文档索引里还提供 closed positions、leaderboard、profile、markets 等接口，可作为补充数据源。

这类接口足够做：

- 候选交易员榜单
- 活跃频率分析
- 当前持仓结构分析
- 历史行为标签化
- 跟单可行性初筛

### 2.2 交易接口，适合自动执行

Polymarket 的交易走 CLOB。官方建议优先使用 SDK，而不是手写 REST 签名。

执行链路要点：

1. 订单本身需要 EIP-712 签名。
2. 下单、撤单、查成交需要 L2 API credentials（API key、secret、passphrase）的 HMAC 认证。
3. 新用户建议使用 deposit wallet，签名类型通常走 `POLY_1271`。
4. 下单前必须做 geoblock 检查；被限制地区提交订单会被拒绝。

结论：

- `analytics/data api` 能用于“发现谁值得跟”。
- `clob trading api/sdk` 能用于“实际跟单执行”。
- 两者都能整合，而且应该分开实现，避免把读数据和下单强耦合在同一个服务里。

## 3. 关键限制

Polymarket 官方公开数据并不会直接告诉你“这个人胜率高，适合跟单”。有几个关键限制需要先讲清楚：

1. 没有现成的“可跟单评分”字段。
2. 对第三方钱包，公开接口拿不到完整的撤单历史，因此机器人识别不能依赖 cancel ratio 精确建模。
3. 高频地址即使历史收益高，也未必能复制，因为你看到的是链上已发生的结果，不是实时排队中的订单意图。
4. 预测市场不是永续合约，持仓对象是 outcome token，开平仓和兑现逻辑跟现有 futures 账户模型不同。
5. Polymarket 存在地理限制和合规约束，系统必须在执行前做 geoblock 检查。

所以这里最核心的不是“找收益最高的人”，而是“找收益稳定且能被复制的人”。

## 4. 建议的系统拆分

### 4.1 数据层

建议新增独立目录：

- `app/services/polymarket/data_client.py`
- `app/services/polymarket/clob_client.py`
- `app/services/polymarket/trader_analytics_service.py`
- `app/services/polymarket/followability_service.py`
- `app/services/polymarket/copy_trade_service.py`
- `app/services/polymarket/execution_service.py`
- `app/services/polymarket/reconciliation_service.py`

职责划分：

1. `data_client.py`
   只负责 Polymarket Data API 的公开查询。
2. `clob_client.py`
   只负责认证、签名、下单、撤单、查用户订单与成交。
3. `trader_analytics_service.py`
   负责交易员画像、频率、收益、市场偏好和人工/机器人特征判断。
4. `followability_service.py`
   负责计算“能不能跟”，核心是延迟、滑点、盘口深度、成交额门槛。
5. `copy_trade_service.py`
   负责把目标交易员行为转成跟单信号。
6. `execution_service.py`
   负责风险校验、下单参数生成、重试与幂等。
7. `reconciliation_service.py`
   负责实际持仓、订单状态、成交结果与目标信号对账。

### 4.2 账户与凭证层

现有账户模型在 [app/models/risk_control.py](app/models/risk_control.py) 主要适配中心化交易所 `api_key/api_secret/api_passphrase`。Polymarket 不适合把钱包签名信息硬塞到这几个字段里。

建议新增表而不是复用 `accounts.settings` 生塞：

- `polymarket_accounts`
- `polymarket_copy_strategies`
- `polymarket_trader_snapshots`
- `polymarket_trader_activities`
- `polymarket_copy_orders`
- `polymarket_copy_fills`

建议字段：

### `polymarket_accounts`

- `account_id`
- `wallet_address`
- `funder_address`
- `signature_type`
- `encrypted_private_key` 或外部 signer 引用
- `poly_api_key`
- `poly_api_secret`
- `poly_api_passphrase`
- `chain_id`，默认 137
- `is_geoblock_checked`
- `last_geoblock_result`
- `last_nonce`

说明：

- 不建议明文存私钥。
- 最好接 KMS、Vault，或者至少做应用层加密。
- 如果你后面希望支持手工签名或远程 signer，模型里要预留 `signer_mode`。

### 4.3 策略层

`polymarket_copy_strategies` 建议至少包含：

- `source_wallet`
- `strategy_name`
- `status`
- `allocation_mode`：固定金额 / 按比例 / 按上限
- `allocation_value`
- `max_order_usdc`
- `max_daily_loss`
- `max_open_positions`
- `max_slippage_bps`
- `max_signal_delay_seconds`
- `min_target_trade_usdc`
- `allowed_tags`
- `blocked_tags`
- `close_only`
- `dry_run`
- `skip_high_frequency`
- `skip_likely_bot`

## 5. 交易员筛选与评分

### 5.1 候选交易员数据来源

候选人来源建议三路合并：

1. Polymarket leaderboard / profile / public ranking 接口。
2. 你手工维护的钱包白名单。
3. 从高热度市场里反向扫描活跃大额地址。

### 5.2 基础画像指标

每个交易员至少计算以下字段：

- 最近 7 天、30 天成交笔数
- 最近 7 天、30 天成交金额
- 交易市场数
- 平均持仓时长
- 当前浮盈浮亏
- 已实现收益估算
- 胜率估算
- 平均单笔收益
- 最大回撤估算
- 市场集中度
- 单市场重复交易占比
- 买入后多久平仓
- 是否偏事件前抢跑

### 5.3 机器人/高频判别

你提到“如果高频是跟不上的，对方是机器人”。这个判断要单独做，不能只看收益。

建议用以下规则打标签：

1. 中位交易间隔小于阈值，例如 15 秒、30 秒、60 秒三个档位。
2. 同一市场连续小额多笔成交比例过高。
3. maker/taker 行为特征异常集中。
4. 多市场并发切换频率过高。
5. 成交规模很小但频率极高，更像做市或脚本扫单。
6. 事件前后秒级反应明显超出人工可复制范围。

输出不要只给一个分值，建议至少打三类标签：

- `HUMAN_LIKELY`
- `MIXED`
- `BOT_LIKELY`

### 5.4 跟单可行性评分

真正重要的是 `followability_score`。建议单独算，不要混进胜率分里。

评分可以由以下维度组成：

- 信号延迟容忍度
- 市场深度是否够大
- 成交金额是否足以覆盖 gasless / 手续费 / 滑点成本
- 该地址是否经常在盘口极薄时下单
- 对方平均成交价格与我们事后可拿到的盘口价差
- 对方是否经常分批成交导致复制成本过高

可以定义：

`总分 = 收益质量分 * 0.4 + 稳定性分 * 0.2 + 可跟单性分 * 0.4`

其中只要 `可跟单性分` 过低，就不允许进入自动执行名单。

## 6. 自动跟单执行流程

### 6.1 推荐流程

1. 拉取目标交易员最新 activity / trades。
2. 识别新增 `TRADE` 事件。
3. 做事件去重与顺序校正。
4. 把目标成交映射为内部信号：开仓、加仓、减仓、平仓。
5. 查询当前市场信息、token、tick size、盘口、mid price。
6. 运行本地风控：地理限制、市场白名单、单笔金额、滑点、延迟、仓位上限。
7. 生成跟单订单。
8. 通过 CLOB SDK 提交限价单。
9. 记录订单、成交、失败原因。
10. 持续对账，必要时补撤单、补减仓、人工接管。

### 6.2 为什么建议用“激进限价单”而不是盲目市价

Polymarket 的复制场景里，真正的问题不是能否下单，而是你看到对方成交时，价格往往已经变了。

所以更稳妥的执行方式是：

1. 根据目标成交方向读取当前 best bid / best ask。
2. 在允许滑点范围内生成一个 marketable limit order。
3. 如果预估价格偏差超过阈值，直接跳过，不追。

这样可以直接把“跟不上”的情况转成明确的风控跳过，而不是强行追单后把收益全交给滑点。

### 6.3 高频场景处理

如果目标地址满足以下任一条件，建议默认禁止自动跟单：

1. 最近 30 分钟成交笔数超过阈值。
2. 中位交易间隔过短。
3. 单笔目标金额过小。
4. 同一市场连续追价频率过高。

此时系统只做：

- 展示
- 标记为 `BOT_LIKELY` 或 `UNFOLLOWABLE`
- 允许人工观察
- 不允许自动执行

## 7. 和现有系统怎么接

### 7.1 后端扩展点

当前仓库已有交易所适配入口 [app/services/exchange/binance_adapter.py](app/services/exchange/binance_adapter.py)，并通过 `create_adapter_for_account` 分发。这个入口适合中心化交易所，但不适合直接承载 Polymarket 的钱包签名与 CLOB 客户端。

建议做法：

1. 保留现有 `exchange/` 目录给 Binance/OKX。
2. Polymarket 新建 `app/services/polymarket/` 子系统。
3. 由新的 API 路由统一调用，不强行塞进 `create_adapter_for_account`。

原因：

- Polymarket 不是普通的 API key 交易所。
- 需要 geoblock、钱包签名、token/outcome 模型、订单对账。
- 跟现有 futures `Position` 模型语义不同。

### 7.2 数据同步与持仓

现有持仓同步服务 [app/services/position_sync.py](app/services/position_sync.py) 面向中心化合约仓位。Polymarket 的 outcome token 持仓建议单独同步，不要直接复用现有 `positions` 表。

建议新增：

- `polymarket_positions`
- `polymarket_position_snapshots`

否则你会很快遇到这些语义冲突：

- `symbol` 对 outcome token 不够表达
- `LONG/SHORT` 不适用于 Yes/No outcome
- `liquidation_price` 在预测市场无意义
- `leverage` 也不是核心字段

### 7.3 风控融合

现有 [app/services/risk_control_service.py](app/services/risk_control_service.py) 偏向合约账户风控。Polymarket 跟单更需要以下约束：

- 最大总投入 USDC
- 单市场最大暴露
- 单事件最大暴露
- 同方向相关市场聚合暴露
- 最大可接受滑点
- 最大信号延迟
- 最大当日亏损
- 分辨率前禁止开仓
- close-only 模式

建议新增 `PolymarketRiskService`，不要硬改现有 futures 风控逻辑。

## 8. 前端设计

建议新增两页，而不是把所有逻辑塞进现有账户管理页 [frontend/src/views/Accounts.vue](frontend/src/views/Accounts.vue)。

### 8.1 交易员池页面

建议页面：`frontend/src/views/PolymarketTraders.vue`

核心模块：

1. 钱包地址搜索
2. 候选榜单
3. 交易频率分布
4. 收益/回撤/胜率卡片
5. 跟单可行性评分
6. 机器人标签
7. 最近成交时间轴
8. 当前持仓与市场偏好

### 8.2 跟单策略页面

建议页面：`frontend/src/views/PolymarketCopyStrategies.vue`

核心模块：

1. 选择目标交易员
2. 选择 dry-run / live
3. 资金分配规则
4. 市场白名单与黑名单
5. 滑点阈值
6. 延迟阈值
7. 高频跳过规则
8. 风险上限
9. 订单执行日志
10. 实盘/模拟收益对比

## 9. API 设计草案

建议新增路由文件：

- `app/api/v1/polymarket.py`

建议接口：

1. `POST /polymarket/accounts`
   新增 Polymarket 交易账户。
2. `POST /polymarket/accounts/{id}/geoblock-check`
   做地理限制检查。
3. `GET /polymarket/traders`
   查询候选交易员列表。
4. `GET /polymarket/traders/{wallet}`
   查询交易员画像。
5. `GET /polymarket/traders/{wallet}/activity`
   查询活动明细。
6. `GET /polymarket/traders/{wallet}/followability`
   查询可跟单评分和原因。
7. `POST /polymarket/strategies`
   创建跟单策略。
8. `POST /polymarket/strategies/{id}/simulate`
   回放历史做模拟跟单。
9. `POST /polymarket/strategies/{id}/start`
   启动实时跟单。
10. `POST /polymarket/strategies/{id}/stop`
    停止实时跟单。
11. `GET /polymarket/strategies/{id}/orders`
    查询策略订单日志。
12. `GET /polymarket/strategies/{id}/fills`
    查询策略成交日志。

## 10. 实时监听建议

V1 建议先用轮询，不要一开始就上全量 WebSocket。

原因：

1. 轮询更容易做幂等与补偿。
2. 交易员跟单的第一阶段重点是先判断“能不能复制”，不是追求最低延迟。
3. 你的系统当前已有定时轮询背景任务经验，落地成本低。

建议 V1：

- 每 3 到 5 秒轮询目标钱包最近活动
- 用 `last_seen_timestamp + transaction_hash` 去重
- 只监控少量已启用的策略

V2 再考虑接用户通道 / 市场通道做更低延迟执行。

## 11. 执行安全与幂等

自动跟单里最容易出事故的是重复执行。必须从一开始就做幂等键。

建议幂等键：

- `strategy_id + source_wallet + source_tx_hash + source_asset + source_side + source_timestamp_bucket`

同时记录：

- 源交易事件
- 是否已转内部信号
- 是否已提交订单
- 订单 hash
- 最终成交结果
- 放弃原因

## 12. MVP 实施顺序

建议分三期，不建议一步到位上实盘。

### 第一期：只做分析和筛选

目标：证明官方公开 API 足够支撑交易员画像。

交付：

1. Polymarket trader 列表页
2. 单交易员分析页
3. 胜率、频率、机器人概率、可跟单评分
4. 数据入库和定时刷新

### 第二期：做模拟跟单

目标：证明“历史上看起来厉害的人”在现实里是否跟得上。

交付：

1. 历史 activity 回放
2. 按当时盘口或近似价格做模拟成交
3. 统计模拟收益、滑点、漏跟率
4. 产出 `followability_score`

### 第三期：小额实盘

目标：验证端到端自动执行稳定性。

交付：

1. geoblock 检查
2. 小额 live 策略
3. 下单与撤单
4. 对账与告警
5. 手动熔断与 close-only

## 13. 我的建议结论

结论很明确：

1. Polymarket 官方 API 能接，而且足够支撑“交易员发现 + 活跃分析 + 跟单可行性分析”。
2. 真正困难点不在 API 可用性，而在“高收益地址是否可复制”。
3. 你的产品应该先做“可跟单性评分 + 模拟跟单”，再上自动执行。
4. Polymarket 不建议硬塞进现有 Binance/OKX adapter；应该新建独立 `polymarket` 子系统。
5. 自动执行一定要从小额、白名单、dry-run、强风控、可熔断开始。

如果进入实现阶段，我建议第一批先做：

1. 后端 `data_client + trader_analytics_service`
2. 新增 `polymarket` API 路由
3. 前端交易员分析页
4. 历史模拟跟单

这四块完成后，再决定要不要接入真实下单。