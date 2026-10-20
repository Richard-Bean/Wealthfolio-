# 数据模型

所有 Connector 必须先输出统一模型，不能直接生成 Wealthfolio CSV。

## 三类记录

```text
Transaction       一笔真实发生的交易
PositionSnapshot  某个时间点的持仓
BalanceSnapshot   某个时间点的账户余额
```

禁止把不同日期的持仓快照直接当作两笔交易。

## 共同溯源字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `recordType` | enum | 是 | `transaction` / `positionSnapshot` / `balanceSnapshot` |
| `source` | string | 是 | `alipay` / `broker` / `bank` / `payment` 等 |
| `sourceRecordId` | string | 否 | 来源提供的稳定记录 ID |
| `sourceFile` | string | 否 | 原始账单或截图文件 |
| `sourceFileHash` | string | 否 | 原始文件 hash，用于批次追踪 |
| `sourceLocator` | string | 否 | 页码、表格行、OCR 行等定位 |
| `confidence` | decimal | 否 | 解析置信度；低置信度进入人工复核 |
| `importedAt` | datetime | 是 | 进入本系统的时间 |

## Transaction

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `transactionId` | string | 是 | 来源 ID 或稳定指纹 |
| `tradeDate` | date | 是 | 实际交易日期 |
| `settlementDate` | date | 否 | 入账或确认日期 |
| `account` | string | 是 | 账户名称 |
| `activityType` | enum | 是 | `BUY` / `SELL` / `DIVIDEND` / `DEPOSIT` / `WITHDRAWAL` 等 |
| `symbol` | string | 否 | 证券或基金代码 |
| `isin` | string | 否 | ISIN |
| `quantity` | decimal | 否 | 数量或份额 |
| `unitPrice` | decimal | 否 | 单价 |
| `amount` | decimal | 是 | 金额 |
| `currency` | string | 是 | `CNY` / `USD` 等 |
| `fee` | decimal | 否 | 手续费 |
| `tax` | decimal | 否 | 税费 |
| `counterparty` | string | 否 | 对手方或摘要 |
| `comment` | string | 否 | 备注 |
| `fxRate` | decimal | 否 | 汇率 |

## PositionSnapshot

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `snapshotId` | string | 是 | 账户、日期、标的和来源组成的稳定标识 |
| `snapshotDate` | date | 是 | 持仓观察日期 |
| `account` | string | 是 | 账户名称 |
| `symbol` | string | 是 | 证券或基金代码 |
| `quantity` | decimal | 否 | 已确认份额 |
| `marketValue` | decimal | 是 | 截图或账单中的持有金额 |
| `costBasis` | decimal | 否 | 持仓总成本 |
| `averageCost` | decimal | 否 | 每份平均成本 |
| `valuationDate` | date | 否 | 使用的净值或价格日期 |

## BalanceSnapshot

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `snapshotId` | string | 是 | 账户、日期和来源组成的稳定标识 |
| `snapshotDate` | date | 是 | 余额观察日期 |
| `account` | string | 是 | 账户名称 |
| `balance` | decimal | 是 | 账户余额 |
| `currency` | string | 是 | 币种 |

## 快照到交易的语义

- 首次快照：只生成一次 `INITIAL_SNAPSHOT` 基线买入。
- 后续份额不变：不生成交易。
- 后续份额和成本可靠增加：生成差额买入。
- 份额减少或持仓消失：需要来源交易、对账单或人工确认后才能生成卖出。
- 乱序旧快照：标记 `STALE_SNAPSHOT`，不生成交易。
- 无法可靠推断：进入 `manual_review`。

## OCR 和派生字段

OCR 结果必须保留原始证据，包括：

- 原始 OCR 利润和累计收益；
- 原始截图收益率；
- 使用的修复来源；
- 模板识别结果和置信度；
- 来源图片；
- 校验错误和警告。

字段可信级别：

```text
source_fact       来源文件直接提供的事实
corroborated      两个以上独立字段交叉验证
derived           由公式或规则推导
uncertain         低置信度或存在冲突
manual_review     必须由用户确认
```

## 校验关系

至少检查：

- 持仓成本 × 份额与成本总额的关系；
- 持有金额 - 持仓成本与持有收益的关系；
- 持有收益 / 成本与持有收益率的关系；
- 份额 × 单位净值与持有金额的关系；
- 同一行“持有收益”和“累计收益”的一致性；
- 交易截止时间和适用净值日期；
- 来源、账户、币种和基金代码的一致性。

严重错误阻止导出；仅口径差异且收益金额一致时，可以记录警告后继续。

## 输出约束

- 不允许 Connector 直接输出 Wealthfolio CSV。
- 不允许丢失原始来源定位。
- 不允许用模糊名称跨基金公司、份额类别或币种合并。
- 不允许在缺少稳定 ID 时宣称已经可靠去重。
