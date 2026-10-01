# Personal Finance Agent 项目设计文档 V2

> 本文基于第一版 `wealthfolio_connection.md` 修改。
>
> **核心变化：** Finance Agent 不再把 Wealthfolio CSV 当作主数据结果，而是以 SQLite 作为标准化后的主数据层；Wealthfolio 变成下游消费者，并通过 `Wealthfolio Adapter` 连接。
>
> 文中使用 `【相比第一版的修改】` 标记的地方，是相对于第一版的重要架构变化。

---

# 1. 项目目标

构建一个本地优先（Local-First）的个人财富自动化系统，将支付宝、银行、券商等账户中的持仓、交易流水和余额自动采集，经过标准化、校验和去重后，保存为统一的本地标准数据，并提供 Wealthfolio 导出/连接能力。

目标流程：

```text
金融平台
   ↓
RPA / API / CSV / DOM / OCR
   ↓
原始数据 Raw Data
   ↓
数据标准化 Normalizer
   ↓
数据校验 Validator
   ↓
去重 Deduplicator
   ↓
Canonical Database（SQLite）
   ↓
Wealthfolio Adapter
   ├── V1：CSV Export
   └── V2：直接连接/自动同步（待根据 Wealthfolio 实际接口实现）
   ↓
Wealthfolio
```

【相比第一版的修改】

第一版的主要目标是：

```text
金融平台 → 标准化 → CSV → Wealthfolio
```

V2 将其修改为：

```text
金融平台 → 标准化 → SQLite → Wealthfolio Adapter → Wealthfolio
```

**原因：**

CSV 更适合作为数据交换格式，而不应该成为整个 Finance Agent 的主数据层。

这样可以避免以后 Wealthfolio 的 CSV 格式、导入方式或接口发生变化时，重新开发支付宝、银行、券商 Connector。

---

# 2. 核心设计原则

1. **本地优先**：浏览器登录状态、财务原始数据尽量保存在本机。
2. **结构化数据优先**：优先使用官方 API、官方导出、页面 DOM 或结构化网络响应。
3. **OCR 作为备用**：只有无法直接读取结构化数据时才使用 OCR。
4. **AI 不作为关键金额的唯一依据**：金额、数量、日期等关键字段必须经过规则校验。
5. **不绕过安全机制**：验证码、二次认证、风控提示由人工处理。
6. **幂等运行**：重复执行不能产生重复交易。
7. **可追溯**：保存 Raw、Normalized 和 Export/Adapter 数据链路。
8. **失败不覆盖成功结果**：本次同步失败不能破坏上一次成功的数据。
9. **Canonical Database 优先**：SQLite 是 Finance Agent 的标准化主数据层；CSV 是下游交换格式。
10. **Wealthfolio 解耦**：采集系统不直接依赖 Wealthfolio 的内部实现。
11. **Adapter 隔离变化**：Wealthfolio 的字段映射、导入方式或未来 API 接入集中在 Adapter 层处理。

【相比第一版的修改】

新增：

```text
Canonical Database
Wealthfolio Adapter
```

并明确：

```text
SQLite = 主数据
CSV = 交换格式
Wealthfolio = 下游消费者
```

**原因：**

这样可以让 Finance Agent 独立运行，也可以未来连接其他投资组合软件，而不会被 Wealthfolio 的内部实现绑定。

---

# 3. 系统架构

```text
                         ┌──────────────────┐
                         │ Scheduler        │
                         │ 定时调度器        │
                         └────────┬─────────┘
                                  ↓
                       ┌────────────────────┐
                       │ FinanceMasterAgent │
                       └─────────┬──────────┘
                                 ↓
          ┌──────────────────────┼──────────────────────┐
          ↓                      ↓                      ↓
   ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
   │ Alipay       │       │ Bank         │       │ Broker       │
   │ Connector    │       │ Connector    │       │ Connector    │
   └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
          ↓                      ↓                      ↓
     API/DOM/OCR            API/CSV/DOM            API/CSV/DOM
          └──────────────────────┼──────────────────────┘
                                 ↓
                          ┌──────────────┐
                          │ Raw Storage  │
                          └──────┬───────┘
                                 ↓
                          ┌──────────────┐
                          │ Normalizer   │
                          └──────┬───────┘
                                 ↓
                          ┌──────────────┐
                          │ Validator    │
                          └──────┬───────┘
                                 ↓
                         ┌────────────────┐
                         │ Deduplicator   │
                         └───────┬────────┘
                                 ↓
                    ┌────────────────────────┐
                    │ Canonical Database     │
                    │ SQLite                 │
                    └───────────┬────────────┘
                                ↓
                    ┌────────────────────────┐
                    │ Wealthfolio Adapter    │
                    └───────────┬────────────┘
                                ↓
                    ┌────────────────────────┐
                    │ Wealthfolio            │
                    └────────────────────────┘
```

---

# 4. 项目目录

```text
finance-agent/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_SCHEMA.md
│   ├── CONNECTOR_SPEC.md
│   ├── SECURITY.md
│   ├── WEALTHFOLIO_ADAPTER.md
│   └── ROADMAP.md
│
├── src/
│   └── finance_agent/
│       ├── agent/
│       │   └── finance_master.py
│       │
│       ├── connectors/
│       │   ├── base.py
│       │   ├── alipay.py
│       │   ├── bank.py
│       │   └── broker.py
│       │
│       ├── browser/
│       │   └── session.py
│       │
│       ├── ocr/
│       │   └── paddleocr_engine.py
│       │
│       ├── normalizer/
│       │   └── transaction.py
│       │
│       ├── validators/
│       │   └── transaction.py
│       │
│       ├── storage/
│       │   ├── raw.py
│       │   └── sqlite.py
│       │
│       ├── mapping/
│       │   └── securities.py
│       │
│       └── wealthfolio/
│           ├── models.py
│           ├── mapper.py
│           ├── exporter.py
│           └── adapter.py
│
├── tests/
├── config/
├── browser/
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── export/
│   └── finance.sqlite
└── logs/
```

【相比第一版的修改】

第一版：

```text
wealthfolio/
└── exporter.py
```

V2：

```text
wealthfolio/
├── models.py
├── mapper.py
├── exporter.py
└── adapter.py
```

**原因：**

把 Wealthfolio 相关逻辑集中在一个独立边界内：

- `models.py`：描述 Wealthfolio 侧需要的数据结构。
- `mapper.py`：负责 Finance Agent → Wealthfolio 字段映射。
- `exporter.py`：负责 V1 CSV 导出。
- `adapter.py`：为未来 V2 自动连接预留接口。

---

# 5. FinanceMasterAgent

## 状态机

```text
INIT
 ↓
CHECK_ENVIRONMENT
 ↓
CHECK_LOGIN
 ↓
COLLECT
 ↓
SAVE_RAW
 ↓
NORMALIZE
 ↓
VALIDATE
 ↓
DEDUPLICATE
 ↓
SAVE_CANONICAL
 ↓
EXPORT / ADAPT
 ↓
REPORT
 ↓
DONE
```

## 主要职责

- 调度账户 Connector
- 检查登录状态
- 收集数据
- 保存原始数据
- 标准化
- 校验
- 去重
- 保存 Canonical Database
- 调用 Wealthfolio Adapter
- 生成 Wealthfolio CSV（V1）
- 输出运行报告

【相比第一版的修改】

新增：

```text
SAVE_CANONICAL
```

并把：

```text
EXPORT
```

改为：

```text
EXPORT / ADAPT
```

**原因：**

标准化数据首先必须进入 SQLite，然后才决定以 CSV、API 或其他方式交给 Wealthfolio。

---

# 6. Connector 规范

每一个金融平台独立实现 Connector。

```python
class Connector:

    def login_status(self) -> bool:
        ...

    def login_interactive(self) -> None:
        ...

    def collect_holdings(self):
        ...

    def collect_transactions(self):
        ...

    def collect_balance(self):
        ...
```

## 支付宝 Connector 第一阶段

第一版只实现：

- 基金持仓
- 基金交易记录

后续再加入：

- 余额
- 余额宝
- 其他财富产品

Connector 只负责：

```text
金融平台
   ↓
采集原始数据
```

不负责：

```text
Wealthfolio 字段映射
CSV 生成
Wealthfolio 数据写入
```

【相比第一版的修改】

明确 Connector 与 Wealthfolio 解耦。

**原因：**

Connector 的任务是“获取数据”，而不是“决定数据最终如何被 Wealthfolio 使用”。这样以后增加银行或券商时，不需要复制 Wealthfolio 相关代码。

---

# 7. 登录状态设计

首次运行：

```text
启动独立浏览器 Profile
        ↓
用户人工登录
        ↓
完成验证码 / 二次认证
        ↓
保存 Browser Profile
```

后续运行：

```text
启动 Browser Profile
        ↓
检查登录状态
        ↓
成功 → 继续
失败 → 停止 → 通知人工重新认证
```

## 安全要求

禁止：

- 把密码硬编码到代码
- 自动破解验证码
- 绕过风控
- 上传 Cookie / Session 到第三方服务

Browser Profile 属于敏感数据，应加入 `.gitignore`。

---

# 8. 数据获取优先级

```text
1. 官方 API / 官方导出
        ↓
2. 页面 DOM
        ↓
3. 页面结构化网络响应
        ↓
4. OCR
        ↓
5. AI 辅助解析
```

OCR 输出必须经过数据规则校验。

例如：

```text
OCR:
金额 = 889.77

↓

规则校验:
数量 × 单价 ≈ 金额

↓

通过 → 保存
失败 → 人工复核
```

---

# 9. 统一交易数据模型

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| date | date | 是 | 交易日期 |
| account | string | 是 | 账户名称 |
| source | string | 是 | 数据来源，如 alipay / bank / broker |
| sourceTransactionId | string | 否 | 来源平台原始交易 ID |
| activityType | enum | 是 | BUY / SELL / DIVIDEND 等 |
| symbol | string | 是 | 证券/基金代码 |
| isin | string | 否 | ISIN |
| quantity | decimal | 是 | 数量/份额 |
| unitPrice | decimal | 是 | 单价 |
| amount | decimal | 是 | 金额 |
| currency | string | 是 | CNY / USD 等 |
| fee | decimal | 否 | 手续费 |
| tax | decimal | 否 | 税费 |
| comment | string | 否 | 备注 |
| fxRate | decimal | 否 | 汇率 |

中国基金代码必须作为字符串保存：

```text
270023
270042
021778
012364
```

禁止自动转换成整数，以免丢失前导零。

【相比第一版的修改】

新增：

```text
source
sourceTransactionId
```

**原因：**

如果支付宝、券商等平台提供自己的交易 ID，应该优先保存原始交易 ID。没有原始 ID 时，再使用字段组合生成 Hash。

这样比单纯依赖：

```text
account + date + activityType + symbol + quantity + amount
```

更加可靠。

---

# 10. Canonical Database

SQLite 是 Finance Agent 的标准化主数据层。

建议至少保存：

```text
transactions
accounts
securities
source_records
sync_runs
mapping_queue
```

其中：

```text
transactions
```

保存经过标准化和验证后的统一交易数据。

```text
source_records
```

保存来源平台的原始记录标识，用于追溯。

```text
sync_runs
```

记录每一次同步：

```text
run_id
start_time
end_time
account
status
records_collected
records_validated
records_inserted
records_skipped
records_review_required
error_count
```

【相比第一版的修改】

第一版虽然已经规划 SQLite，但主要把它作为存储组件；V2 明确将 SQLite 定义为：

> **Canonical Database / 主数据层**

**原因：**

这是整个架构最重要的变化。

以后：

```text
支付宝 → SQLite
银行 → SQLite
券商 → SQLite
```

然后：

```text
SQLite → Wealthfolio
SQLite → 其他分析工具
SQLite → 自己的 Dashboard
```

所有下游系统共享同一份经过验证的数据。

---

# 11. Security / Fund Mapping

由于 Wealthfolio 可能无法自动识别中国公募基金，因此维护证券映射表：

```json
{
  "270023": {
    "name": "广发全球精选股票",
    "type": "fund",
    "currency": "CNY"
  },
  "270042": {
    "name": "示例基金",
    "type": "fund",
    "currency": "CNY"
  }
}
```

建议将原来的 `Fund Mapping` 扩展为：

```text
Security Mapping
```

因为未来不只处理基金，也可能处理：

- 股票
- ETF
- 债券
- 货币基金
- 其他证券

未知证券进入：

```text
Mapping Queue
```

由用户确认后加入映射表。

【相比第一版的修改】

```text
Fund Mapping
```

升级为：

```text
Security Mapping
```

**原因：**

当前支付宝阶段主要处理基金，但整个项目最终还包括券商和银行，因此映射层不应该从架构上限制为“基金”。

---

# 12. 去重

每一笔交易生成稳定指纹。

优先级：

```text
如果存在 sourceTransactionId：

source
+
sourceTransactionId
```

否则：

```text
source
+
account
+
date
+
activityType
+
symbol
+
quantity
+
amount
```

计算：

```text
transaction_id
```

例如：

```text
alipay|广发基金|2026-09-28|BUY|270023|137.04|889.77
```

计算 Hash。

数据库中已存在相同 ID 时：

```text
SKIP
```

避免重复导入。

---

# 13. Wealthfolio Adapter

## 13.1 Adapter 的职责

Wealthfolio Adapter 负责：

```text
Canonical Database
        ↓
Wealthfolio 数据模型
        ↓
字段映射
        ↓
导出 / 自动同步
```

Adapter 不负责：

- 登录支付宝
- OCR
- 抓取金融平台
- 修改原始数据
- 绕过平台安全机制

---

## 13.2 V1：CSV Adapter

第一阶段使用：

```text
SQLite
 ↓
Wealthfolio Mapper
 ↓
CSV Exporter
 ↓
wealthfolio_default_import.csv
 ↓
Wealthfolio 手动导入
```

目标文件：

```text
wealthfolio_default_import.csv
```

示例：

```csv
date,account,activityType,symbol,quantity,unitPrice,amount,currency,fee,tax,comment
2026-09-28,广发基金,BUY,270023,137.04,6.4928,889.77,CNY,0,0,支付宝基金
```

导出前必须完成：

- 字段完整性检查
- 数值检查
- 日期检查
- 证券代码检查
- 重复交易检查
- 币种检查
- Wealthfolio 字段映射检查

---

## 13.3 V2：自动连接 Wealthfolio

目标：

```text
SQLite
   ↓
Wealthfolio Adapter
   ↓
Wealthfolio
```

具体实现方式暂不写死。

开发前必须确认当前 Wealthfolio 版本实际支持的：

- 数据模型
- Import API
- Extension / Plugin API
- 本地 API
- 数据库结构
- 自动导入能力

只有确认实际接口后，才实现 `adapter.py`。

**禁止 Coding Agent 根据猜测直接修改 Wealthfolio 数据库。**

【相比第一版的修改】

第一版主要只有：

```text
CSV Exporter
```

V2 增加：

```text
Wealthfolio Adapter
```

并明确分为：

```text
V1 = CSV
V2 = 自动连接
```

**原因：**

先用稳定的 CSV 路径验证整个数据链路，再根据实际 Wealthfolio 版本实现自动连接，可以降低项目早期开发风险。

---

# 14. Agent CLI

```bash
finance sync
```

同步全部账户。

```bash
finance sync --account alipay
```

只同步支付宝。

```bash
finance login --account alipay
```

启动支付宝浏览器 Profile，等待人工登录。

```bash
finance check-login
```

检查所有账户登录状态。

```bash
finance validate
```

检查标准化数据。

```bash
finance deduplicate
```

检查重复交易。

```bash
finance export
```

生成 Wealthfolio CSV。

```bash
finance wealthfolio sync
```

调用 Wealthfolio Adapter。

V1 阶段：

```text
生成 CSV
```

V2 阶段：

```text
尝试自动同步到 Wealthfolio
```

```bash
finance report
```

生成本次同步报告。

```bash
finance retry --account alipay
```

重试指定账户。

---

# 15. 异常处理

## LoginExpired

```text
停止该账户
↓
保存已有数据
↓
通知用户
↓
等待人工重新认证
```

## CaptchaDetected

```text
停止自动化
↓
等待人工处理
```

不尝试自动破解。

## DataMissing

```text
记录异常
↓
不写入 Canonical Database
↓
等待人工复核
```

## OCRLowConfidence

```text
标记 REVIEW_REQUIRED
```

## MappingError

```text
进入 Security Mapping Queue
```

## WealthfolioAdapterError

新增：

```text
Canonical Database
        ↓
同步 Wealthfolio 失败
        ↓
保留 Canonical Database
        ↓
记录 Adapter Error
        ↓
允许稍后重新执行 Adapter
```

【相比第一版的修改】

新增：

```text
WealthfolioAdapterError
```

**原因：**

Wealthfolio 同步失败不应该影响已经成功采集、标准化和保存的数据。

例如：

```text
支付宝抓取成功
SQLite 保存成功
Wealthfolio 同步失败
```

此时数据仍然安全存在 SQLite 中，可以稍后：

```bash
finance wealthfolio sync
```

重新执行。

---

# 16. 安全设计

重点保护：

- Browser Profile
- Cookies
- Session
- Token
- 财务流水
- 资产余额
- SQLite 数据库

`.gitignore`：

```gitignore
.env
browser/
data/raw/
data/finance.sqlite
logs/
*.csv
*.db
```

日志不得记录：

- 密码
- 验证码
- Cookie
- 完整 Token
- 完整账户敏感信息

---

# 17. MVP 路线

## Phase 0：项目骨架

- [ ] Python 项目
- [ ] CLI
- [ ] 配置文件
- [ ] 日志
- [ ] SQLite
- [ ] 测试框架
- [ ] Transaction 数据模型
- [ ] Connector 基础接口

## Phase 1：支付宝基金

- [ ] Playwright Browser Profile
- [ ] 登录检测
- [ ] 基金持仓读取
- [ ] 交易记录读取
- [ ] OCR fallback
- [ ] Security Mapping
- [ ] SQLite Canonical Database
- [ ] Wealthfolio CSV

## Phase 2：Wealthfolio V1

- [ ] 完成 Wealthfolio 字段映射
- [ ] CSV Exporter
- [ ] CSV 导入验证
- [ ] 端到端测试：
  `支付宝 → SQLite → CSV → Wealthfolio`

## Phase 3：券商

- [ ] CSV 导入
- [ ] 交易标准化
- [ ] 去重
- [ ] 多币种
- [ ] Security Mapping

## Phase 4：银行

- [ ] 余额
- [ ] 流水
- [ ] 账户净值

## Phase 5：Wealthfolio V2

- [ ] 调研当前 Wealthfolio 实际接口
- [ ] 实现 Wealthfolio Adapter
- [ ] 自动同步
- [ ] 同步结果验证
- [ ] Adapter 重试机制

## Phase 6：自动化

- [ ] Windows Task Scheduler / Cron
- [ ] 自动重试
- [ ] 异常通知
- [ ] 每日同步报告

## Phase 7：分析

- [ ] 总净资产
- [ ] 资产配置
- [ ] 投资收益
- [ ] 现金流
- [ ] 数据质量监控

---

# 18. Coding Agent 开发规则

Coding Agent 开始工作前必须：

1. 阅读 `README.md`
2. 阅读 `ARCHITECTURE.md`
3. 阅读 `DATA_SCHEMA.md`
4. 阅读 `CONNECTOR_SPEC.md`
5. 阅读 `SECURITY.md`
6. 阅读 `WEALTHFOLIO_ADAPTER.md`
7. 阅读 `ROADMAP.md`

开发时：

- 不擅自改变数据模型
- 不擅自改变目录结构
- 不把账号密码写进代码
- 不绕过验证码
- 不上传用户财务数据
- 每完成一个模块都增加测试
- 先完成 Phase 0，再进入 Phase 1
- 修改架构前先说明理由
- Connector 不直接依赖 Wealthfolio
- Canonical Database 不依赖 CSV
- Wealthfolio Adapter 不修改原始 Raw Data
- 未确认 Wealthfolio 实际接口前，不得猜测其内部 API 或数据库结构

---

# 19. 第一开发任务

Coding Agent 第一阶段只执行：

```text
TASK-001

创建 Python 项目骨架。
```

要求：

1. 创建目录结构。
2. 创建 `pyproject.toml`。
3. 创建 CLI。
4. 创建配置系统。
5. 创建 logging。
6. 创建 SQLite 数据库。
7. 创建 Transaction 数据模型。
8. 创建基础 Connector 接口。
9. 创建基础 Wealthfolio Adapter 接口。
10. 创建单元测试。
11. 不实现支付宝自动化。
12. 不实现 OCR。
13. 不处理真实账户。
14. 不修改 Wealthfolio 源代码。

---

# 20. 第二开发任务

```text
TASK-002

实现 Browser Session 管理。
```

要求：

1. 创建独立 Browser Profile。
2. 支持首次人工登录。
3. 支持复用 Profile。
4. 支持 `login_status()`。
5. 检测登录失效。
6. 不自动绕过验证码。
7. 添加测试。

---

# 21. 第三开发任务

```text
TASK-003

实现支付宝基金 Connector MVP。
```

要求：

1. 基金持仓读取。
2. 基金交易记录读取。
3. 保存 Raw Data。
4. 转换为统一 Transaction Model。
5. 执行 Validator。
6. 执行 Deduplicator。
7. 写入 SQLite。
8. 不直接生成 Wealthfolio 特定数据结构。
9. 添加测试。

---

# 22. 第四开发任务

```text
TASK-004

实现 Wealthfolio V1 CSV Adapter。
```

要求：

1. 从 SQLite 读取已验证交易。
2. 使用 Wealthfolio Mapper 转换字段。
3. 生成 `wealthfolio_default_import.csv`。
4. 执行导出前校验。
5. 不修改 SQLite 原始数据。
6. 添加端到端测试。
7. 验证：
   `支付宝 → SQLite → CSV → Wealthfolio`

---

# 23. 第五开发任务

```text
TASK-005

调研并设计 Wealthfolio V2 Adapter。
```

要求：

1. 确认当前 Wealthfolio 版本。
2. 确认其数据模型。
3. 确认官方/实际可用的导入接口。
4. 确认是否存在 Extension / Plugin API。
5. 确认是否存在本地 API。
6. 确认数据库结构及其是否适合作为集成入口。
7. 不在没有证据的情况下修改 Wealthfolio 数据库。
8. 输出 `WEALTHFOLIO_ADAPTER.md`。
9. 只有完成调研后，才实现自动同步。

---

# 24. 第一版与 V2 的核心区别总结

| 项目 | 第一版 | V2 |
|---|---|---|
| 主流程 | 数据 → CSV → Wealthfolio | 数据 → SQLite → Adapter → Wealthfolio |
| 主数据层 | SQLite 有规划，但定位不够明确 | SQLite = Canonical Database |
| CSV | 主要输出结果 | 下游交换格式 |
| Wealthfolio | 主要作为最终导入目标 | 下游消费者 |
| Wealthfolio 接入 | CSV Exporter | Adapter + CSV Exporter |
| 自动同步 | 未明确 | V2 专门设计 |
| Connector | 采集数据 | 只负责采集，与 Wealthfolio 解耦 |
| 去重 | 字段组合 Hash | 优先使用 sourceTransactionId |
| 映射 | Fund Mapping | Security Mapping |
| 同步失败 | 主要考虑采集异常 | Adapter 失败不影响 SQLite |
| 项目扩展性 | 偏向 Wealthfolio | 可连接其他下游系统 |

---

# 25. 为什么做这些修改

## 25.1 SQLite 不应该只是“存储工具”

第一版已经有 SQLite，但 V2 明确它是：

```text
Finance Agent 的事实数据源
```

即：

```text
支付宝 ─┐
银行   ─┼→ SQLite
券商   ─┘
```

而不是：

```text
支付宝 → CSV → Wealthfolio
```

这样系统中的每个下游组件都读取同一份经过校验的数据。

---

## 25.2 CSV 不应该成为系统核心

CSV 很适合：

```text
系统 A
 ↓
文件
 ↓
系统 B
```

但不适合承担：

```text
长期数据库
交易去重
同步状态
错误恢复
来源追踪
```

因此：

```text
SQLite = 数据库
CSV = 导出格式
```

职责更加清晰。

---

## 25.3 Wealthfolio Adapter 可以保护整个系统

如果未来 Wealthfolio：

```text
CSV 格式变化
```

只修改：

```text
wealthfolio/exporter.py
```

如果未来出现：

```text
官方 API
```

只实现：

```text
wealthfolio/adapter.py
```

如果以后你不用 Wealthfolio，而使用其他软件：

```text
SQLite
 ↓
PortfolioPerformance Adapter
```

也不需要重新写支付宝 Connector。

---

## 25.4 先做 V1，再做 V2

不建议一开始就修改 Wealthfolio。

先验证：

```text
支付宝
 ↓
采集
 ↓
标准化
 ↓
校验
 ↓
去重
 ↓
SQLite
 ↓
CSV
 ↓
Wealthfolio
```

整个链路稳定后，再研究：

```text
SQLite
 ↓
Wealthfolio Adapter
 ↓
自动同步
```

这样可以把问题拆成两个相对独立的问题：

```text
问题 A：
能不能稳定获取并标准化金融数据？

问题 B：
能不能自动把标准化数据交给 Wealthfolio？
```

先解决 A，再解决 B。

---

# 26. 项目最终目标

最终系统：

```text
                         Finance Agent
                              │
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
            支付宝            银行             券商
              │               │               │
              └───────────────┼───────────────┘
                              ↓
                        数据标准化
                              ↓
                          数据校验
                              ↓
                            去重
                              ↓
                     Canonical Database
                           SQLite
                              ↓
                    Wealthfolio Adapter
                       /            \
                      /              \
                     ↓                ↓
             CSV Exporter       Auto Sync
                     ↓                ↓
                     └──────┬─────────┘
                            ↓
                       Wealthfolio
                            ↓
                       财富仪表盘
```

系统应该能够长期运行，并在登录失效、数据异常、证券映射失败或 Wealthfolio 同步失败时，把需要人工处理的部分明确交给用户，而不是尝试绕过平台安全机制。

---

# 27. V2 架构一句话定义

> **Finance Agent 负责把现实世界分散的金融账户数据转换成可信的本地标准化财富数据；Wealthfolio 只是这个标准化数据的一个下游消费者。**

这也是本项目后续开发必须遵守的核心架构原则。
