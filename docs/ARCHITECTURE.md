# 系统架构

## 目标

系统把用户主动导出的金融数据或受监督截图，转换为标准化、可校验、可追溯、可去重的 Wealthfolio 导入数据。

## 架构原则

1. 本地优先。
2. 用户官方导出文件优先。
3. OCR 只是补充。
4. AI 不作为关键金额的唯一依据。
5. 不绕过安全机制。
6. 幂等运行。
7. 保存 Raw、Normalized、Export 三层数据。
8. 失败不覆盖成功结果。

## 总体数据流

```text
用户官方文件 / 受监督截图
        ↓
Connector（discover / parse / normalize）
        ↓
Raw Storage
        ↓
统一记录模型
        ↓
Validator
        ↓
Deduplicator / Snapshot Reconciler
        ↓
Wealthfolio Exporter
        ↓
CSV / 导入报告 / 人工复核清单
```

公开基金净值等市场数据只用于估值，不能替代用户账户的持仓和交易来源。

## 当前实现目录

```text
Wealthfolio中国金融同步连接器架构设计/
├── AGENTS.md
├── STATUS.md
├── README.md
├── docs/
├── FinanceBot/
│   ├── agent/
│   ├── config/
│   ├── connectors/
│   │   ├── alipay/
│   │   └── wealthfolio/
│   ├── core/
│   │   ├── market_data/
│   │   ├── normalizer/
│   │   ├── parser/
│   │   └── pipeline/
│   ├── data/
│   │   ├── raw/
│   │   ├── processed/
│   │   └── export/
│   ├── scripts/
│   └── tests/
└── 运行截图转CSV.bat
```

## FinanceMasterAgent 状态机

```text
INIT
→ CHECK_ENVIRONMENT
→ CHECK_LOGIN（仅浏览器辅助路径）
→ COLLECT
→ SAVE_RAW
→ NORMALIZE
→ VALIDATE
→ DEDUPLICATE
→ RECONCILE
→ EXPORT
→ REPORT
→ DONE
```

失败时进入：

```text
HUMAN_REVIEW / RETRY / ABORT
```

不得从失败阶段直接覆盖上一次成功结果。

## 模块职责

### Connector

识别来源、账户、文件类型和批次；把原始文件解析为来源记录并标准化。Connector 不负责最终 Wealthfolio 导出。

### Normalizer

统一字段、单位、日期和记录类型，区分真实交易、持仓快照和余额快照。

### Validator

校验金额、份额、成本、收益率、净值、日期和来源一致性；低置信度或严重冲突进入人工复核。

### Deduplicator / Snapshot Reconciler

根据稳定 ID、来源 hash、时间和业务语义去重；快照只在可靠差额下推断交易。

### Exporter

只消费已经校验和对账的统一记录，生成 Wealthfolio CSV 和导入报告。

## Context Engineering 分层

```text
Stable Context：AGENTS.md、docs/*
Task Context：当前任务和所需模块
State Context：STATUS.md、上次成功快照、当前 pending
Evidence Context：来源文件、OCR 原始值、置信度、校验结果
```

每次运行应生成 Context Manifest，使输入、配置、状态、输出和人工复核项可以重放和审计。

## 设计决策

本文件保存已经稳定的设计决策及理由。当前执行进度见 `STATUS.md`。

### ADR-001：文件优先，不依赖个人账户 API

状态：已采纳。

#### 决策

支付宝、银行和券商的用户官方导出文件是主数据入口。个人账户 API 不作为项目前置条件。

#### 理由

- 开放接口主要面向商户、企业、收单、清算或持牌合作方；
- 个人账户认证依赖密码、短信、设备和安全控件；
- 交易或量化接口不保证完整历史账单；
- 网页 DOM 和私有接口不稳定；
- 保存凭据、绕过验证码或规避风控不可接受。

#### 影响

所有 Connector 必须支持 CSV、Excel、PDF、对账单或交割单。浏览器自动化只能作为用户监督下的辅助下载。

### ADR-002：AI 和 OCR 不作为关键金额的唯一依据

状态：已采纳。

#### 决策

AI、OCR 或模糊匹配产生的关键字段必须经过规则、交叉字段或人工确认。

#### 影响

- 保存 OCR 原始值；
- 使用“持有收益”和“累计收益”交叉校验；
- 严重不一致阻止导出；
- 歧义映射进入 `pending_mapping_rows`；
- 低置信度进入人工复核。

### ADR-003：区分交易和快照

状态：已采纳，正式链路仍在实施。

#### 决策

`Transaction`、`PositionSnapshot`、`BalanceSnapshot` 是不同记录类型。持仓快照不能直接当作交易。

#### 理由

不同时间点的持仓变化可能是买入、卖出、分红、净值变化、费用或口径差异。直接写入完整持仓会产生重复买入。

#### 影响

- 首次快照只建立一次基线；
- 后续只在可靠差额下推断交易；
- 乱序快照标记 `STALE_SNAPSHOT`；
- 无法推断的减少进入人工复核。

### ADR-004：可追溯、幂等、失败隔离

状态：已采纳，统一实现仍在进行。

#### 决策

每条数据保留来源、定位、hash、置信度和导入时间。重复执行不能产生重复交易。失败不得覆盖上一次成功产物。

#### 影响

- 建立稳定 `sourceRecordId` / `transactionId`；
- 临时文件加原子替换；
- 生成运行报告；
- 后续增加 Context Manifest；
- 测试覆盖重复运行和失败恢复。

### ADR-005：本地优先和离线缓存

状态：已采纳。

#### 决策

财务原始数据尽量保存在本机。基金名称映射和净值使用本地缓存，网络失败时可降级。

#### 影响

- 映射结果保存到本地映射表；
- 净值默认使用本地缓存；
- 只有显式联网模式才调用公开接口；
- 不把用户财务数据上传到第三方。

### ADR-006：模糊映射必须受业务约束

状态：已采纳。

#### 决策

名称相似度不能单独决定基金代码，必须同时约束基金公司、A/C 份额类别和币种。

#### 理由

旧实现曾因低阈值模糊匹配把不同基金公司映射到同一代码，导致错误合并和删除。

#### 影响

- 本地匹配阈值提高到 `0.88`；
- 候选需满足公司、份额类别和币种兼容；
- 歧义候选保留人工复核；
- 同代码金额冲突全部保留并报告。

### ADR-007：上下文按稳定性和任务路由

状态：已采纳。

#### 决策

- `AGENTS.md` 保存稳定规则和路由；
- `STATUS.md` 保存动态状态；
- `docs/` 保存稳定详细设计；
- `TROUBLESHOOTING.md` 保存案例；
- 运行证据由结构化 manifest 保存。

#### 影响

Agent 不需要读取所有历史文档，而按当前任务加载最小充分上下文。敏感原始数据不进入模型上下文。
