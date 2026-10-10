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
wealthfolio_import.csv
```

当前截图快照流程使用与原 Wealthfolio CSV 一致的字段：

``` csv
date,account,activityType,symbol,isin,quantity,unitPrice,amount,currency,fee,tax,comment
```

示例：

``` csv
2026-10-10,蚂蚁财富——测试B,buy,017125,,1458.3,0.7543,1100.0,CNY,,,持仓截图+公开净值API
```

注意：为兼容原 CSV 表头，持仓快照暂以 `activityType=buy` 表示。该行为可能导致同一持仓的两个截图被 Wealthfolio 当作两笔买入活动，详见“当前实施状态与问题”。

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


# 20. 当前截图输入规范

截图保存位置：

``` text
FinanceBot/data/raw/alipay/
```

截图获取方式：

> 打开支付宝，点击下方“理财”，下拉总资产后点击“基金”，再点击“我的总资产”进行截图。

需要的页面内容：

- 基金名称或可识别的名称；
- 持有金额；
- 持有收益；
- 持有收益率。

项目保留的打码样式模板：

``` text
FinanceBot/docs/templates/持仓截图模板_打码.jpg
```

正式输入不要使用打码模板。模板只用于说明页面结构和敏感数字位置。

当前一键入口：

``` text
运行截图转CSV.bat
```

执行流程：

``` text
JPG
→ Windows OCR
→ OCR JSON
→ 持仓行/列解析
→ 公开净值 API
→ 持有份额和平均成本计算
→ Wealthfolio CSV
```

---

# 21. 当前实施状态与问题

## 21.1 已完成

- [x] 项目根目录提供一键 BAT；
- [x] JPG 自动放入 `FinanceBot/data/raw/alipay/` 后自动选择；
- [x] Windows 本地 OCR 生成文本、行和文字坐标；
- [x] 支持“我的持有”和“全部持有”两种常见列表布局；
- [x] 自动提取持有金额、持有收益并计算持有收益率；
- [x] 调用公开净值 API 获取基金单位净值；
- [x] 计算持仓总成本、持有份额、每股平均成本；
- [x] 生成与原 Wealthfolio CSV 表头一致的文件；
- [x] 净值缓存保存到本地；
- [x] 已提供关键数字打码的 JPG 样式模板。

## 21.2 未完成

- [ ] 多张截图批量生成多个 CSV；
- [ ] 同一持仓不同截图时间的自动归并；
- [ ] 自动识别“旧快照”和“新快照”并只保留最新快照；
- [ ] 自动导入 Wealthfolio；
- [ ] Wealthfolio 导入后自动检查重复数据；
- [ ] 自动删除或冲销重复导入的活动；
- [ ] `sourceTransactionId` 级别的稳定去重；
- [ ] 详情页、其他 App 或全新布局的 OCR 适配；
- [ ] 新基金名称自动搜索并补全基金代码；
- [ ] 每日净值结算后的定时更新；
- [ ] Ollama 复杂 OCR 纠错的正式集成。

## 21.3 当前项目存在的问题

### 问题一：两张截图不能同时生成两个 CSV

当前 BAT 默认只处理 `FinanceBot/data/raw/alipay/` 下修改时间最新的 JPG，并固定输出：

``` text
wealthfolio_import_auto.csv
snapshot_input.auto.json
```

因此：

- 同时放入两张 JPG 时只会处理最新的一张；
- 连续运行两次会覆盖上一次结果；
- 两张同一持仓、不同截图时间的文件不会自动合并。

### 问题二：两个时间点可能被 Wealthfolio 当作两笔交易

当前 CSV 为了兼容原 Wealthfolio 字段，将每条持仓快照写成：

``` text
activityType=buy
```

如果两张截图分别生成并作为“交易活动”导入，可能得到：

``` text
第一次截图 → buy
第二次截图 → buy
```

Wealthfolio 会把它们看作两笔买入，从而重复计算持仓。

即使使用 Wealthfolio 的持仓快照导入，不同日期也可能形成两个持仓快照。当前项目没有自动识别它们是同一持仓的不同时间点。

### 问题三：缺少稳定来源交易 ID

当前截图没有平台交易 ID，无法使用：

``` text
sourceTransactionId
```

进行可靠去重。名称、日期、金额、份额的组合只能作为临时去重依据，遇到净值变化或四舍五入就可能失效。

### 问题四：基金代码映射仍是辅助依赖

OCR 主要识别基金名称，基金代码由本地名称映射表补全。遇到未登记的新基金、名称截断或同名基金时，需要人工补充映射。

## 21.4 推荐的重复截图处理策略

在未实现自动归并前，采用以下人工策略：

1. 同一批次只保留最新截图；
2. 运行 BAT 生成一个 CSV；
3. 核对 CSV 中的日期、份额和平均成本；
4. 只导入这个最新 CSV；
5. 将旧截图移动到归档目录，不重复导入。

未来应将持仓快照和交易活动分开：

``` text
持仓快照 = quantity + averageCost + snapshotDate
交易活动 = transactionId + buy/sell + actualTradeDate
```

这样不同截图时间只产生不同快照，不会被误认为两笔买入。
