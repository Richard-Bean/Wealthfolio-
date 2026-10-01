# Personal Finance Agent 项目设计文档

## 1. 项目目标

构建一个本地优先（Local-First）的个人财富自动化系统，将支付宝、银行、券商等账户中的持仓、交易流水和余额自动采集，经过标准化、校验和去重后，生成
Wealthfolio Default 格式的 CSV 文件。

目标流程：

``` text
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
Wealthfolio CSV
   ↓
Wealthfolio
```

------------------------------------------------------------------------

## 2. 核心设计原则

1.  **本地优先**：浏览器登录状态、财务原始数据尽量保存在本机。
2.  **结构化数据优先**：优先使用官方 API、官方导出、页面 DOM
    或结构化网络响应。
3.  **OCR 作为备用**：只有无法直接读取结构化数据时才使用 OCR。
4.  **AI
    不作为关键金额的唯一依据**：金额、数量、日期等关键字段必须经过规则校验。
5.  **不绕过安全机制**：验证码、二次认证、风控提示由人工处理。
6.  **幂等运行**：重复执行不能产生重复交易。
7.  **可追溯**：保存 Raw、Normalized 和 Export 三层数据。
8.  **失败不覆盖成功结果**：本次同步失败不能破坏上一次成功的数据。

------------------------------------------------------------------------

# 3. 系统架构

``` text
                    ┌──────────────────┐
                    │ Scheduler        │
                    │ 定时调度器        │
                    └────────┬─────────┘
                             ↓
                  ┌────────────────────┐
                  │ FinanceMasterAgent │
                  └─────────┬──────────┘
                            ↓
       ┌────────────────────┼────────────────────┐
       ↓                    ↓                    ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Alipay       │    │ Bank         │    │ Broker       │
│ Connector    │    │ Connector    │    │ Connector    │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       ↓                   ↓                   ↓
  API/DOM/OCR          API/CSV/DOM        API/CSV/DOM
       └───────────────────┼───────────────────┘
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
                    ┌──────────────┐
                    │ Deduplicator │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ CSV Exporter │
                    └──────┬───────┘
                           ↓
                wealthfolio_default_import.csv
```

------------------------------------------------------------------------

# 4. 项目目录

``` text
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
│   └── ROADMAP.md
│
├── src/
│   └── finance_agent/
│       ├── agent/
│       │   └── finance_master.py
│       ├── connectors/
│       │   ├── base.py
│       │   ├── alipay.py
│       │   ├── bank.py
│       │   └── broker.py
│       ├── browser/
│       │   └── session.py
│       ├── ocr/
│       │   └── paddleocr_engine.py
│       ├── normalizer/
│       │   └── transaction.py
│       ├── validators/
│       │   └── transaction.py
│       ├── storage/
│       │   ├── raw.py
│       │   └── sqlite.py
│       ├── mapping/
│       │   └── funds.py
│       └── wealthfolio/
│           └── exporter.py
│
├── tests/
├── config/
├── browser/
├── data/
│   ├── raw/
│   ├── normalized/
│   └── export/
└── logs/
```

------------------------------------------------------------------------

# 5. FinanceMasterAgent

## 状态机

``` text
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
EXPORT
 ↓
REPORT
 ↓
DONE
```

## 主要职责

-   调度账户 Connector
-   检查登录状态
-   收集数据
-   保存原始数据
-   标准化
-   校验
-   去重
-   生成 Wealthfolio CSV
-   输出运行报告

------------------------------------------------------------------------

# 6. Connector 规范

每一个金融平台独立实现 Connector。

``` python
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

-   基金持仓
-   基金交易记录

后续再加入：

-   余额
-   余额宝
-   其他财富产品

------------------------------------------------------------------------

# 7. 登录状态设计

首次运行：

``` text
启动独立浏览器 Profile
        ↓
用户人工登录
        ↓
完成验证码 / 二次认证
        ↓
保存 Browser Profile
```

后续运行：

``` text
启动 Browser Profile
        ↓
检查登录状态
        ↓
成功 → 继续
失败 → 停止 → 通知人工重新认证
```

## 安全要求

禁止：

-   把密码硬编码到代码
-   自动破解验证码
-   绕过风控
-   上传 Cookie / Session 到第三方服务

Browser Profile 属于敏感数据，应加入 `.gitignore`。

------------------------------------------------------------------------

# 8. 数据获取优先级

``` text
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

``` text
OCR:
金额 = 889.77

↓

规则校验:
数量 × 单价 ≈ 金额

↓

通过 → 保存
失败 → 人工复核
```

------------------------------------------------------------------------

# 9. 统一交易数据模型

  字段           类型        必填 说明
  -------------- --------- ------ --------------------------
  date           date          是 交易日期
  account        string        是 账户名称
  activityType   enum          是 BUY / SELL / DIVIDEND 等
  symbol         string        是 证券代码
  isin           string        否 ISIN
  quantity       decimal       是 数量/份额
  unitPrice      decimal       是 单价
  amount         decimal       是 金额
  currency       string        是 CNY / USD 等
  fee            decimal       否 手续费
  tax            decimal       否 税费
  comment        string        否 备注
  fxRate         decimal       否 汇率

中国基金代码必须作为字符串保存：

``` text
270023
270042
021778
012364
```

禁止自动转换成整数，以免丢失前导零。

------------------------------------------------------------------------

# 10. Wealthfolio 导出

目标文件：

``` text
wealthfolio_default_import.csv
```

示例：

``` csv
date,account,activityType,symbol,quantity,unitPrice,amount,currency,fee,tax,comment
2026-09-28,广发基金,BUY,270023,137.04,6.4928,889.77,CNY,0,0,支付宝基金
```

导出前必须完成：

-   字段完整性检查
-   数值检查
-   日期检查
-   基金代码检查
-   重复交易检查
-   币种检查

------------------------------------------------------------------------

# 11. Fund Mapping

由于 Wealthfolio 可能无法自动识别中国公募基金，因此维护基金映射表：

``` json
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

未知基金进入：

``` text
Mapping Queue
```

由用户确认后加入映射表。

------------------------------------------------------------------------

# 12. 去重

每一笔交易生成稳定指纹：

``` text
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

例如：

``` text
广发基金|2026-09-28|BUY|270023|137.04|889.77
```

计算 Hash：

``` text
transaction_id
```

数据库中已存在相同 ID 时：

``` text
SKIP
```

避免重复导入。

------------------------------------------------------------------------

# 13. Agent CLI

``` bash
finance sync
```

同步全部账户。

``` bash
finance sync --account alipay
```

只同步支付宝。

``` bash
finance login --account alipay
```

启动支付宝浏览器 Profile，等待人工登录。

``` bash
finance check-login
```

检查所有账户登录状态。

``` bash
finance validate
```

检查标准化数据。

``` bash
finance export
```

生成 Wealthfolio CSV。

``` bash
finance report
```

生成本次同步报告。

``` bash
finance retry --account alipay
```

重试指定账户。

------------------------------------------------------------------------

# 14. 异常处理

## LoginExpired

登录状态失效：

``` text
停止该账户
↓
保存已有数据
↓
通知用户
↓
等待人工重新认证
```

## CaptchaDetected

检测到验证码：

``` text
停止自动化
↓
等待人工处理
```

不尝试自动破解。

## DataMissing

关键字段缺失：

``` text
记录异常
↓
不导出该交易
↓
等待人工复核
```

## OCRLowConfidence

OCR 置信度过低：

``` text
标记 REVIEW_REQUIRED
```

## MappingError

证券代码无法识别：

``` text
进入 Fund Mapping Queue
```

------------------------------------------------------------------------

# 15. 安全设计

重点保护：

-   Browser Profile
-   Cookies
-   Session
-   Token
-   财务流水
-   资产余额
-   SQLite 数据库

`.gitignore`：

``` gitignore
.env
browser/
data/raw/
logs/
*.sqlite
*.db
*.csv
```

日志不得记录：

-   密码
-   验证码
-   Cookie
-   完整 Token

------------------------------------------------------------------------

# 16. MVP 路线

## Phase 0：项目骨架

-   [ ] Python 项目
-   [ ] CLI
-   [ ] 配置文件
-   [ ] 日志
-   [ ] SQLite
-   [ ] 测试框架

## Phase 1：支付宝基金

-   [ ] Playwright Browser Profile
-   [ ] 登录检测
-   [ ] 基金持仓读取
-   [ ] 交易记录读取
-   [ ] OCR fallback
-   [ ] 基金代码映射
-   [ ] Wealthfolio CSV

## Phase 2：券商

-   [ ] CSV 导入
-   [ ] 交易标准化
-   [ ] 去重
-   [ ] 多币种

## Phase 3：银行

-   [ ] 余额
-   [ ] 流水
-   [ ] 账户净值

## Phase 4：自动化

-   [ ] Windows Task Scheduler / Cron
-   [ ] 自动重试
-   [ ] 异常通知
-   [ ] 每日同步报告

## Phase 5：分析

-   [ ] 总净资产
-   [ ] 资产配置
-   [ ] 投资收益
-   [ ] 现金流
-   [ ] 数据质量监控

------------------------------------------------------------------------

# 17. Coding Agent 开发规则

Coding Agent 开始工作前必须：

1.  阅读 `README.md`
2.  阅读 `ARCHITECTURE.md`
3.  阅读 `DATA_SCHEMA.md`
4.  阅读 `CONNECTOR_SPEC.md`
5.  阅读 `SECURITY.md`
6.  阅读 `ROADMAP.md`

开发时：

-   不擅自改变数据模型
-   不擅自改变目录结构
-   不把账号密码写进代码
-   不绕过验证码
-   不上传用户财务数据
-   每完成一个模块都增加测试
-   先完成 Phase 0，再进入 Phase 1
-   修改架构前先说明理由

------------------------------------------------------------------------

# 18. 第一开发任务

Coding Agent 第一阶段只执行：

``` text
TASK-001

创建 Python 项目骨架。

要求：

1. 创建目录结构。
2. 创建 pyproject.toml。
3. 创建 CLI。
4. 创建配置系统。
5. 创建 logging。
6. 创建 SQLite 数据库。
7. 创建 Transaction 数据模型。
8. 创建基础 Connector 接口。
9. 创建单元测试。
10. 不实现支付宝自动化。
11. 不实现 OCR。
12. 不处理真实账户。
```

完成 TASK-001 后，再执行：

``` text
TASK-002

实现 Browser Session 管理。

要求：

1. 创建独立 Browser Profile。
2. 支持首次人工登录。
3. 支持复用 Profile。
4. 支持 login_status()。
5. 检测登录失效。
6. 不自动绕过验证码。
7. 添加测试。
```

然后：

``` text
TASK-003

实现支付宝基金 Connector MVP。
```

------------------------------------------------------------------------

# 19. 项目最终目标

最终系统：

``` text
                Finance Agent
                     │
       ┌─────────────┼─────────────┐
       ↓             ↓             ↓
     支付宝          银行          券商
       │             │             │
       └─────────────┼─────────────┘
                     ↓
              数据标准化
                     ↓
                数据校验
                     ↓
                  去重
                     ↓
             Wealthfolio CSV
                     ↓
                Wealthfolio
                     ↓
             个人财富仪表盘
```

系统应该能够长期运行，并在登录失效、数据异常或证券映射失败时，把需要人工处理的部分明确地交给用户，而不是尝试绕过平台安全机制。
