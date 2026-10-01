# 支付宝基金交割单 PDF 直导入 Wealthfolio —— Addon 技术设计

> 版本：v0.1（草案）・日期：2026-09-29
> 目标：把「PDF → Python 转 CSV → Wealthfolio 手动导入」两步流程，缩成「PDF 拖进 Wealthfolio 导入界面 → 直接入库」一步。
> 范围：仅设计；涉及现有代码移植的部分均给出「Python 源 → TS 目标」对照，可直接照做。



***

## 1. 背景与约束

### 1.1 现状



```
支付宝交割单 PDF
   │  (你已有的 alipay_fund_csv 程序)
   ▼
wealthfolio_import.csv        ← data/output/，12 列标准格式
   │  (Wealthfolio 导入向导，选账户→拖 CSV→映射→确认)
   ▼
Wealthfolio 数据库
```

### 1.2 用户诉求

直接把支付宝 PDF 放进 Wealthfolio 的「上传 CSV 文件」区域（截图里那个上传框），数据就完成导入。

### 1.3 硬约束（已核实官方文档）



| 约束                   | 说明                                                                               |
| -------------------- | -------------------------------------------------------------------------------- |
| 核心上传区写死「仅限 CSV」      | 官方导入向导只接受 CSV；第三方代码无法修改核心 UI                                                     |
| Wealthfolio 无 PDF 解析 | 官方没有任何 PDF 导入通道                                                                  |
| Addon 沙箱禁本地网络        | `network.request` 仅 HTTPS 公网域名，[localhost/](https://localhost/)私网 / 链路本地 IP 全部拦截 |
| Addon 沙箱无任意文件读取      | Files API 只有 `openCsvDialog` / `openSaveDialog`（均 CSV）                           |
| 包体积限制                | 256 个文件条目 / 单文件 5 MiB / 总计 25 MiB                                                |
| 响应体限制                | 请求体 ≤1 MiB，响应体 ≤2 MiB，重定向禁用                                                      |

**结论**：核心上传区无法被第三方接管；「PDF 一步导入」只能通过 **Wealthfolio Addon** 实现 —— 由 Addon 自己提供一个长得跟官方导入页一样的拖放区，收到 PDF 后在 Addon 内解析并直接调用官方导入 API 入库。



***

## 2. 可行性依据（官方 Addon API，3.7+）



| 能力     | API                                                                        | 用途                                   |
| ------ | -------------------------------------------------------------------------- | ------------------------------------ |
| 文件拖放接收 | `events.import.onDrop` / `onDropHover` / `onDropCancelled`                 | 文件拖入导入时触发，`event.payload.files` 携带文件 |
| 程序化导入  | `activities.checkImport()` / `import()` / `saveMany()` / `create()`        | 校验 + 直接写入，带重复检测                      |
| 账户管理   | `accounts.getAll()` / `create()`                                           | 匹配 / 创建「蚂蚁财富」账户                      |
| 页面与导航  | `contributes.routes` + `contributes.links.sidebar`，`navigation.navigate()` | 侧边栏入口 + 完成跳转                         |
| 通知     | `toast.success/error/warning`                                              | 导入结果反馈                               |
| 净值（可选） | `network.request`（HTTPS）                                                   | 天天基金公网接口拉最新净值                        |

来源：[https://wealthfolio.app/docs/addons/api-reference/](https://wealthfolio.app/docs/addons/api-reference/) 、[https://wealthfolio.app/docs/addons/](https://wealthfolio.app/docs/addons/)



***

## 3. 总体架构



```
┌─ 用户操作 ─────────────────────────────────────────────┐
│  打开 Wealthfolio → 侧边栏「支付宝对账单」 → 拖入 PDF   │
└────────────────────────┬───────────────────────────────┘
                         ▼
┌─ Addon（沙箱 iframe）──────────────────────────────────┐
│  pdfjs 解析 12 列表格        ← 移植 statement_parser.py │
│  业务分类 + 字段映射         ← 移植 exporter/position    │
│  账户匹配（蚂蚁财富）        ← accounts.getAll/create    │
│  checkImport 校验 → import() ← 官方写入 API             │
│  toast 结果 → navigate('/activities')                   │
└────────────────────────┬───────────────────────────────┘
                         ▼
              Wealthfolio 数据库（流水+持仓）
                         │  （可选，Phase 2）
                         ▼
       network.request → 天天基金 HTTPS 拉净值（可离线跳过）
```

关键取舍：



* **主入口 = Addon 自带页面**（完全自控，不与核心向导冲突）；

* `events.import.onDrop`**&#x20;全局拖放 = 增强项**，语义需原型验证（见 §7 风险），验证通过后用户把 PDF 拖到任意导入入口都行；

* **不引入本地 Python 中转**：沙箱禁访本地 HTTP，桥接方案不可行，解析逻辑必须 JS 化。



***

## 4. Addon 项目结构

建议在仓库内新建独立子目录（不污染现有 Python 代码）：



```
alipay_fund_csv/
└── alipay-addon/                    # 新目录：Addon 工程
    ├── src/
    │   ├── addon.tsx                # 入口：enable(ctx)，注册路由/事件
    │   ├── pages/ImportPage.tsx     # 拖放页（外观对齐官方导入页）
    │   ├── utils/
    │   │   ├── pdfParser.ts         # pdfjs 解析交割单 → 标准明细
    │   │   ├── statementMapper.ts   # 业务分类 + 12 列导出映射
    │   │   └── wealthfolioClient.ts # accounts/checkImport/import 封装
    │   └── types.ts                 # 明细行、ActivityImport 类型
    ├── assets/                      # 空（预留）
    ├── manifest.json                # 路由/权限/network host
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── README.md                    # 安装/开发/验证说明
```

### manifest.json 示例



```
{
  "id": "alipay-statement-import",
  "name": "支付宝对账单导入",
  "version": "0.1.0",
  "main": "dist/addon.js",
  "description": "拖入蚂蚁财富基金交割单 PDF，直接转换为 Wealthfolio 活动并入库",
  "author": "you",
  "sdkVersion": "3.8.0",
  "minWealthfolioVersion": "3.8.0",
  "enabled": true,
  "contributes": {
    "routes": [{ "id": "alipay-import" }],
    "links": {
      "sidebar": [
        {
          "id": "alipay-import",
          "route": "alipay-import",
          "label": "支付宝对账单",
          "icon": "banknote",
          "order": 100
        }
      ]
    }
  },
  "permissions": [
    { "category": "activities", "functions": ["checkImport", "import", "getAll"], "purpose": "导入支付宝基金交易流水" },
    { "category": "accounts", "functions": ["getAll", "create"], "purpose": "匹配或创建蚂蚁财富账户" },
    { "category": "events", "functions": ["onDrop"], "purpose": "接收拖入的 PDF 文件" }
  ],
  "network": {
    "allowedHosts": ["fund.eastmoney.com"]
  }
}
```

> 权限按需最小化：若 Phase 1 不做净值，可去掉 
>
> `network`
>
>  块（宿主在安装时会静态扫描实际调用的 API 并提示授权）。



***

## 5. 关键设计决策

### 5.1 PDF 解析移植（核心工作量）

**Python 现状**（`src/statement_parser.py`）：`pdfplumber.extract_tables()` 智能识别 12 列表格 → 清洗（去换行 /¥/ 逗号、"/"）→ 日期 `2026/09/29 → 2026-09-29` → 按 (基金代码，确认日期) 排序。

**TS 方案**：蚂蚁交割单是**文本型 PDF**（非扫描件），可用 `pdfjs-dist` 提取文本后**按坐标分列**：



1. `page.getTextContent()` 得到每个文本项及其 `transform`（x, y）坐标；

2. 定义 12 列的 x 边界常量 `COLUMN_BOUNDS`（在样例 PDF 上标定一次）；

3. 按 x 归属列、按 y 聚合为行；行首列含「订单号」= 表头行，跳过；

4. 清洗与日期格式逻辑逐行照搬。

**Python → TS 对照表**：



| Python（statement\_parser.py） | TS（pdfParser.ts）                | 说明                                       |
| ---------------------------- | ------------------------------- | ---------------------------------------- |
| `_IDX_*` 列索引常量               | `COLUMN_BOUNDS` 数组              | 蚂蚁改版列序变化 → 只改这一处（对齐现有维护约定）               |
| `_HEADER_MARK = "订单号"`       | 同常量                             | 表头行识别                                    |
| `_clean_text()`              | `cleanText()`                   | 去换行 / 空白                                 |
| `_to_float()`                | `toFloat()`                     | `/`、`-`、`¥`、空 → 0                        |
| `_to_date()`                 | `toDate()`                      | `(\d{4})/(\d{2})/(\d{2})` → `YYYY-MM-DD` |
| `parse_statement_pdf()`      | `parseStatementPdf(file: File)` | 返回明细行数组                                  |

> pdfjs-dist minified 约 1.5 MiB，满足包体积限制。

### 5.2 业务分类与字段映射（简单，直接照搬）

**分类逻辑**（合并 `exporter._classify` 与 `position_calculator._classify` 两处口径，TS 实现一份）：



```
转换 且 申请份额>0            → SELL（转出）
转换 且 申请金额>0            → BUY（转入）
含「卖出/转出」               → SELL
含「分红」且不含「再投」       → DIVIDEND（现金分红）
其余                          → BUY（未知类型不丢记录）
```

**12 列导出口径**（对齐 `exporter.export_wealthfolio_csv`，口径不变）：



| 字段         | BUY          | SELL    | DIVIDEND |
| ---------- | ------------ | ------- | -------- |
| amount     | 确认金额 − 手续费   | 确认金额    | 确认金额     |
| fee        | 手续费          | 手续费     | 0        |
| unitPrice  | 净额 / 份额      | 金额 / 份额 | 0        |
| quantity   | 确认份额         | 确认份额    | 0        |
| symbol     | 基金代码         | 基金代码    | 基金代码     |
| currency   | CNY          | CNY     | CNY      |
| comment    | 业务类型 \| 基金名称 | 同       | 同        |
| isin / tax | 空 / 0        | 空 / 0   | 空 / 0    |

> 与 Python 程序产出 CSV 做
>
> **同一 PDF 双跑对比**
>
> （验收项，见 §8），确保口径零漂移。

### 5.3 入库流程



```
构造 ActivityImport[]（accountId=蚂蚁财富, activityType, activityDate,
                      asset:{symbol}, quantity, unitPrice, amount,
                      currency:'CNY', fee, tax, status:'POSTED'）
   → activities.checkImport()    // 逐条校验，展示错误/警告（对应用户习惯的 Review 步骤）
   → activities.import()          // 写入 + 重复检测
   → toast.success('导入 N 笔，跳过重复 M 笔') → navigate('/activities')
```

账户匹配：`accounts.getAll()` 找名称「蚂蚁财富」；不存在则 `create({ name:'蚂蚁财富', accountType:'SECURITIES', currency:'CNY', trackingMode:'TRANSACTIONS' })`—— 具体 `accountType` 取值以实现时 SDK 类型定义为准。

### 5.4 净值获取（可选，Phase 2）



* 官方 `network.request` 允许 HTTPS 公网域名 → `https://fund.eastmoney.com/pingzhongdata/<code>.js` 可申请放行；

* 响应体 ≤2 MiB：该 JS 单基金通常远小于此，可行；

* 解析逻辑照搬 `nav_provider.py` 两个正则（`fS_name` / `Data_netWorthTrend` 末项）；

* 默认**离线**（用交割单确认净值兜底，与 `config.FETCH_NAV=False` 等价），联网拉净值作为开关项。

> 注意：6 位数字基金代码在 Wealthfolio 内置行情源的识别、以及净值更新，属于「行情 / 资产」域问题，与「导入」解耦，不在本设计范围（见 §7 风险）。



***

## 6. 实施计划（里程碑）



| 里程碑     | 内容                                                                            | 预计       | 验证方式                                  |
| ------- | ----------------------------------------------------------------------------- | -------- | ------------------------------------- |
| M1 原型验证 | 最小 addon 骨架（hello-world + 拖放页 + pdfjs 加载）；验证 onDrop 是否拿到文件内容、pdfjs 能否解析样例 PDF | 0.5\~1 天 | 本地安装 addon，拖入样例 PDF，看 toast / 日志      |
| M2 移植   | pdfParser + statementMapper + 类型；用 2\~3 份真实交割单跑通                              | 1\~2 天   | 与 Python 程序同 PDF 对比输出（§8 验收①）         |
| M3 入库   | ImportPage 完整 UI + checkImport/import + 账户匹配 + 跳转                             | 0.5 天    | 拖 PDF → /activities 出现流水，金额口径一致（验收②③） |
| M4 可选   | network.request 拉天天基金净值（开关控制）                                                 | 0.5 天    | 净值出现在持仓 / 资产页                         |

前置条件（用户本地）：



1. 确认 Wealthfolio 桌面版 ≥ 3.7（查看方法见 §9）；

2. 准备 1\~2 份真实交割单 PDF 用于标定列边界（解析仅在本地沙箱进行，不上传任何地方）。



***

## 7. 风险与开放问题



| 风险 / 问题                                                | 影响             | 应对                                                          |
| ------------------------------------------------------ | -------------- | ----------------------------------------------------------- |
| `events.import.onDrop` 语义未验证：是否携带文件内容、是否与核心 CSV 向导叠加触发 | 决定全局拖放是否启用     | M1 优先验证；主入口用 Addon 自带页面，不依赖该事件                              |
| 6 位基金代码的行情识别                                           | 持仓价格 / 收益可能拉不到 | 独立议题：自定义行情源或 MANUAL quote（`assets.updateQuoteMode`），不在本设计范围 |
| Wealthfolio 版本 < 3.7                                   | Addon 不可用      | 先升级                                                         |
| 样例 PDF 含姓名 / 身份证号                                      | 隐私             | 解析只在本地；README 沿用现有隐私说明；测试尽量脱敏                               |
| Wealthfolio API 迭代                                     | 接口变动           | 锁定 minWealthfolioVersion；文档版本为参考，以 SDK 类型为准                 |



***

## 8. 验收标准（Definition of Done）



1. **口径零漂移**：同一交割单，Addon 解析出的活动与 Python 生成的 `wealthfolio_import.csv` 逐行一致（date/amount/fee/quantity/unitPrice/activityType）；

2. **一步导入**：打开 Wealthfolio → 侧边栏「支付宝对账单」→ 拖入 PDF → 提示成功 → `/activities` 出现对应流水；

3. **幂等**：重复拖入同一 PDF → 提示重复跳过，不产生重复数据；

4. **离线可用**：不联网也能完成导入（净值走交割单确认净值兜底）；

5. **权限最小化**：安装时宿主提示的权限与 manifest 一致，无多余授权。



***

## 9. 附录

### 9.1 官方文档



* Addon 开发：[https://wealthfolio.app/docs/addons/](https://wealthfolio.app/docs/addons/)

* Addon API 参考：[https://wealthfolio.app/docs/addons/api-reference/](https://wealthfolio.app/docs/addons/api-reference/)

* CSV 导入（格式 / 映射）：[https://wealthfolio.app/docs/guide/csv-import/](https://wealthfolio.app/docs/guide/csv-import/)

* 活动类型：[https://wealthfolio.app/docs/concepts/activity-types/](https://wealthfolio.app/docs/concepts/activity-types/)

### 9.2 查看 Wealthfolio 版本



* 打开 Wealthfolio → 菜单 / 设置 → 关于（About），查看版本号；

* 版本 ≥ 3.7 才能安装 Addon；3.8 提供最新 API（本设计按 3.8 编写）。

* 当前官方文档最后更新于 2026-09-27，引用 3.8 API；若本地版本较旧，先升级。

### 9.3 Addon 安装方式（两种）



1. **开发模式（推荐调试）**：`npm run dev:server` 启动 [localhost:3001](https://localhost:3001)，Wealthfolio 自动发现开发服务器；

2. **打包安装**：构建为 ZIP（含 manifest.json + dist/），Wealthfolio 内安装 → 解压 → 校验 → 权限批准 → 启用。

### 9.4 最小骨架参考（M1 起点）



```
// src/addon.tsx
import type { AddonContext, AddonEnableFunction } from '@wealthfolio/addon-sdk';

let ctx: AddonContext;

export const enable: AddonEnableFunction = async (c) => {
  ctx = c;
  ctx.router.add({ id: 'alipay-import', path: '/addons/alipay-statement-import', component: ImportPage });

  // 全局拖放（待 M1 验证）
  const un = await ctx.api.events.import.onDrop(async (ev) => {
    const files = ev?.payload?.files as unknown as File[];
    if (files?.some((f) => f.name.toLowerCase().endsWith('.pdf'))) {
      await handlePdf(files[0]);
    }
  });
  c.onDisable(() => un?.());
};

async function handlePdf(file: File) {
  const rows = await parseStatementPdf(file);        // M2 实现
  const activities = rows.map(toActivity);           // M2 实现
  const checked = await ctx.api.activities.checkImport(activities);
  const result = await ctx.api.activities.import(checked);
  ctx.api.toast.success(`导入 ${result?.imported ?? 0} 笔活动`);
  await ctx.api.navigation.navigate('/activities');
}
```



***

*本文档为设计草案；任何与官方文档 / SDK 不一致之处，以 Wealthfolio SDK 类型与实测为准。*