# FinanceBot —— 中国金融账户同步到 Wealthfolio

面向个人的金融账户同步连接器框架：各金融机构（支付宝/银行等）的连接器负责把来源数据解析为标准化明细，经通用业务层计算后，导出为 [Wealthfolio](https://github.com/nnaumenko/wealthfolio) 可导入的 CSV。

## 目录结构

```
FinanceBot/
├── agent/                    # AI Agent：任务理解与流程调度（规划中：planner.py / executor.py）
├── connectors/               # 机构连接器（来源/目标适配）
│   ├── alipay/               # 支付宝（蚂蚁财富）：交割单 PDF 解析 + 净值 + 一键入口
│   ├── bank/                 # 银行（预留）
│   └── wealthfolio/          # Wealthfolio 目标适配：导入 CSV 格式
├── browser/                  # Playwright / 浏览器 Profile / RPA（预留）
│   ├── profiles/
│   └── playwright/
├── core/                     # 通用业务逻辑（与具体机构无关）
│   ├── parser/               # 通用解析器（预留）
│   ├── normalizer/           # 持仓计算、对账校验、快照对账和 OCR 数值一致性校验
│   └── pipeline/             # 任务编排（预留；当前编排入口在 connectors/alipay/scripts/run.py）
├── data/                     # 全局数据层
│   ├── raw/                  # 原始数据：data/raw/alipay/ 放交割单 PDF（用户投放区）
│   ├── processed/            # 处理产物：data/processed/alipay/ 放生成的 CSV（用户取件区）
│   └── export/               # 待导出/同步给外部系统的文件（预留）
├── config/
│   └── config.yaml           # 全局配置（连接器开关、账户名、目录等）
├── tests/
│   └── connectors/alipay/    # 支付宝连接器冒烟测试（不依赖 PDF/网络）
└── logs/                     # 运行日志（alipay_fund_csv.log）
```

## 快速开始（支付宝 → Wealthfolio）

```bash
cd FinanceBot   # 进入项目目录（若已在 FinanceBot/ 内则跳过）

# 1. 安装依赖
pip install -r connectors/alipay/requirements.txt

# 2. 把支付宝邮箱下载的交割单 PDF 放入 data/raw/alipay/（只放 1 份，文件名随意）

# 3. 运行（或直接双击 connectors/alipay/运行.bat）
python connectors/alipay/scripts/run.py
```

产物：`data/processed/alipay/fund_positions.csv`（持仓汇总）、`data/processed/alipay/wealthfolio_import.csv`（可直接导入 Wealthfolio）。

## 测试

```bash
python -m pytest tests/ -v
```

## 放置映射（迁移自 alipay_fund_csv）

| 原位置（alipay_fund_csv/） | 新位置 |
|---|---|
| src/statement_parser.py | connectors/alipay/statement_parser.py |
| src/nav_provider.py | connectors/alipay/nav_provider.py |
| src/position_calculator.py | core/normalizer/position_calculator.py |
| src/validator.py | core/normalizer/validator.py |
| src/exporter.py（Wealthfolio 部分） | connectors/wealthfolio/exporter.py |
| src/exporter.py（持仓汇总部分） | connectors/alipay/exporter.py |
| scripts/run.py | connectors/alipay/scripts/run.py |
| config.py | config/config.yaml + connectors/alipay/config.py（读取器） |
| data/input | data/raw/alipay |
| data/output | data/processed/alipay |
| tests/test_pipeline.py | tests/connectors/alipay/test_pipeline.py |
| 运行.bat | connectors/alipay/运行.bat |

## 截图基金名称映射

- 独立映射表：`data/processed/alipay/fund_mapping.csv`；
- `fund_positions.csv` 只作为旧数据来源之一，不再承担完整基金字典职责；
- 本地匹配相似度阈值为 `0.88`，并要求基金公司、A/C 份额类别和人民币/美元币种一致；
- 本地没有高可信匹配时，保留 OCR 原始名称并调用公开基金搜索 API；
- API 候选过于接近、相似度过低或网络失败时进入 `pending_mapping_rows`，不猜测代码；
- 自动确认的 API 结果写入 `fund_mapping.csv`，后续运行可离线复用。

## 截图数值校验

`core/normalizer/snapshot_validation.py` 负责检查持有金额、持有收益、收益率、净值和份额之间的
关系。OCR 解析会同时读取“持有收益”和“累计收益”，自动修复可信的漏位错误，并保留原始识别值。
严重不一致会阻止导出；仅收益率口径不同但收益金额一致时记录警告。Wealthfolio 账户名统一为
“蚂蚁财富”。

这套校验主要用于提升 OCR 识别后数据的准确性，防止识别错误扩散到标准化、持仓计算、交易推断和
最终导出；它不改变 OCR 引擎本身的识别能力。

## 演进路线

### API 可行性结论

**支付宝、银行和券商的个人账户 API 对本项目不可行。** 普通个人项目无法获得可合法、稳定、
长期读取个人余额、持仓和完整历史流水的通用 API。现有接口主要面向商户、企业、收单、清算或
持牌合作方，且个人账户认证依赖密码、短信、设备和安全控件，不能改造成普通第三方数据 API。
券商的交易或量化接口也不保证提供完整历史账单。

因此，所有来源连接器都必须支持文件导入，不能依赖官方 API 才能工作。

### 实施顺序

- **优先修复快照和交易语义**：区分 `Transaction`、`PositionSnapshot`、`BalanceSnapshot`，建立稳定来源 ID，避免不同日期的持仓快照被当作重复交易。
- **券商连接器采用文件优先**：支持用户下载的 CSV、Excel、交割单和对账单 PDF，截图 OCR 只作补充。
- **银行和支付连接器采用文件优先**：支持银行流水、账单 PDF 和支付平台导出账单，通过账户映射避免银行流水与支付流水重复计算。
- **浏览器自动化属于可选辅助**：只在用户监督下辅助下载文件，不保存登录密码，不绕过验证码或风控。
- **任务编排自动化**：完成数据闭环后再实现 `agent/`，由 planner/executor 读取 `config/config.yaml` 调度各连接器。

## 隐私

交割单 PDF 含姓名、身份证号等个人信息。`.gitignore` 已忽略 `data/raw/alipay/*.pdf` 与 `data/processed/alipay/*.csv`；请勿上传到不受信任的第三方。
